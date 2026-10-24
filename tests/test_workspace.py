"""Integration tests for desktop use cases without a Qt event loop."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from test_documents import _make_docx


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.directory = Path(self.temporary.name)
        self.workspace = WorkspaceService()
        self.workspace.execute("create_project", {"path": str(self.directory / "project"), "name": "Desktop test"})

    def tearDown(self):
        self.workspace.close()
        self.temporary.cleanup()

    def test_paginated_search_is_literal_and_parameterized(self):
        for name in ("Example 100%", "Example 1000", "Other", "Example _field"):
            self.workspace.create_record("companies", {"name": name})
        result = self.workspace.list_records("companies", search="%")
        self.assertEqual([row["name"] for row in result["rows"]], ["Example 100%"])
        self.assertEqual(self.workspace.list_records("companies", search="_")["total"], 1)
        self.assertEqual(self.workspace.list_records("companies", search="' OR 1=1 --")["total"], 0)
        first = self.workspace.list_records("companies", limit=2)
        second = self.workspace.list_records("companies", offset=2, limit=2)
        self.assertEqual(first["total"], 4)
        self.assertFalse({r["id"] for r in first["rows"]} & {r["id"] for r in second["rows"]})
        with self.assertRaises(ValueError):
            self.workspace.list_records("companies; DROP TABLE contacts")

    def test_failed_project_open_preserves_previous_project(self):
        with self.assertRaises(Exception):
            self.workspace.open(str(self.directory / "missing"))
        self.assertEqual(self.workspace.snapshot()["name"], "Desktop test")
        self.workspace.create_record("contacts", {"display_name": "Grace"})
        self.assertEqual(self.workspace.snapshot()["counts"]["contacts"], 1)

    def test_project_setup_mode_goal_and_old_project_defaults(self):
        snapshot = self.workspace.create(str(self.directory / "mail-project"), "Aufträge", "mail", "  Angebote senden  ")
        self.assertEqual(snapshot["workspace_mode"], "mail")
        self.assertEqual(snapshot["project_goal"], "Angebote senden")
        self.assertEqual(snapshot["recent_mail_jobs"], [])
        self.workspace.set_workspace_mode("applications")
        self.workspace.open(str(self.directory / "mail-project"))
        self.assertEqual(self.workspace.snapshot()["workspace_mode"], "applications")
        self.workspace.project.connection.execute("DELETE FROM project_metadata WHERE key IN ('workspace_mode','project_goal')")
        self.assertEqual(self.workspace.snapshot()["workspace_mode"], "applications")
        self.assertEqual(self.workspace.snapshot()["project_goal"], "")

    def test_invalid_project_setup_does_not_create_folder_or_replace_project(self):
        for mode, goal in (("unsupported", ""), ("mail", "a" * 4001)):
            with self.assertRaises(Exception):
                self.workspace.create(str(self.directory / "invalid"), "Invalid", mode, goal)
            self.assertFalse((self.directory / "invalid").exists())
            self.assertEqual(self.workspace.snapshot()["name"], "Desktop test")
        with self.assertRaises(ValueError):
            self.workspace.set_workspace_mode("unsupported")
        self.assertEqual(self.workspace.snapshot()["workspace_mode"], "applications")

    def test_initial_record_failure_preserves_open_project(self):
        old = self.workspace.project
        with self.assertRaises(Exception):
            self.workspace.create(str(self.directory / "invalid"), "Invalid",
                                  initial_profile={"display_name": "Ada", "email": "invalid"})
        self.assertIs(self.workspace.project, old)
        self.assertFalse(old.is_closed)
        self.assertFalse((self.directory / "invalid").exists())
        self.workspace.create_record("contacts", {"display_name": "Still writable"})

    def test_desktop_application_values_generation_and_preview(self):
        company = self.workspace.create_record("companies", {"name": "Example GmbH"})
        applicant = self.workspace.create_record("applicants", {"display_name": "Ada", "email": "ada@example.test"})
        application = self.workspace.create_record("applications", {
            "title": "Engineer", "company_id": company["id"], "applicant_profile_id": applicant["id"],
        })
        source = self.directory / "template.docx"
        _make_docx(source)
        imported = self.workspace.import_template(
            str(source), "Letter", {"NAME": "applicant.display_name", "COMPANY": "company.name"}, ["NAME"],
        )
        version_id = imported["version"]["id"]
        values = self.workspace.document_values(version_id, application["id"])["values"]
        self.assertEqual(values, {"NAME": "Ada", "COMPANY": "Example GmbH"})
        preview = self.workspace.preview_document(version_id, values)
        self.assertIn("{{NA", preview["before"])
        self.assertIn("Ada", preview["after"])
        self.assertEqual(self.workspace.snapshot()["counts"]["documents"], 0)
        self.assertTrue(list((self.workspace.project.path / "tmp").iterdir()))
        self.workspace.release_preview()
        self.assertEqual(list((self.workspace.project.path / "tmp").iterdir()), [])
        generated = self.workspace.generate_document(template_version_id=version_id, values=values,
                                                     output_filename="Letter.docx", application_id=application["id"])
        self.assertTrue(Path(generated["path"]).is_file())
        listing = self.workspace.list_records("documents")
        self.assertEqual(listing["rows"][0]["application_title"], "Engineer")
        self.assertEqual(self.workspace.document_path(generated["document"]["id"])["path"], generated["path"])

    def test_closing_releases_preview_and_project(self):
        source = self.directory / "template.docx"
        _make_docx(source)
        imported = self.workspace.import_template(str(source), "Preview", {}, [])
        self.workspace.preview_document(imported["version"]["id"], {})
        project_path = self.workspace.project.path
        self.workspace.close()
        self.assertEqual(list((project_path / "tmp").iterdir()), [])
        self.assertIsNone(self.workspace.project)
        with self.assertRaisesRegex(ValueError, "Projekt"):
            self.workspace.snapshot()

    def test_status_and_backup_use_cases(self):
        application = self.workspace.create_record("applications", {"title": "Engineer"})
        self.workspace.change_status(application["id"], "interview")
        self.assertEqual(self.workspace.list_records("applications")["rows"][0]["status_code"], "interview")
        backup = self.workspace.backup()
        self.assertTrue(Path(backup).is_file())

    def test_unknown_actions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unbekannte Aktion"):
            self.workspace.execute("__dict__", {})

    def test_workspace_draft_details_and_pagination_without_network(self):
        drafts = []
        for index in range(4):
            drafts.append(self.workspace.mail_save_draft(subject=f"Entwurf {index}", body="Nachricht",
                recipients_value={"to": ["target@example.test"]}))
        first = self.workspace.execute("workspace_mail_snapshot", {"limit": 2})
        second = self.workspace.execute("workspace_mail_snapshot", {"limit": 2, "draft_offset": 2})
        self.assertEqual(first["draft_total"], 4)
        self.assertFalse({row["id"] for row in first["drafts"]} & {row["id"] for row in second["drafts"]})
        details = self.workspace.execute("mail_compose_details", {"draft_id": drafts[0]["id"]})
        self.assertEqual(details["draft"]["subject"], "Entwurf 0")
        self.assertIn("documents", details["snapshot"])
        self.assertIsNone(self.workspace.execute("mail_compose_details", {})["draft"])
        with self.assertRaises(Exception):
            self.workspace.execute("mail_compose_details", {"draft_id": "missing"})


if __name__ == "__main__":
    unittest.main()
