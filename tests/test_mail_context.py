"""Mail context suggestions never create drafts or send messages."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.database import DocumentRepository, DocumentSetRepository, utc_timestamp


class MailContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.workspace = WorkspaceService()
        self.workspace.create(str(Path(self.temporary.name) / "project"), "Context")
        self.db = self.workspace.project.connection
        self.company = self.record("companies", name="Example GmbH")
        self.applicant = self.record("applicants", display_name="Ada", email="applicant@example.test")
        self.job = self.record("jobs", title="Entwicklerin", reference_number="DEV-42", company_id=self.company["id"])
        self.application = self.record("applications", title="Meine Bewerbung", company_id=self.company["id"],
                                       applicant_profile_id=self.applicant["id"], job_posting_id=self.job["id"])

    def tearDown(self):
        self.workspace.close()
        self.temporary.cleanup()

    def record(self, entity, **fields):
        return self.workspace.create_record(entity, fields)

    def link(self, entity, record, contact, **options):
        version = self.workspace.record_links(entity, record["id"])["version"]
        self.workspace.save_record_link(entity, record["id"], contact["id"], expected_version=version, **options)

    def context(self, **options):
        return self.workspace.execute("mail_context_details", options or {"application_id": self.application["id"]})

    def document(self, name, application=None, *, via_set=False):
        application = application or self.application
        path = self.workspace.project.file_path("documents/" + name)
        content = b"test attachment"
        path.write_bytes(content)
        document = DocumentRepository(self.db).create(file_path="documents/" + name,
            original_filename=name, file_size_bytes=len(content), file_hash=hashlib.sha256(content).hexdigest(),
            template_version_id=None, document_type="application_document", application_id=application["id"],
            file_format="pdf" if name.endswith(".pdf") else "docx")
        if via_set:
            document_set = DocumentSetRepository(self.db).create("Set", application_id=application["id"])
            self.db.execute("UPDATE documents SET application_id=NULL,document_set_id=? WHERE id=?",
                            (document_set["id"], document["id"]))
        return document

    def test_application_contacts_precede_company_primary_and_profile_is_not_recipient(self):
        recruiter = self.record("contacts", display_name="Grace", email="grace@example.test")
        company_contact = self.record("contacts", display_name="General", email="general@example.test")
        self.link("companies", self.company, company_contact, is_primary=True)
        self.link("applications", self.application, recruiter)
        context = self.context()
        self.assertEqual(context["recipients"]["to"], ["grace@example.test"])
        self.assertEqual(context["subject"], "Bewerbung: Entwicklerin (Referenz: DEV-42)")
        self.assertIn("Guten Tag Grace", context["body"])
        self.assertEqual([c["id"] for c in context["candidates"]], [recruiter["id"]])
        self.assertNotIn("applicant@example.test", context["body"])

    def test_multiple_contacts_require_choice_and_documents_belong_to_selected_application(self):
        for name in ("Grace", "Linus"):
            self.link("applications", self.application, self.record("contacts", display_name=name, email=name.lower()+"@example.test"))
        own = self.document("letter.docx")
        own_pdf = self.document("letter.pdf", via_set=True)
        deleted = self.document("old.docx")
        self.db.execute("UPDATE documents SET deleted_at=? WHERE id=?", (utc_timestamp(), deleted["id"]))
        other_application = self.record("applications", title="Other", company_id=self.company["id"])
        other = self.document("other.docx", other_application)
        context = self.context()
        self.assertEqual(context["recipients"]["to"], [])
        self.assertIsNone(context["selected_contact_id"])
        self.assertTrue(any("Mehrere" in text for text in context["warnings"]))
        self.assertEqual({d["id"] for d in context["documents"]}, {own["id"], own_pdf["id"]})
        self.assertNotIn(other["id"], {d["id"] for d in context["documents"]})
        selected = self.context(application_id=self.application["id"], contact_id=context["candidates"][1]["id"])
        self.assertEqual(selected["recipients"]["to"], [context["candidates"][1]["email"]])

    def test_company_fallback_uses_primary_and_filters_archived_contacts(self):
        for name in ("Grace", "Linus"):
            contact = self.record("contacts", display_name=name, email=name.lower()+"@example.test")
            self.link("companies", self.company, contact, is_primary=name == "Linus")
        context = self.context()
        self.assertEqual(context["recipients"]["to"], ["linus@example.test"])
        self.db.execute("UPDATE contacts SET deleted_at=? WHERE id=?", (utc_timestamp(), contact["id"]))
        self.assertEqual(self.context()["recipients"]["to"], ["grace@example.test"])

    def test_invalid_application_contact_requires_manual_recipient_without_silent_company_fallback(self):
        self.link("applications", self.application, self.record("contacts", display_name="Missing", email="invalid"))
        self.link("companies", self.company, self.record("contacts", display_name="Other", email="other@example.test"), is_primary=True)
        context = self.context()
        self.assertEqual(context["recipients"]["to"], [])
        self.assertEqual(context["candidates"], [])
        self.assertTrue(any("Missing" in text for text in context["warnings"]))

    def test_contact_suggestions_normalize_subject_and_allow_missing_email(self):
        contact = self.record("contacts", display_name="Grace\nBcc: injected", email="bad\r\naddress@example.test")
        context = self.context(contact_id=contact["id"])
        self.assertEqual(context["application_id"], None)
        self.assertEqual(context["subject"], "Nachricht an Grace Bcc: injected")
        self.assertEqual(context["recipients"]["to"], [])
        self.assertTrue(context["warnings"])
        self.assertEqual(context["documents"], [])

    def test_missing_archived_and_unrelated_records_are_rejected(self):
        unrelated = self.record("contacts", display_name="Unrelated", email="other@example.test")
        for options in ({"application_id": "missing"}, {"contact_id": "missing"},
                        {"application_id": self.application["id"], "contact_id": unrelated["id"]}):
            with self.assertRaises(ValueError):
                self.context(**options)
        self.db.execute("UPDATE contacts SET deleted_at=? WHERE id=?", (utc_timestamp(), unrelated["id"]))
        with self.assertRaises(ValueError):
            self.context(contact_id=unrelated["id"])
        self.db.execute("UPDATE applications SET deleted_at=? WHERE id=?", (utc_timestamp(), self.application["id"]))
        with self.assertRaises(ValueError):
            self.context()
        with self.assertRaises(ValueError):
            self.workspace.mail_context_details()

    def test_compose_context_is_read_only_and_existing_drafts_are_not_overwritten(self):
        draft = self.workspace.mail_save_draft(subject="Unchanged", body="Original", recipients_value={"to": ["original@example.test"]})
        before = self.db.total_changes
        files = set(self.workspace.project.path.rglob("*"))
        details = self.workspace.mail_compose_details(application_id=self.application["id"])
        self.assertIsNone(details["draft"])
        self.assertEqual(details["context"]["application_id"], self.application["id"])
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(set(self.workspace.project.path.rglob("*")), files)
        self.assertEqual(self.workspace.mail_compose_details(draft_id=draft["id"])["draft"]["body"], "Original")
        with self.assertRaises(ValueError):
            self.workspace.mail_compose_details(draft_id=draft["id"], application_id=self.application["id"])


if __name__ == "__main__":
    unittest.main()
