"""Mail template versions, rendering and persistence without live mail."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.database import TemplateRepository, utc_timestamp
from emailcenter.mail_templates import MailTemplateService


class MailTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.temporary.name) / "project"
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.path), "Templates")
        self.db = self.workspace.project.connection
        self.service = MailTemplateService(self.db)

    def tearDown(self):
        self.workspace.close()
        self.temporary.cleanup()

    def save(self, **options):
        return self.service.save(**{"name": "Bewerbung", "subject": "An {{company.name}}", "body": "Hallo {{NAME}}", **options})

    def fixture(self):
        create = self.workspace.create_record
        company = create("companies", {"name": "Example & Partner"})
        applicant = create("applicants", {"display_name": "Ada", "email": "ada@example.test"})
        job = create("jobs", {"title": "Entwicklerin", "reference_number": "DEV-42", "company_id": company["id"]})
        application = create("applications", {"title": "Meine Bewerbung", "company_id": company["id"],
            "applicant_profile_id": applicant["id"], "job_posting_id": job["id"]})
        contact = create("contacts", {"display_name": "Grace <HR>", "email": "grace@example.test"})
        links = self.workspace.record_links("applications", application["id"])
        self.workspace.save_record_link("applications", application["id"], contact["id"], expected_version=links["version"])
        return application, contact

    def test_versions_duplicate_and_reopen_preserve_old_content(self):
        first = self.save()
        second = self.save(template_id=first["template_id"], base_version_id=first["id"], body="Neue Nachricht")
        self.assertEqual(second["version_number"], 2)
        self.assertEqual(self.service.version(first["id"])["body"], "Hallo {{NAME}}")
        copy = self.service.duplicate(first["id"])
        self.assertNotEqual(copy["template_id"], first["template_id"])
        self.assertEqual(copy["body"], first["body"])
        self.assertEqual(copy["version_number"], 1)
        self.workspace.open(str(self.path))
        self.service = MailTemplateService(self.workspace.project.connection)
        details = self.service.details(first["template_id"])
        self.assertEqual([v["version_number"] for v in details["versions"]], [2, 1])
        self.assertEqual(details["latest_version_id"], second["id"])

    def test_search_pagination_and_document_templates_are_separate(self):
        TemplateRepository(self.db).create("DOCX only")
        for name in ("100%", "1000", "_Name", "Other"):
            self.save(name=name)
        self.assertEqual([row["name"] for row in self.service.list(search="%")["rows"]], ["100%"])
        self.assertEqual(self.service.list(search="_")["total"], 1)
        self.assertEqual(self.service.list(search="' OR 1=1 --")["total"], 0)
        first, second = self.service.list(limit=2), self.service.list(limit=2, offset=2)
        self.assertEqual(first["total"], 4)
        self.assertFalse({r["id"] for r in first["rows"]} & {r["id"] for r in second["rows"]})
        self.assertEqual(len(self.service.choices()), 4)
        with self.assertRaises(ValueError):
            self.service.list(limit=0)

    def test_render_uses_explicit_context_and_escapes_html_values(self):
        application, contact = self.fixture()
        version = self.save(subject="{{job.title}} – {{company.name}}", body_format="html",
            body="<p>Guten Tag {{contact.display_name}},</p><p>{{applicant.display_name}} · {{job.reference_number}}</p>")
        missing = self.service.render(version["id"], application_id=application["id"])
        self.assertEqual(missing["missing"], ["contact.display_name"])
        rendered = self.service.render(version["id"], application_id=application["id"], contact_id=contact["id"])
        self.assertEqual(rendered["missing"], [])
        self.assertEqual(rendered["subject"], "Entwicklerin – Example & Partner")
        self.assertIn("Grace &lt;HR&gt;", rendered["body"])
        self.assertIn("Ada · DEV-42", rendered["body"])
        unrelated = self.workspace.create_record("contacts", {"display_name": "Other", "email": "other@example.test"})
        with self.assertRaises(ValueError):
            self.service.render(version["id"], application_id=application["id"], contact_id=unrelated["id"])

    def test_missing_custom_values_and_replacements_are_not_recursive(self):
        version = self.save(subject="Betreff", body="Hallo {{NAME}}. {{NOTE}}")
        result = self.service.render(version["id"])
        self.assertEqual(result["missing"], ["NAME", "NOTE"])
        result = self.service.render(version["id"], values={"NAME": "Ada", "NOTE": "Wörtlich {{NAME}}"})
        self.assertEqual(result["body"], "Hallo Ada. Wörtlich {{NAME}}")
        self.assertEqual(result["missing"], [])
        for values in ({"UNKNOWN": "x"}, {"NAME": 123}, {"NAME": "x" * 10001}):
            with self.assertRaises(ValueError):
                self.service.render(version["id"], values=values)

    def test_invalid_templates_and_rendered_headers_are_rejected(self):
        for options in ({"name": ""}, {"subject": "Injected\nBcc:"}, {"body": ""}, {"body_format": "markdown"},
                        {"body": "{{call()}}"}, {"body": "{{NAME}"}, {"body": "x" * 100001}):
            with self.assertRaises(ValueError):
                self.save(**options)
        self.assertEqual(self.service.list()["total"], 0)
        version = self.save(subject="{{NAME}}", body="Text")
        for value in ("Line\nHeader", "x" * 999):
            with self.assertRaises(ValueError):
                self.service.render(version["id"], values={"NAME": value})

    def test_conflict_and_document_type_cannot_overwrite_existing_version(self):
        first = self.save()
        latest = self.save(template_id=first["template_id"], base_version_id=first["id"], body="Latest")
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.save(template_id=first["template_id"], base_version_id=first["id"], body="Stale")
        self.assertEqual(self.service.details(first["template_id"])["latest_version_id"], latest["id"])
        document = TemplateRepository(self.db).create("DOCX")
        with self.assertRaises(ValueError):
            self.save(template_id=document["id"], base_version_id="invalid")
        self.assertEqual(self.db.execute("SELECT template_type FROM templates WHERE id=?", (document["id"],)).fetchone()[0], "document")

    def test_activity_failure_rolls_back_new_template_and_updated_version(self):
        original = self.save()
        self.db.execute("CREATE TRIGGER reject_template_log BEFORE INSERT ON activity_log "
                        "WHEN NEW.event_type='email_template.saved' BEGIN SELECT RAISE(ABORT,'log failed'); END")
        for options in ({"name": "New"}, {"name": "Changed", "template_id": original["template_id"], "base_version_id": original["id"]}):
            with self.assertRaises(Exception):
                self.save(**options)
        self.assertEqual(self.service.list()["total"], 1)
        self.assertEqual(len(self.service.choices()), 1)
        self.assertEqual(self.service.version(original["id"])["name"], "Bewerbung")

    def test_tampered_and_archived_versions_are_rejected(self):
        version = self.save()
        self.db.execute("UPDATE template_versions SET content_text='Tampered' WHERE id=?", (version["id"],))
        with self.assertRaisesRegex(ValueError, "verändert"):
            self.service.render(version["id"])
        self.db.execute("UPDATE templates SET deleted_at=? WHERE id=?", (utc_timestamp(), version["template_id"]))
        self.assertEqual(self.service.choices(), [])
        with self.assertRaises(ValueError):
            self.service.version(version["id"])

    def test_template_changes_do_not_modify_drafts_or_prepared_jobs(self):
        from emailcenter.credentials import WindowsTokenStore
        from emailcenter.mail_service import MailService
        from test_mail import FakeProvider, MemoryVault
        provider = FakeProvider()
        service = MailService(self.workspace.project,
            token_store=WindowsTokenStore(self.workspace.project.project_id, backend=MemoryVault()),
            provider_factory=lambda account: provider)
        account = service.register_account(provider.email, {"refresh_token": "fake"})
        version = self.save(subject="Old", body="Old body")
        before = self.db.total_changes
        rendered = self.workspace.execute("mail_template_render", {"version_id": version["id"]})
        self.assertEqual(self.db.total_changes, before)
        draft = service.save_draft(subject=rendered["subject"], body=rendered["body"],
            recipients_value={"to": ["target@example.test"]}, provider_account_id=account["id"])
        job = service.prepare_job(draft["id"])
        self.save(template_id=version["template_id"], base_version_id=version["id"], subject="New", body="New body")
        self.assertEqual(service.draft(draft["id"])["body"], "Old body")
        self.assertEqual(service.job(job["id"])["body_snapshot"], "Old body")
        self.assertEqual(provider.sent, [])


if __name__ == "__main__":
    unittest.main()
