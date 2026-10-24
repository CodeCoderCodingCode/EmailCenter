"""Tests for DOCX placeholder analysis and generation."""

import sys
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import zipfile
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.database import ApplicationRepository, apply_migrations  # noqa: E402
from emailcenter.document_service import (  # noqa: E402
    DocumentService,
    DocumentServiceError,
    convert_docx_to_pdf,
    find_libreoffice,
)
from emailcenter.documents import (  # noqa: E402
    DocumentError,
    MissingRequiredValues,
    analyze_docx,
    generate_docx,
)
from emailcenter.project import create_project  # noqa: E402


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MIGRATIONS = ROOT / "migrations"


def _make_docx(path: Path) -> None:
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14"><w:body>
  <w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Hello {{{{NA</w:t></w:r><w:r><w:t>ME}}}}</w:t></w:r><w:r><w:t> at {{{{COMPANY}}}}.</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>{{{{ROLE}}}}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  <w:p><w:r><w:t>{{{{UNKNOWN}}}}</w:t></w:r></w:p>
  <w:sectPr><w:headerReference w:type="default" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></w:sectPr>
</w:body></w:document>'''
    header_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>{{{{DATE}}}}</w:t></w:r></w:p></w:hdr>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/header1.xml", header_xml)


class DocxTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.directory = Path(self.temporary_directory.name)
        self.template = self.directory / "template.docx"
        _make_docx(self.template)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_analysis_finds_placeholders_in_body_tables_and_headers(self):
        analysis = analyze_docx(self.template)
        self.assertEqual(
            analysis.occurrences,
            {"NAME": 1, "COMPANY": 1, "ROLE": 1, "UNKNOWN": 1, "DATE": 1},
        )

    def test_generation_replaces_tokens_across_runs_and_preserves_source(self):
        original_bytes = self.template.read_bytes()
        output = self.directory / "generated.docx"
        result = generate_docx(
            self.template,
            output,
            {"{{NAME}}": "Ada Example", "COMPANY": "Example GmbH", "ROLE": "Engineer", "DATE": "2026-10-11"},
            required_placeholders=("NAME", "COMPANY", "ROLE", "DATE"),
        )
        self.assertEqual(self.template.read_bytes(), original_bytes)
        self.assertEqual(result.replaced["NAME"], 1)
        self.assertEqual(result.unresolved, ("UNKNOWN",))

        with zipfile.ZipFile(output, "r") as archive:
            body = ET.fromstring(archive.read("word/document.xml"))
            header = ET.fromstring(archive.read("word/header1.xml"))
        body_text = "".join(element.text or "" for element in body.iter(f"{{{W}}}t"))
        header_text = "".join(element.text or "" for element in header.iter(f"{{{W}}}t"))
        self.assertIn("Hello Ada Example at Example GmbH.", body_text)
        self.assertIn("Engineer", body_text)
        self.assertIn("{{UNKNOWN}}", body_text)
        self.assertEqual(header_text, "2026-10-11")
        self.assertEqual(len(list(body.iter(f"{{{W}}}r"))), 5)
        with zipfile.ZipFile(output, "r") as archive:
            serialized_body = archive.read("word/document.xml")
        self.assertIn(b'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"', serialized_body)
        self.assertIn(b'mc:Ignorable="w14"', serialized_body)

    def test_missing_required_value_stops_before_output_is_created(self):
        output = self.directory / "should-not-exist.docx"
        with self.assertRaisesRegex(MissingRequiredValues, "NAME"):
            generate_docx(self.template, output, {}, required_placeholders=("NAME",))
        self.assertFalse(output.exists())

    def test_template_cannot_be_used_as_its_own_output(self):
        with self.assertRaisesRegex(DocumentError, "must not overwrite"):
            generate_docx(self.template, self.template, {"NAME": "Ada"})

    def test_pdf_conversion_reports_missing_libreoffice(self):
        with self.assertRaisesRegex(DocumentServiceError, "Could not run LibreOffice"):
            convert_docx_to_pdf(
                self.template,
                self.directory / "output.pdf",
                executable=self.directory / "missing-soffice.exe",
            )

    def test_document_service_versions_templates_and_records_generated_document(self):
        project = create_project(self.directory / "project")
        try:
            service = DocumentService(project)
            imported = service.import_template(self.template, name="Bewerbung")
            version = imported["version"]
            self.assertEqual(version["version_number"], 1)
            self.assertEqual(version["placeholders_json"], '["COMPANY", "DATE", "NAME", "ROLE", "UNKNOWN"]')
            application = ApplicationRepository(project.connection).create("Engineer")
            generated, document = service.generate_document(
                str(version["id"]),
                {"NAME": "Ada", "COMPANY": "Example", "ROLE": "Engineer", "DATE": "today"},
                output_filename="ada.docx",
                required_placeholders=("NAME", "COMPANY", "ROLE", "DATE"),
                application_id=str(application["id"]),
            )
            self.assertTrue(generated.output_path.is_file())
            self.assertEqual(document["format"], "docx")
            self.assertEqual(document["application_id"], application["id"])
            self.assertEqual(document["template_version_id"], version["id"])
            self.assertEqual(generated.unresolved, ("UNKNOWN",))

            def fake_convert(source_path, output_path, **kwargs):
                Path(output_path).write_bytes(b"%PDF-1.7\nmock pdf bytes")
                return Path(output_path)

            with patch("emailcenter.document_service.convert_docx_to_pdf", side_effect=fake_convert):
                pdf_document = service.create_pdf_version(str(document["id"]))
            self.assertEqual(pdf_document["format"], "pdf")
            self.assertEqual(pdf_document["source_document_id"], document["id"])
            self.assertEqual(pdf_document["application_id"], application["id"])
            self.assertEqual(pdf_document["document_set_id"], document["document_set_id"])
            members = service.document_sets.list_documents(str(document["document_set_id"]))
            self.assertEqual({item["format"] for item in members}, {"docx", "pdf"})
        finally:
            project.close()

    def test_new_version_keeps_previous_file_and_mapping_unchanged(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            first = service.import_template(
                self.template, name="Application", mapping={"NAME": "applicant.name"},
                required_placeholders=("NAME",),
            )
            old_version = first["version"]
            old_file = project.file_path(old_version["file_path"])
            original = old_file.read_bytes()
            # A new source file has different content, while the archived version stays fixed.
            updated_source = self.directory / "updated.docx"
            generate_docx(self.template, updated_source, {"COMPANY": "New Company"})
            second = service.add_template_version(
                first["template"]["id"], updated_source,
                mapping={"NAME": "contact.name"}, required_placeholders=("NAME",),
            )
            self.assertEqual(second["version"]["version_number"], 2)
            self.assertNotEqual(second["version"]["content_hash"], old_version["content_hash"])
            self.assertEqual(old_file.read_bytes(), original)
            self.assertEqual(service.templates.get_version(old_version["id"]), old_version)
            result, _ = service.generate_from_context(
                old_version["id"], {"applicant": {"name": "Ada"}}, output_filename="old.docx",
            )
            self.assertEqual(result.replaced["NAME"], 1)
            result, _ = service.generate_from_context(
                second["version"]["id"], {"contact": {"name": "Grace"}}, output_filename="new.docx",
            )
            self.assertEqual(result.replaced["NAME"], 1)

    def test_mapping_missing_required_field_reports_structured_error(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            imported = service.import_template(
                self.template, name="Application", mapping={"NAME": "applicant.name"},
                required_placeholders=("NAME",),
            )
            with self.assertRaises(MissingRequiredValues) as raised:
                service.generate_from_context(imported["version"]["id"], {}, output_filename="bad.docx")
            self.assertEqual(raised.exception.placeholders, ("NAME",))
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM document_sets").fetchone()[0], 0)
            self.assertEqual(list((project.path / "tmp").iterdir()), [])

    def test_invalid_mapping_removes_failed_import_and_files(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            for mapping in ({"TYPO": "applicant.name"}, {"NAME": "applicant..name"}):
                with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                    service.import_template(self.template, name="Invalid", mapping=mapping)
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM templates").fetchone()[0], 0)
            self.assertEqual(list((project.path / "templates").rglob("*.docx")), [])
            self.assertEqual(list((project.path / "tmp").iterdir()), [])

    def test_modified_stored_template_is_rejected_before_generation(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            project.file_path(version["file_path"]).write_bytes(b"modified")
            with self.assertRaisesRegex(DocumentServiceError, "changed or is missing"):
                service.generate_document(version["id"], {}, output_filename="bad.docx")
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)

    def test_preview_is_temporary_and_records_no_documents(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]

            def fake_convert(source, destination, **kwargs):
                Path(destination).write_bytes(b"%PDF-1.7\npreview")
                return Path(destination)

            with patch("emailcenter.document_service.convert_docx_to_pdf", side_effect=fake_convert):
                with service.preview_document(version["id"], {"NAME": "Ada"}, with_pdf=True) as preview:
                    generated_path = preview.generated.output_path
                    pdf_path = preview.pdf_path
                    self.assertTrue(generated_path.is_file())
                    self.assertTrue(pdf_path.is_file())
                    self.assertTrue(preview.template_path.is_file())
                    self.assertEqual(preview.generated.replaced["NAME"], 1)
            self.assertFalse(generated_path.exists())
            self.assertFalse(pdf_path.exists())
            self.assertEqual(list((project.path / "tmp").iterdir()), [])
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM document_sets").fetchone()[0], 0)

    def test_preview_conversion_failure_cleans_temporary_files(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            with patch("emailcenter.document_service.convert_docx_to_pdf", side_effect=DocumentServiceError("failed")):
                with self.assertRaises(DocumentServiceError):
                    with service.preview_document(version["id"], {}, with_pdf=True):
                        self.fail("Failed preview must not be delivered")
            self.assertEqual(list((project.path / "tmp").iterdir()), [])

    def test_document_set_can_hold_multiple_documents_and_rejects_other_application(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            apps = ApplicationRepository(project.connection)
            first, second = apps.create("First"), apps.create("Second")
            document_set = service.document_sets.create("Application pack", application_id=first["id"])
            for name in ("letter.docx", "resume.docx"):
                service.generate_document(version["id"], {}, output_filename=name,
                                          application_id=first["id"], document_set_id=document_set["id"])
            with self.assertRaisesRegex(ValueError, "same application"):
                service.generate_document(version["id"], {}, output_filename="wrong.docx",
                                          application_id=second["id"], document_set_id=document_set["id"])
            self.assertEqual(len(service.document_sets.list_documents(document_set["id"])), 2)
            self.assertEqual(len(list((project.path / "documents").rglob("*.docx"))), 2)

    def test_failed_document_record_cleans_generated_file_and_new_set(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            with patch.object(service.documents, "create", side_effect=RuntimeError("write failed")):
                with self.assertRaises(DocumentServiceError):
                    service.generate_document(version["id"], {}, output_filename="failed.docx")
            self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM document_sets").fetchone()[0], 0)
            self.assertEqual(list((project.path / "documents").rglob("*.docx")), [])

    def test_changed_generated_docx_is_not_converted(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            result, document = service.generate_document(version["id"], {}, output_filename="generated.docx")
            result.output_path.write_bytes(b"changed")
            with self.assertRaisesRegex(DocumentServiceError, "changed or is missing"):
                service.create_pdf_version(document["id"])

    def test_database_rejection_rolls_back_set_and_document_together(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            project.connection.execute(
                "CREATE TRIGGER reject_document BEFORE INSERT ON documents "
                "BEGIN SELECT RAISE(ABORT, 'rejected'); END"
            )
            with self.assertRaisesRegex(DocumentServiceError, "rejected"):
                service.generate_document(version["id"], {}, output_filename="rejected.docx")
            self.assertFalse(project.connection.in_transaction)
            for table in ("documents", "document_sets"):
                self.assertEqual(project.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertEqual(list((project.path / "documents").rglob("*.docx")), [])

    def test_service_rejects_existing_transaction_without_modifying_it(self):
        with create_project(self.directory / "project") as project:
            service = DocumentService(project)
            version = service.import_template(self.template, name="Application")["version"]
            project.connection.execute("BEGIN")
            try:
                with self.assertRaisesRegex(DocumentServiceError, "current transaction"):
                    service.generate_document(version["id"], {}, output_filename="rejected.docx")
                self.assertTrue(project.connection.in_transaction)
                self.assertEqual(project.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
            finally:
                project.connection.rollback()

    def test_analysis_rejects_zip_without_document_part(self):
        invalid = self.directory / "invalid.docx"
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr("unrelated.txt", "not a Word document")
        with self.assertRaisesRegex(DocumentError, "missing word/document.xml"):
            analyze_docx(invalid)

    def test_converter_uses_isolated_profile_and_cleans_working_folder(self):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            folder = Path(command[command.index("--outdir") + 1])
            (folder / "template.pdf").write_bytes(b"%PDF-1.7\nconverted")
            self.assertEqual(kwargs["timeout"], 15)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        output = self.directory / "converted.pdf"
        with patch("emailcenter.document_service.tempfile.gettempdir",return_value=str(self.directory)), patch("emailcenter.document_service.subprocess.run", side_effect=fake_run):
            convert_docx_to_pdf(self.template, output, executable="soffice", timeout_seconds=15)
            convert_docx_to_pdf(self.template, output, executable="soffice", timeout_seconds=15)
        self.assertTrue(output.read_bytes().startswith(b"%PDF-"))
        profiles = [next(arg for arg in command if arg.startswith("-env:UserInstallation=file:")) for command in commands]
        self.assertNotEqual(profiles[0], profiles[1])
        self.assertEqual(list(self.directory.glob("emailcenter-pdf-*")), [])

    def test_converter_errors_preserve_existing_output(self):
        output = self.directory / "existing.pdf"
        original = b"%PDF-1.7\nexisting output"

        def invalid_pdf(command, **kwargs):
            folder = Path(command[command.index("--outdir") + 1])
            (folder / "template.pdf").write_bytes(b"not pdf")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        outcomes = [
            SimpleNamespace(returncode=1, stdout="", stderr="conversion failed"),
            SimpleNamespace(returncode=0, stdout="no output", stderr=""),
            subprocess.TimeoutExpired("soffice", 2),
            invalid_pdf,
        ]
        for outcome in outcomes:
            output.write_bytes(original)
            parameters = {"side_effect": outcome} if callable(outcome) or isinstance(outcome, Exception) else {"return_value": outcome}
            with self.subTest(outcome=outcome), patch("emailcenter.document_service.tempfile.gettempdir",return_value=str(self.directory)), patch("emailcenter.document_service.subprocess.run", **parameters):
                with self.assertRaises(DocumentServiceError):
                    convert_docx_to_pdf(self.template, output, executable="soffice", timeout_seconds=2)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(list(self.directory.glob("emailcenter-pdf-*")), [])

    def test_converter_discovers_windows_installation(self):
        installation = self.directory / "program files"
        executable = installation / "LibreOffice" / "program" / "soffice.exe"
        executable.parent.mkdir(parents=True)
        executable.touch()
        with patch("emailcenter.document_service.shutil.which", return_value=None):
            with patch.dict("os.environ", {"ProgramFiles": str(installation)}):
                self.assertEqual(find_libreoffice(), str(executable))


if __name__ == "__main__":
    unittest.main(verbosity=2)
