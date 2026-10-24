"""Project-aware template versioning and document generation services."""

from __future__ import annotations

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING
from uuid import uuid4

from .database import DocumentRepository, DocumentSetRepository, TemplateRepository
from .documents import DocumentError, GenerationResult, analyze_docx, generate_docx
from .project import Project

if TYPE_CHECKING:
    from collections.abc import Iterable


class DocumentServiceError(RuntimeError):
    """Raised when template or generated document operations fail."""


@dataclass(frozen=True)
class DocumentPreview:
    template_path: Path
    generated: GenerationResult
    pdf_path: Path | None


class DocumentService:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.templates = TemplateRepository(project.connection)
        self.documents = DocumentRepository(project.connection)
        self.document_sets = DocumentSetRepository(project.connection)

    def import_template(
        self,
        source_path: str | Path,
        *,
        name: str,
        description: str | None = None,
        mapping: dict[str, str] | None = None,
        required_placeholders: Iterable[str] = (),
    ) -> dict[str, object]:
        self._ensure_idle()
        template = self.templates.create(name, description=description)
        template_id = str(template["id"])
        try:
            imported = self.add_template_version(
                template_id, source_path, mapping=mapping,
                required_placeholders=required_placeholders,
            )
            return {"template": template, **imported}
        except Exception:
            self.project.connection.execute("DELETE FROM templates WHERE id = ?", (template_id,))
            raise

    def add_template_version(
        self, template_id: str, source_path: str | Path, *,
        mapping: dict[str, str] | None = None,
        required_placeholders: Iterable[str] = (),
    ) -> dict[str, object]:
        self._ensure_idle()
        template = self.project.connection.execute(
            "SELECT * FROM templates WHERE id = ? AND deleted_at IS NULL", (template_id,),
        ).fetchone()
        if template is None:
            raise KeyError(f"Unknown template: {template_id}")
        if template["template_type"] != "document":
            raise DocumentServiceError("Only document templates can receive DOCX versions.")
        source = Path(source_path).resolve()
        if source.suffix.lower() != ".docx" or not source.is_file():
            raise DocumentServiceError("Template must be an existing .docx file.")
        # Analyze the captured copy so the version's hash and placeholders agree.
        relative_path = Path("templates") / template_id / f"{uuid4().hex}.docx"
        destination = self.project.file_path(relative_path, create_parent=True)
        staging = self.project.file_path(Path("tmp") / f"template-{uuid4().hex}.docx")
        try:
            content_hash = _sha256(source)
            shutil.copyfile(source, staging)
            if _sha256(staging) != content_hash:
                raise DocumentServiceError("Imported template changed while being copied.")
            analysis = analyze_docx(staging)
            configuration = _mapping_configuration(analysis.placeholders, mapping, required_placeholders)
            os.replace(staging, destination)
            version = self.templates.add_version(
                template_id, file_path=relative_path.as_posix(),
                placeholders=list(analysis.placeholders), content_hash=content_hash,
                configuration=configuration,
            )
            return {"version": version, "analysis": analysis}
        except Exception as error:
            staging.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            if isinstance(error, (DocumentServiceError, DocumentError, ValueError, KeyError)):
                raise
            raise DocumentServiceError(f"Could not import template version: {error}") from error

    def _template(self, version_id: str) -> tuple[Path, dict[str, object]]:
        version = self.templates.get_version(version_id)
        if version is None:
            raise KeyError(f"Unknown template version: {version_id}")
        if version["template_type"] != "document":
            raise DocumentServiceError("Template version is not a document template.")
        path = self.project.file_path(str(version["file_path"]))
        if not path.is_file() or _sha256(path) != version["content_hash"]:
            raise DocumentServiceError("Stored template version was changed or is missing. Import a new version.")
        return path, json.loads(str(version["configuration_json"]))

    def duplicate_template(self, version_id: str, name: str | None = None):
        self._ensure_idle()
        source, configuration = self._template(version_id)
        version = self.templates.get_version(version_id)
        template = self.project.connection.execute("SELECT description FROM templates WHERE id=? AND deleted_at IS NULL", (version["template_id"],)).fetchone()
        if template is None:
            raise DocumentServiceError("Template is no longer available.")
        captured = self.project.file_path(Path("tmp") / f"duplicate-{uuid4().hex}.docx", create_parent=True)
        try:
            shutil.copyfile(source, captured)
            if _sha256(captured) != version["content_hash"]:
                raise DocumentServiceError("Selected template version changed while being copied.")
            return self.import_template(captured, name=name or str(version["template_name"]) + " Kopie", description=template["description"],
                                        mapping=configuration.get("mapping", {}),
                                        required_placeholders=configuration.get("required_placeholders", []))
        finally:
            captured.unlink(missing_ok=True)

    def _ensure_idle(self) -> None:
        if self.project.connection.in_transaction:
            raise DocumentServiceError("Finish the current transaction before changing project documents.")

    @contextmanager
    def _record_transaction(self):
        """Persist the set and document together after file generation finished."""
        self.project.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.project.connection.commit()
        except BaseException:
            self.project.connection.rollback()
            raise

    def generate_from_context(
        self, template_version_id: str, context: dict[str, object], **options,
    ) -> tuple[GenerationResult, dict[str, object]]:
        """Resolve the version's field mapping from nested domain records."""
        _, configuration = self._template(template_version_id)
        values = resolve_mapping(configuration.get("mapping", {}), context)
        return self.generate_document(template_version_id, values, **options)

    @contextmanager
    def preview_document(
        self, template_version_id: str, values: dict[str, object], *,
        required_placeholders: Iterable[str] = (), with_pdf: bool = False,
        executable: str | Path | None = None, timeout_seconds: int = 120,
        cancelled=None,
    ):
        """Keep preview files available inside the context, then remove them."""
        template_path, configuration = self._template(template_version_id)
        required = set(required_placeholders) | set(configuration.get("required_placeholders", []))
        with tempfile.TemporaryDirectory(prefix="preview-", dir=self.project.path / "tmp") as folder:
            generated = generate_docx(template_path, Path(folder) / "preview.docx", values,
                                      required_placeholders=required)
            pdf = convert_docx_to_pdf(
                generated.output_path, Path(folder) / "preview.pdf",
                executable=executable, timeout_seconds=timeout_seconds,
                **({"cancelled": cancelled} if cancelled is not None else {}),
            ) if with_pdf else None
            yield DocumentPreview(template_path, generated, pdf)

    def generate_document(
        self,
        template_version_id: str,
        values: dict[str, object],
        *,
        output_filename: str,
        required_placeholders: Iterable[str] = (),
        application_id: str | None = None,
        document_type: str = "application_document",
        document_set_id: str | None = None,
        cancelled=None,
    ) -> tuple[GenerationResult, dict[str, object]]:
        self._ensure_idle()
        template_path, configuration = self._template(template_version_id)
        if Path(output_filename).name != output_filename or not output_filename.lower().endswith(".docx"):
            raise DocumentServiceError("Output filename must be a simple .docx filename.")

        required = set(required_placeholders) | set(configuration.get("required_placeholders", []))
        output_relative = Path("documents") / "generated" / f"{uuid4().hex}-{output_filename}"
        output_path = self.project.file_path(output_relative, create_parent=True)
        staging_path = self.project.file_path(Path("tmp") / f"generated-{uuid4().hex}.docx")
        try:
            result = generate_docx(
                template_path,
                staging_path,
                values,
                required_placeholders=required,
            )
            if cancelled and cancelled():
                raise DocumentServiceError(_ui_tr('Dokumenterzeugung abgebrochen; Original bleibt erhalten.'))
            os.replace(staging_path, output_path)
            with self._record_transaction():
                if document_set_id is None:
                    document_set = self.document_sets.create(output_filename, application_id=application_id)
                    document_set_id = str(document_set["id"])
                document = self.documents.create(
                    file_path=output_relative.as_posix(),
                    original_filename=output_filename,
                    file_size_bytes=output_path.stat().st_size,
                    file_hash=_sha256(output_path),
                    template_version_id=template_version_id,
                    document_type=document_type,
                    application_id=application_id,
                    document_set_id=document_set_id,
                )
            return GenerationResult(
                output_path=output_path,
                replaced=result.replaced,
                unresolved=result.unresolved,
            ), document
        except Exception as error:
            staging_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            if isinstance(error, (DocumentServiceError, DocumentError, KeyError, ValueError)):
                raise
            raise DocumentServiceError(f"Could not save generated document: {error}") from error

    def create_pdf_version(
        self,
        source_document_id: str,
        *,
        executable: str | Path | None = None,
        timeout_seconds: int = 120,
        cancelled=None,
    ) -> dict[str, object]:
        self._ensure_idle()
        source_document = self.project.connection.execute(
            "SELECT * FROM documents WHERE id = ? AND deleted_at IS NULL",
            (source_document_id,),
        ).fetchone()
        if source_document is None:
            raise KeyError(f"Unknown document: {source_document_id}")
        if source_document["format"] != "docx":
            raise DocumentServiceError("PDF conversion source must be a DOCX document.")

        source_path = self.project.file_path(str(source_document["file_path"]))
        if not source_path.is_file() or _sha256(source_path) != source_document["file_hash"]:
            raise DocumentServiceError("Generated DOCX was changed or is missing. Generate it again before conversion.")
        original_name = Path(str(source_document["original_filename"])).stem + ".pdf"
        relative_path = Path("documents") / "generated" / f"{uuid4().hex}-{original_name}"
        output_path = self.project.file_path(relative_path, create_parent=True)
        staging_path = self.project.file_path(Path("tmp") / f"pdf-{uuid4().hex}.pdf")
        try:
            convert_docx_to_pdf(
                source_path,
                staging_path,
                executable=executable,
                timeout_seconds=timeout_seconds,
                **({"cancelled": cancelled} if cancelled is not None else {}),
            )
            if cancelled and cancelled():
                raise DocumentServiceError(_ui_tr('PDF-Erzeugung abgebrochen; Original bleibt erhalten.'))
            os.replace(staging_path, output_path)
            return self.documents.create(
                file_path=relative_path.as_posix(),
                original_filename=original_name,
                file_size_bytes=output_path.stat().st_size,
                file_hash=_sha256(output_path),
                template_version_id=(
                    str(source_document["template_version_id"])
                    if source_document["template_version_id"] is not None
                    else None
                ),
                document_type=str(source_document["document_type"]),
                application_id=(
                    str(source_document["application_id"])
                    if source_document["application_id"] is not None
                    else None
                ),
                file_format="pdf",
                source_document_id=source_document_id,
                document_set_id=source_document["document_set_id"],
            )
        except Exception as error:
            staging_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            if isinstance(error, (DocumentServiceError, KeyError, ValueError)):
                raise
            raise DocumentServiceError(f"Could not save PDF document: {error}") from error


def convert_docx_to_pdf(
    source_path: str | Path,
    output_path: str | Path,
    *,
    executable: str | Path | None = None,
    timeout_seconds: int = 120,
    cancelled=None,
) -> Path:
    """Convert a DOCX to PDF with LibreOffice, if it is installed."""
    source = Path(source_path).resolve()
    destination = Path(output_path).resolve()
    converter = str(executable) if executable is not None else find_libreoffice()
    if not converter:
        raise DocumentServiceError(
            "LibreOffice was not found. Install it or provide its soffice executable path."
        )
    if not source.is_file() or source.suffix.lower() != ".docx":
        raise DocumentServiceError("PDF conversion requires an existing .docx source file.")
    if source == destination or destination.suffix.lower() != ".pdf":
        raise DocumentServiceError("PDF destination must be a separate .pdf file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    try:
        if cancelled and cancelled():
            raise DocumentServiceError(_ui_tr('PDF-Konvertierung abgebrochen; Original bleibt erhalten.'))
        with tempfile.TemporaryDirectory(
            # LibreOffice's profile can exceed Windows path limits in deeply
            # nested project output folders. Keep conversion paths short.
            prefix="ec-pdf-", ignore_cleanup_errors=True
        ) as temporary_directory:
            temporary_output = Path(temporary_directory)
            profile_uri = (temporary_output / "profile").as_uri()
            command = [converter, f"-env:UserInstallation={profile_uri}", "--headless",
                       "--convert-to", "pdf", "--outdir", str(temporary_output), str(source)]
            if cancelled is None:
                result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
            else:
                import time
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                deadline = time.monotonic() + timeout_seconds
                try:
                    while True:
                        if cancelled():
                            raise DocumentServiceError(_ui_tr('PDF-Konvertierung abgebrochen; Original bleibt erhalten.'))
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(command, timeout_seconds)
                        try:
                            stdout, stderr = process.communicate(timeout=min(.2, remaining))
                            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                            break
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    if process.poll() is None:
                        if os.name == "nt":
                            # Only this isolated headless converter and its children are stopped.
                            try:
                                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                               timeout=5, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                            except (OSError, subprocess.TimeoutExpired):
                                pass
                        if process.poll() is None:
                            process.kill()
                        process.communicate(timeout=2)
            generated_pdf = temporary_output / f"{source.stem}.pdf"
            if result.returncode != 0 or not generated_pdf.is_file():
                details = (result.stderr or result.stdout).strip()
                raise DocumentServiceError(
                    f"LibreOffice conversion failed (exit {result.returncode}): {details}"
                )
            with generated_pdf.open("rb") as pdf_file:
                if pdf_file.read(5) != b"%PDF-":
                    raise DocumentServiceError("LibreOffice produced an invalid PDF file.")
            # Publish on the destination volume, including projects on another
            # drive. Failed copying never replaces an existing output.
            handle, stage_name = tempfile.mkstemp(prefix=".ec-pdf-", suffix=".pdf", dir=destination.parent)
            os.close(handle)
            stage = Path(stage_name)
            try:
                shutil.copyfile(generated_pdf, stage)
                if cancelled and cancelled():
                    raise DocumentServiceError(_ui_tr('PDF-Konvertierung abgebrochen; Original bleibt erhalten.'))
                os.replace(stage, destination)
            finally:
                stage.unlink(missing_ok=True)
    except subprocess.TimeoutExpired as error:
        raise DocumentServiceError(f"LibreOffice conversion exceeded {timeout_seconds} seconds.") from error
    except OSError as error:
        raise DocumentServiceError(f"Could not run LibreOffice: {error}") from error
    return destination


def find_libreoffice() -> str | None:
    """Find the converter on PATH or in common Windows installation folders."""
    from .resources import resource_path
    bundled = resource_path('LibreOffice', 'program', 'soffice.com')
    if bundled.is_file():
        return str(bundled)
    located = shutil.which("soffice") or shutil.which("libreoffice")
    if located:
        return located
    for variable, fallback in (("ProgramFiles", "C:/Program Files"),
                               ("ProgramFiles(x86)", "C:/Program Files (x86)")):
        candidate = Path(os.environ.get(variable, fallback)) / "LibreOffice" / "program" / "soffice.exe"
        if candidate.is_file():
            console = candidate.with_suffix('.com')
            return str(console if console.is_file() else candidate)
    local = Path(__file__).resolve().parents[2] / '.tools' / 'libreoffice' / 'program' / 'soffice.com'
    if local.is_file():
        return str(local)
    return None


def _mapping_configuration(
    placeholders: Iterable[str], mapping: dict[str, str] | None,
    required_placeholders: Iterable[str],
) -> dict[str, object]:
    mapping = {} if mapping is None else mapping
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and isinstance(path, str) and path.strip()
        and all(part.strip() for part in path.split(".")) for key, path in mapping.items()
    ):
        raise ValueError("Mapping must associate placeholder names with nonempty dotted field paths.")
    required = list(required_placeholders)
    if not all(isinstance(name, str) for name in required):
        raise ValueError("Required placeholders must be names.")
    unknown = (set(mapping) | set(required)) - set(placeholders)
    if unknown:
        raise ValueError("Configuration contains unknown placeholders: " + ", ".join(sorted(unknown)))
    return {"mapping": dict(mapping), "required_placeholders": sorted(set(required))}


def resolve_mapping(mapping: dict[str, str], context: dict[str, object]) -> dict[str, object]:
    """Resolve explicit field paths; unavailable fields stay unresolved."""
    values: dict[str, object] = {}
    for placeholder, field_path in mapping.items():
        value: object = context
        for component in field_path.split("."):
            if not isinstance(value, dict) or component not in value:
                break
            value = value[component]
        else:
            values[placeholder] = value
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

