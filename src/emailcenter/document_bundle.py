"""Reviewed document sets as a ZIP, with a manifest and explicit missing-file report."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
from .mail_bulk import digest
from .mail_models import MailError


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def safe_name(value):
    name = re.sub(r'[^\w. -]', '_', str(value), flags=re.UNICODE).strip(" .")[:90]
    return name or "Dokument"


class DocumentBundleService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def preview(self, *, search="", selected_ids=None, formats=None, cancelled=lambda: False):
        formats = ["docx", "pdf"] if formats is None else formats
        if not isinstance(search, str) or not isinstance(formats, list) or not formats or any(f not in ("docx", "pdf") for f in formats) or len(set(formats)) != len(formats):
            raise MailError(_ui_tr('DOCX und/oder PDF sowie einen gültigen Suchfilter wählen.'))
        if selected_ids is not None and (not isinstance(selected_ids, list) or not 1 <= len(selected_ids) <= 1000 or any(not isinstance(i, str) for i in selected_ids) or len(set(selected_ids)) != len(selected_ids)):
            raise MailError(_ui_tr('1 bis 1000 verschiedene Dokumente auswählen.'))
        projection = "SELECT d.*,s.name AS set_name,a.title AS application_title FROM documents d LEFT JOIN document_sets s ON s.id=d.document_set_id LEFT JOIN applications a ON a.id=d.application_id "
        condition = "d.deleted_at IS NULL AND d.format IN ('docx','pdf')"
        parameters = []
        if selected_ids is not None:
            condition += " AND d.id IN (" + ",".join("?" for _ in selected_ids) + ")"
            parameters.extend(selected_ids)
        elif search.strip():
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            condition += " AND (d.original_filename LIKE ? ESCAPE '\\' OR s.name LIKE ? ESCAPE '\\' OR a.title LIKE ? ESCAPE '\\')"
            parameters.extend(["%" + escaped + "%"] * 3)
        seeds = [dict(row) for row in self.db.execute(projection + "WHERE " + condition + " ORDER BY d.created_at,d.id LIMIT 1001", parameters)]
        if len(seeds) > 1000:
            raise MailError(_ui_tr('Export auf höchstens 1000 Dokumente begrenzen; Filter oder Auswahl verwenden.'))
        def group(row):
            return row["document_set_id"] or row["source_document_id"] or row["id"]
        selected = set(selected_ids or [])
        if selected_ids is not None and selected - {row["id"] for row in seeds}:
            raise MailError(_ui_tr('Gewählte Dokumente fehlen oder sind keine DOCX/PDF-Dateien. Auswahl aktualisieren.'))
        matching = sorted({group(row) for row in seeds})
        rows = [dict(row) for row in self.db.execute(projection + "WHERE d.deleted_at IS NULL AND d.format IN ('docx','pdf') AND COALESCE(d.document_set_id,d.source_document_id,d.id) IN (" + ",".join("?" for _ in matching) + ") ORDER BY d.created_at,d.id LIMIT 1001", matching)] if matching else []
        if len(rows) > 1000:
            raise MailError(_ui_tr('Export auf höchstens 1000 Dokumente begrenzen.'))
        files, warnings, groups, actual = [], [], {}, {}
        total_bytes = 0
        for row in rows:
            if cancelled():
                raise MailError(_ui_tr('Dokumentvorschau abgebrochen.'))
            identifier = group(row)
            groups[identifier] = {"id": identifier, "name": row["set_name"] or row["original_filename"],
                                  "application": row["application_title"] or ""}
            error, actual_hash, size = "", None, 0
            try:
                source = self.project.file_path(row["file_path"])
                size = source.stat().st_size
                if not source.is_file() or size > 100 * 1024 * 1024:
                    raise ValueError()
                actual_hash = file_hash(source)
                if not row["file_hash"] or actual_hash != row["file_hash"]:
                    error = "Datei verändert oder gespeicherte Prüfsumme fehlt"
            except (OSError, ValueError):
                error = "Datei fehlt, ist unzugänglich oder größer als 100 MiB"
            actual[row["id"]] = {"hash": actual_hash, "error": error}
            if row["format"] in formats:
                arcname = safe_name(groups[identifier]["name"]) + "-" + safe_name(identifier) + "/" + safe_name(row["id"]) + "-" + safe_name(row["original_filename"])
                files.append({"id": row["id"], "set_id": identifier, "filename": row["original_filename"], "format": row["format"],
                              "file_path": row["file_path"], "archive_path": arcname, "hash": row["file_hash"], "size": size, "error": error})
                if error:
                    warnings.append(row["original_filename"] + ": " + error)
                else:
                    total_bytes += size
        if "pdf" in formats:
            for row in rows:
                if row["format"] == "docx" and not any(pdf["source_document_id"] == row["id"] and not actual[pdf["id"]]["error"] for pdf in rows if pdf["format"] == "pdf"):
                    warnings.append(row["original_filename"] + ": PDF-Version fehlt oder ist nicht verwendbar (unter Dokumente → PDF erzeugen).")
        if total_bytes > 1024 * 1024 * 1024:
            raise MailError(_ui_tr('Dokumentpaket ist größer als 1 GiB; Auswahl verkleinern.'))
        value = {"files": files, "sets": list(groups.values()), "warnings": warnings, "formats": formats,
                 "count": sum(not f["error"] for f in files), "bytes": total_bytes, "source_records": rows, "actual": actual}
        return {**value, "fingerprint": digest(value)}

    def write(self, preview, target_path, *, allow_incomplete=False, overwrite=False, cancelled=lambda: False):
        if type(allow_incomplete) is not bool or type(overwrite) is not bool or not preview["count"]:
            raise MailError(_ui_tr('Mindestens ein verwendbares Dokument wählen.'))
        if preview["warnings"] and not allow_incomplete:
            raise MailError(_ui_tr('Fehlende/veränderte Dateien zuerst beheben oder unvollständiges Paket ausdrücklich bestätigen.'))
        target = Path(target_path).expanduser()
        if not target.is_absolute() or target.suffix.lower() != ".zip":
            raise MailError(_ui_tr('Einen absoluten Zielpfad mit .zip auswählen.'))
        target = target.resolve()
        if target.is_relative_to(self.project.path.resolve()) and not target.is_relative_to((self.project.path / "exports").resolve()):
            raise MailError(_ui_tr('Innerhalb des Projekts nur unter exports speichern.'))
        existed = target.exists()
        if existed and (not overwrite or not target.is_file()):
            raise MailError(_ui_tr('Vorhandene ZIP-Datei ausdrücklich zum Überschreiben bestätigen.'))
        original = file_hash(target) if existed else None
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".emailcenter-documents-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
            manifest = {"version": 1, "sets": preview["sets"], "formats": preview["formats"], "warnings": preview["warnings"], "documents": []}
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for entry in preview["files"]:
                    if cancelled():
                        raise MailError(_ui_tr('Dokumentexport abgebrochen; Zieldatei bleibt erhalten.'))
                    public = {key: entry[key] for key in ("id", "set_id", "filename", "format", "archive_path", "hash", "size", "error")}
                    public["included"] = not bool(entry["error"])
                    manifest["documents"].append(public)
                    if entry["error"]:
                        continue
                    hasher, written = hashlib.sha256(), 0
                    with self.project.file_path(entry["file_path"]).open("rb") as source, archive.open(entry["archive_path"], "w") as output:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            if cancelled():
                                raise MailError(_ui_tr('Dokumentexport abgebrochen; Zieldatei bleibt erhalten.'))
                            written += len(chunk)
                            if written > 100 * 1024 * 1024:
                                raise MailError(_ui_tr('Dokument während Export vergrößert; Vorschau erneut laden.'))
                            hasher.update(chunk)
                            output.write(chunk)
                    if hasher.hexdigest() != entry["hash"] or written != entry["size"]:
                        raise MailError(_ui_tr('Dokument während Export verändert; Vorschau erneut laden.'))
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                archive.writestr("Exportbericht.txt", "EmailCenter · Dokumentpaket\n" + f"{preview['count']} Dateien · {len(preview['sets'])} Sätze\n" +
                                 ("\n".join(preview["warnings"]) if preview["warnings"] else "Alle gewählten Formate vollständig vorhanden.") + "\n")
            if cancelled():
                raise MailError(_ui_tr('Dokumentexport abgebrochen; Zieldatei bleibt erhalten.'))
            if target.exists() != existed or (existed and file_hash(target) != original):
                raise MailError(_ui_tr('Zieldatei zwischenzeitlich verändert; Export neu starten.'))
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            return {"path": str(target), "count": preview["count"], "warnings": preview["warnings"], "sets": len(preview["sets"])}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
