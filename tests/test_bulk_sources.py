"""Real Excel rows feed both mail and DOCX; no network or live credentials."""

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.bulk_sources import BulkSourceService
from emailcenter.document_service import DocumentService
from emailcenter.documents import extract_docx_text
from emailcenter.import_service import ImportService
from emailcenter.mail_bulk import BulkMailService
from emailcenter.mail_service import MailService
from emailcenter.mail_templates import MailTemplateService
from test_documents import W


class BulkSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.root / "project"), "Datenquellen")
        self.project, self.db = self.workspace.project, self.workspace.project.connection
        self.service = BulkMailService(self.project)
        self.sources = BulkSourceService(self.db)
        self.version = MailTemplateService(self.db).save(name="Bewerbung", subject="Bewerbung bei {{company.name}}",
            body="{{contact.salutation}} {{contact.display_name}},\n{{application.cover_letter}}")
        self.mapping = {"contact.display_name": "Name", "contact.email": "Email", "contact.salutation": "Anrede",
                        "company.name": "Firma", "application.cover_letter": "Anschreiben", "job.title": "Stelle"}

    def tearDown(self):
        self.workspace.close()
        self.temp.cleanup()

    def import_excel(self, count=2):
        from openpyxl import Workbook
        source = self.root / "Bewerbungen.xlsx"
        workbook = Workbook()
        workbook.active.title = "Bewerbungen"
        workbook.active.append(["Name", "Email", "Anrede", "Firma", "Anschreiben", "Stelle"])
        for i in range(count):
            workbook.active.append([f"Kontakt {i}", f"c{i}@example.test", "Guten Tag", f"Firma {i}", f"Anschreiben {i}", "Entwicklung"])
        workbook.save(source)
        workbook.close()
        importer = ImportService(self.project)
        run = importer.prepare(str(source), "contacts", {"display_name": "Name", "email": "Email"}, options={"sheet": "Bewerbungen"})
        rows = importer.list_rows(run["id"])["rows"]
        return run, rows, importer

    def options(self, rows):
        return {"version_id": self.version["id"], "items": [{"contact_id": "import:" + r["id"],
            "source": {"kind": "import", "row_id": r["id"], "mapping": self.mapping}} for r in rows]}

    def document_template(self):
        path = self.root / "letter.docx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{{{{ANREDE}}}} {{{{NAME}}}} bei {{{{FIRMA}}}}: {{{{TEXT}}}}</w:t></w:r></w:p></w:body></w:document>')
        mapping = {"ANREDE": "contact.salutation", "NAME": "contact.display_name", "FIRMA": "company.name", "TEXT": "application.cover_letter"}
        return DocumentService(self.project).import_template(path, name="Anschreiben", mapping=mapping)["version"]

    def test_excel_extra_columns_are_available_before_and_after_contact_import(self):
        run, rows, importer = self.import_excel()
        listing = self.sources.rows(run["id"], limit=1)
        self.assertIn("Anschreiben", listing["headers"])
        self.assertEqual(listing["rows"][0]["values"]["Firma"], "Firma 0")
        preview = self.service.preview(**self.options(rows))
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["rows"][0]["subject"], "Bewerbung bei Firma 0")
        self.assertIn("Guten Tag Kontakt 0", preview["rows"][0]["body"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
        importer.process(run["id"])
        preview = self.service.preview(**self.options(rows))
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["rows"][1]["source_snapshot"]["raw_values"]["Anschreiben"], "Anschreiben 1")
        self.assertEqual(self.sources.select([rows[0]["id"]], self.mapping)["contacts"][0]["email"], "c0@example.test")

    def test_mapping_pages_corrections_and_invalid_rows(self):
        run, rows, importer = self.import_excel(28)
        page = self.sources.rows(run["id"], offset=25)
        self.assertEqual(len(page["rows"]), 3)
        self.assertEqual(page["rows"][0]["number"], 27)
        importer.edit_row(rows[0]["id"], {"display_name": "Korrigiert", "email": "fixed@example.test"})
        preview = self.service.preview(**self.options([rows[0]]))
        self.assertEqual(preview["rows"][0]["name"], "Korrigiert")
        self.assertEqual(preview["rows"][0]["email"], "fixed@example.test")
        importer.edit_row(rows[1]["id"], {"display_name": "Invalid", "email": "bad"})
        self.assertFalse(self.sources.rows(run["id"])["rows"][1]["eligible"])
        self.assertFalse(self.service.preview(**self.options([rows[1]]))["ready"])
        with self.assertRaises(ValueError):
            self.sources.select([rows[1]["id"]], self.mapping)

    def test_source_change_blocks_stale_creation_and_snapshot_survives_reopen(self):
        run, rows, _ = self.import_excel()
        options = self.options(rows)
        preview = self.workspace.mail_bulk_preview(**options)
        raw = json.loads(rows[0]["source_data_json"])
        raw["Firma"] = "Neu"
        self.db.execute("UPDATE import_rows SET source_data_json=? WHERE id=?", (json.dumps(raw), rows[0]["id"]))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.workspace.mail_bulk_create("Stale", preview["preview_id"])
        preview = self.workspace.mail_bulk_preview(**options)
        batch = self.workspace.mail_bulk_create("Bewerbungen", preview["preview_id"])["batch"]
        self.assertEqual(batch["items"][0]["source_snapshot"]["filename"], "Bewerbungen.xlsx")
        self.workspace.open(str(self.root / "project"))
        reopened = self.workspace.mail_bulk_batch(batch["id"])
        self.assertEqual(reopened["items"][0]["source_snapshot"]["effective_values"]["company.name"], "Neu")
        self.assertEqual(self.workspace.snapshot()["counts"]["mail_drafts"], 2)

    def test_manual_rows_html_overrides_and_individual_files(self):
        version = MailTemplateService(self.db).save(name="HTML", subject="{{company.name}}", body="<p>{{application.cover_letter}}</p>", body_format="html")
        items = []
        for i in range(2):
            path = self.root / f"cv{i}.txt"
            path.write_text(f"CV {i}", encoding="utf-8")
            items.append({"contact_id": f"manual:{i}", "source": {"kind": "manual", "fields": {
                "contact.display_name": f"Person {i}", "contact.email": f"m{i}@example.test", "company.name": f"Firma {i}",
                "application.cover_letter": "<Zeile>"}}, "attachments": [{"path": str(path)}]})
        items[1]["values"] = {"company.name": "Persönlich"}
        preview = self.workspace.mail_bulk_preview(version_id=version["id"], items=items)
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["rows"][1]["subject"], "Persönlich")
        self.assertEqual(preview["rows"][0]["body"], "<p>&lt;Zeile&gt;</p>")
        result = self.workspace.mail_bulk_create("Manuell", preview["preview_id"])
        for i, entry in enumerate(result["batch"]["items"]):
            self.assertIsNone(entry["contact_id"])
            draft = MailService(self.project).draft(entry["draft_id"])
            self.assertEqual(draft["configuration"]["attachments"][0]["filename"], f"cv{i}.txt")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)

    def test_same_excel_values_generate_personalized_docx_attachments_atomically(self):
        _, rows, _ = self.import_excel()
        version = self.document_template()
        options = {**self.options(rows), "document_version_id": version["id"]}
        preview = self.workspace.mail_bulk_preview(**options)
        self.assertTrue(preview["ready"], preview["rows"])
        self.assertIn("Kontakt 0 bei Firma 0: Anschreiben 0", preview["rows"][0]["generated_document"]["text"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
        self.assertEqual(list((self.project.path / "tmp").iterdir()), [])
        batch = self.workspace.mail_bulk_create("Anschreiben", preview["preview_id"])["batch"]
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 2)
        for i, entry in enumerate(batch["items"]):
            draft = MailService(self.project).draft(entry["draft_id"])
            attachment = draft["configuration"]["attachments"][0]
            text = extract_docx_text(self.project.file_path(attachment["path"]))
            self.assertIn(f"Kontakt {i} bei Firma {i}: Anschreiben {i}", text)
            self.assertNotIn("{{", text)
            self.assertTrue(attachment["document_id"])
            with zipfile.ZipFile(self.project.file_path(attachment["path"])) as archive:
                self.assertIn(b"<w:b", archive.read("word/document.xml"))

    def test_document_missing_values_tamper_and_converter_preflight(self):
        _, rows, _ = self.import_excel()
        version = self.document_template()
        options = {**self.options(rows), "document_version_id": version["id"]}
        missing = self.service.preview(**options, document_mapping={"NAME": "does.not.exist"})
        self.assertFalse(missing["ready"])
        with patch("emailcenter.mail_bulk.find_libreoffice", return_value=None):
            pdf = self.service.preview(**options, document_format="pdf")
        self.assertFalse(pdf["ready"])
        self.assertIn("LibreOffice", pdf["rows"][0]["error"])
        path = self.project.file_path(version["file_path"])
        path.write_bytes(b"tampered")
        self.assertFalse(self.service.preview(**options)["ready"])
        self.assertEqual(self.service.batches(), [])

    def test_personalized_excel_applications_can_use_existing_approved_send_pipeline(self):
        from email import policy
        from email.parser import BytesParser
        from emailcenter.credentials import WindowsTokenStore
        from test_mail import FakeProvider, MemoryVault
        _, rows, _ = self.import_excel()
        version = self.document_template()
        provider = FakeProvider()
        mail = MailService(self.project, token_store=WindowsTokenStore(self.project.project_id, backend=MemoryVault()),
                           provider_factory=lambda account: provider)
        account = mail.register_account("sender@example.test", {"refresh_token": "fake"})
        preview = self.workspace.mail_bulk_preview(**self.options(rows), document_version_id=version["id"], provider_account_id=account["id"])
        batch = self.workspace.mail_bulk_create("Bewerbungen", preview["preview_id"])["batch"]
        self.assertEqual(provider.sent, [])
        for item in batch["items"]:
            job = mail.prepare_job(item["draft_id"])
            self.assertEqual(mail.approve_and_send(job["id"])["status"], "Sent")
        self.assertEqual(len(provider.sent), 2)
        for i, raw in enumerate(provider.sent):
            message = BytesParser(policy=policy.default).parsebytes(raw)
            self.assertEqual(message["To"], f"c{i}@example.test")
            self.assertIn(f"Anschreiben {i}", message.get_body(preferencelist=("plain",)).get_content())
            attachment = list(message.iter_attachments())[0]
            self.assertEqual(attachment.get_filename(), f"Anschreiben-Kontakt {i}.docx")
            path = self.root / f"sent{i}.docx"
            path.write_bytes(attachment.get_payload(decode=True))
            self.assertIn(f"Firma {i}: Anschreiben {i}", extract_docx_text(path))

    def test_generated_documents_and_files_rollback_on_second_recipient_failure(self):
        _, rows, _ = self.import_excel()
        version = self.document_template()
        preview = self.workspace.mail_bulk_preview(**self.options(rows), document_version_id=version["id"])
        self.db.execute("CREATE TRIGGER fail_letters BEFORE INSERT ON email_draft_batch_items WHEN NEW.name_snapshot='Kontakt 1' BEGIN SELECT RAISE(ABORT,'failure'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.workspace.mail_bulk_create("No partial", preview["preview_id"])
        for table in ("documents", "email_drafts", "email_draft_batches"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual([p for p in (self.project.path / "exports/mail/drafts").rglob("*") if p.is_file()], [])
        self.assertEqual(list((self.project.path / "tmp").iterdir()), [])

    def test_pdf_conversion_failure_cleans_everything_and_docx_text_is_explicit(self):
        _, rows, _ = self.import_excel()
        version = self.document_template()
        with patch("emailcenter.mail_bulk.find_libreoffice", return_value="fake"):
            preview = self.workspace.mail_bulk_preview(**self.options(rows), document_version_id=version["id"], document_format="pdf")
            with patch("emailcenter.document_service.convert_docx_to_pdf", side_effect=RuntimeError("Conversion failed")):
                with self.assertRaises(RuntimeError):
                    self.workspace.mail_bulk_create("PDF failed", preview["preview_id"])
        self.assertEqual(self.service.batches(), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
        result = self.workspace.mail_bulk_docx_text(str(self.root / "letter.docx"))
        self.assertIn("{{ANREDE}}", result["text"])
        with self.assertRaises(ValueError):
            self.workspace.mail_bulk_docx_text(str(self.root / "not.docx"))

    def test_malformed_mapping_missing_sources_and_manual_invalid_fields(self):
        _, rows, _ = self.import_excel()
        for mapping in ({}, {**self.mapping, "X": "not found"}, {**self.mapping, "X": []}):
            with self.assertRaises(ValueError):
                self.sources.select([rows[0]["id"]], mapping)
        for ids in ([], [rows[0]["id"]] * 2, ["missing"]):
            with self.assertRaises(ValueError):
                self.sources.select(ids, self.mapping)
        for fields in ({"bad key": "x"}, {"contact.email": 1}, {"contact.email": "a\x00b"}):
            with self.assertRaises(ValueError):
                self.sources.resolve({"kind": "manual", "fields": fields})
        result = self.service.preview(version_id=self.version["id"], items=[{"contact_id": "manual:empty",
            "source": {"kind": "manual", "fields": {"contact.display_name": "Name", "contact.email": ""}}}])
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
