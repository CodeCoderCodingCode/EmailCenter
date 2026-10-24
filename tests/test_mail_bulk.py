"""Bulk staging never invokes Gmail; previews, replay and file rollback are tested locally."""

import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.mail_bulk import BulkMailService
from emailcenter.mail_service import MailService
from emailcenter.mail_templates import MailTemplateService


class BulkMailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.root / "project"), "Bulk")
        self.db = self.workspace.project.connection
        self.service = BulkMailService(self.workspace.project)
        self.version = MailTemplateService(self.db).save(name="Persönlich", subject="An {{contact.display_name}}",
                                                       body="Hallo {{contact.display_name}}, {{NOTE}}")
        self.contacts = [self.workspace.create_record("contacts", {"display_name": name, "email": email}) for name, email in
                         (("Ada", "ada@example.test"), ("Grace", "grace@example.test"))]
        self.options = {"version_id": self.version["id"], "items": [
            {"contact_id": c["id"], "values": {"NOTE": "Gruß " + c["display_name"]}} for c in self.contacts]}

    def tearDown(self):
        self.workspace.close()
        self.temp.cleanup()

    def test_preview_is_read_only_and_personalized(self):
        with patch.object(MailService, "_provider", side_effect=AssertionError("No provider calls")):
            result = self.service.preview(**self.options)
        self.assertTrue(result["ready"])
        self.assertEqual([r["subject"] for r in result["rows"]], ["An Ada", "An Grace"])
        self.assertEqual([r["body"] for r in result["rows"]], ["Hallo Ada, Gruß Ada", "Hallo Grace, Gruß Grace"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)
        self.assertEqual(self.service.batches(), [])

    def test_invalid_duplicate_and_missing_values_block_whole_group(self):
        invalid = self.workspace.create_record("contacts", {"display_name": "No address"})
        duplicate = self.workspace.create_record("contacts", {"display_name": "Duplicate", "email": "ADA@example.test"})
        options = {**self.options, "items": self.options["items"] + [{"contact_id": invalid["id"]},
                   {"contact_id": duplicate["id"], "values": {"NOTE": "Duplicate"}}]}
        result = self.service.preview(**options)
        self.assertFalse(result["ready"])
        self.assertIn("Doppelte", result["rows"][0]["error"])
        self.assertTrue(result["rows"][2]["error"])
        with self.assertRaises(ValueError):
            self.service.create(name="No", expected_fingerprint=result["fingerprint"], **options)
        missing = self.service.preview(version_id=self.version["id"], items=[{"contact_id": self.contacts[0]["id"]}])
        self.assertEqual(missing["rows"][0]["missing"], ["NOTE"])
        self.assertFalse(missing["ready"])
        self.assertEqual(self.service.batches(), [])
        details = self.service.details()
        self.assertTrue(next(c for c in details["contacts"] if c["id"] == self.contacts[0]["id"])["duplicate"])

    def test_limits_archive_and_unknown_inputs(self):
        for items in ([], [{"contact_id": "x"}] * 101, [self.options["items"][0]] * 2, [{"contact_id": "x", "other": 1}]):
            with self.assertRaises(ValueError):
                self.service.preview(version_id=self.version["id"], items=items)
        with self.assertRaises(ValueError):
            self.service.preview(**self.options, attachments={"path": "x"})
        self.db.execute("UPDATE contacts SET deleted_at='now' WHERE id=?", (self.contacts[0]["id"],))
        self.db.commit()
        self.assertFalse(self.service.preview(**self.options)["ready"])
        self.assertEqual(len(self.service.details()["contacts"]), 1)

    def test_atomic_creation_snapshot_attachments_and_reopen(self):
        attachment = self.root / "note.txt"
        attachment.write_text("Original", encoding="utf-8")
        options = {**self.options, "attachments": [{"path": str(attachment)}]}
        preview = self.workspace.mail_bulk_preview(**options)
        with patch.object(MailService, "_provider", side_effect=AssertionError("No provider calls")):
            result = self.workspace.mail_bulk_create("Grüße", preview["preview_id"])
        self.assertEqual(len(result["batch"]["items"]), 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
        attachment.write_text("Changed", encoding="utf-8")
        drafts = [MailService(self.workspace.project).draft(i["draft_id"]) for i in result["batch"]["items"]]
        for draft in drafts:
            self.assertEqual(len(draft["recipients"]["to"]), 1)
            self.assertEqual(draft["recipients"]["bcc"], [])
            self.assertIsNone(draft["provider_account_id"])
            self.assertEqual(self.workspace.project.file_path(draft["configuration"]["attachments"][0]["path"]).read_text(), "Original")
        self.assertNotEqual(drafts[0]["configuration"]["attachments"][0]["path"], drafts[1]["configuration"]["attachments"][0]["path"])
        with self.assertRaises(ValueError):
            self.workspace.mail_bulk_create("Replay", preview["preview_id"])
        batch_id = result["batch"]["id"]
        self.workspace.open(str(self.root / "project"))
        self.assertEqual(len(self.workspace.mail_bulk_batch(batch_id)["items"]), 2)
        self.assertEqual(self.workspace.mail_bulk_details()["batches"][0]["name"], "Grüße")

    def test_stale_contact_file_signature_and_version_require_new_preview(self):
        preview = self.workspace.mail_bulk_preview(**self.options)
        self.db.execute("UPDATE contacts SET email='new@example.test' WHERE id=?", (self.contacts[0]["id"],))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.workspace.mail_bulk_create("Stale", preview["preview_id"])
        attachment = self.root / "note.txt"
        attachment.write_text("one", encoding="utf-8")
        preview = self.workspace.mail_bulk_preview(**self.options, attachments=[{"path": str(attachment)}])
        attachment.write_text("two", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.workspace.mail_bulk_create("Stale", preview["preview_id"])
        signature = MailService(self.workspace.project).save_signature("Gruß", "Original")
        preview = self.workspace.mail_bulk_preview(**self.options, signature_id=signature)
        self.assertIn("Original", preview["rows"][0]["preview_body"])
        MailService(self.workspace.project).save_signature("Gruß", "Neu", signature_id=signature)
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.workspace.mail_bulk_create("Stale", preview["preview_id"])
        self.assertEqual(self.service.batches(), [])

    def test_database_failure_rolls_back_group_drafts_and_copied_files(self):
        attachment = self.root / "note.txt"
        attachment.write_text("data", encoding="utf-8")
        preview = self.workspace.mail_bulk_preview(**self.options, attachments=[{"path": str(attachment)}])
        self.db.execute("CREATE TRIGGER fail_bulk BEFORE INSERT ON email_draft_batch_items WHEN NEW.name_snapshot='Grace' BEGIN SELECT RAISE(ABORT,'failure'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.workspace.mail_bulk_create("Fail", preview["preview_id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)
        self.assertEqual(self.service.batches(), [])
        self.assertEqual([p for p in (self.root / "project/exports/mail/drafts").rglob("*") if p.is_file()], [])
        self.db.execute("DROP TRIGGER fail_bulk")
        self.db.commit()
        self.assertEqual(len(self.workspace.mail_bulk_create("Retry", preview["preview_id"])["batch"]["items"]), 2)

    def test_copy_race_and_missing_file_never_leave_partial_group(self):
        attachment = self.root / "note.txt"
        attachment.write_text("before", encoding="utf-8")
        options = {**self.options, "attachments": [{"path": str(attachment)}]}
        preview = self.service.preview(**options)
        original = self.service.mail._copy_attachments
        def changed(*args):
            attachment.write_text("after", encoding="utf-8")
            return original(*args)
        with patch.object(self.service.mail, "_copy_attachments", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "geändert"):
                self.service.create(name="Race", expected_fingerprint=preview["fingerprint"], **options)
        self.assertEqual(self.service.batches(), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)
        self.assertEqual([p for p in (self.root / "project/exports/mail/drafts").rglob("*") if p.is_file()], [])
        attachment.unlink()
        self.assertFalse(self.service.preview(**options)["ready"])

    def test_application_membership_html_and_project_change(self):
        company = self.workspace.create_record("companies", {"name": "Company"})
        profile = self.workspace.create_record("applicants", {"display_name": "Me"})
        application = self.workspace.create_record("applications", {"title": "Job", "company_id": company["id"], "applicant_profile_id": profile["id"]})
        links = self.workspace.record_links("applications", application["id"])
        self.workspace.save_record_link("applications", application["id"], self.contacts[0]["id"], expected_version=links["version"])
        version = MailTemplateService(self.db).save(name="HTML", subject="{{application.title}}", body="<p>{{NOTE}}</p>", body_format="html")
        result = self.service.preview(version_id=version["id"], items=[
            {"contact_id": c["id"], "application_id": application["id"], "values": {"NOTE": "<image>"}} for c in self.contacts])
        self.assertFalse(result["ready"])
        self.assertEqual(result["rows"][0]["body"], "<p>&lt;image&gt;</p>")
        self.assertTrue(result["rows"][1]["error"])
        result = self.service.preview(version_id=version["id"], items=[{
            "contact_id": self.contacts[0]["id"], "application_id": application["id"], "values": {"NOTE": "ok"}, "documents": ["unrelated"]}])
        self.assertFalse(result["ready"])
        preview = self.workspace.mail_bulk_preview(**self.options)
        self.workspace.open(str(self.root / "project"))
        with self.assertRaises(ValueError):
            self.workspace.mail_bulk_create("Wrong project", preview["preview_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
