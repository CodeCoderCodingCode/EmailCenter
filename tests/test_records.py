"""Record editing, optimistic concurrency and relationship integrity."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.workspace = WorkspaceService()
        self.workspace.create(str(Path(self.temporary.name) / "project"), "Records")
        self.company = self.create("companies", name="Example GmbH")

    def tearDown(self):
        self.workspace.close()
        self.temporary.cleanup()

    def create(self, entity, **fields):
        return self.workspace.create_record(entity, fields)

    def edit(self, entity, record_id, **fields):
        details = self.workspace.record_details(entity, record_id)
        return self.workspace.update_record(entity=entity, record_id=record_id, fields=fields, expected_version=details["version"])

    def link(self, entity, record_id, contact_id, **fields):
        details = self.workspace.record_links(entity=entity, record_id=record_id)
        return self.workspace.save_record_link(entity=entity, record_id=record_id, contact_id=contact_id,
                                               expected_version=details["version"], **fields)

    def test_all_record_types_can_be_edited_without_losing_hidden_fields(self):
        cases = [("companies", self.company, "name"),
                 ("contacts", self.create("contacts", display_name="Ada", notes="Existing"), "display_name"),
                 ("applicants", self.create("applicants", display_name="Ada"), "display_name"),
                 ("jobs", self.create("jobs", title="Engineer", company_id=self.company["id"]), "title"),
                 ("applications", self.create("applications", title="Engineer"), "title")]
        for entity, record, name_key in cases:
            with self.subTest(entity=entity):
                original = self.workspace.record_details(entity, record["id"])["record"]
                updated = self.edit(entity, record["id"], **{name_key: "Updated"})
                self.assertEqual(updated[name_key], "Updated")
                for key in original.keys() - {name_key, "updated_at"}:
                    self.assertEqual(updated[key], original[key])
        events = self.workspace.project.connection.execute("SELECT COUNT(*) FROM activity_log WHERE event_type='record.updated'").fetchone()[0]
        self.assertEqual(events, 5)

    def test_same_second_stale_update_is_rejected(self):
        old = self.workspace.record_details("companies", self.company["id"])
        self.edit("companies", self.company["id"], name="First editor")
        with self.assertRaisesRegex(ValueError, "zwischenzeitlich"):
            self.workspace.update_record("companies", self.company["id"], {"name": "Stale editor"}, old["version"])
        self.assertEqual(self.workspace.record_details("companies", self.company["id"])["record"]["name"], "First editor")

    def test_uneditable_fields_empty_names_and_unknown_entities_are_rejected(self):
        application = self.create("applications", title="Engineer")
        for fields in ({"status_id": "bad"}, {"status_code": "sent"}, {"deleted_at": "now"}, {"id": "new"}, {"title": " "}, {"title": 42}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.edit("applications", application["id"], **fields)
        with self.assertRaises(ValueError):
            self.workspace.record_details("companies; DROP TABLE contacts", "x")
        with self.assertRaises(ValueError):
            self.workspace.record_details("unknown")
        with self.assertRaises(ValueError):
            self.workspace.record_details("companies", "missing")

    def test_job_application_company_consistency_and_reassignment(self):
        other = self.create("companies", name="Other GmbH")
        job = self.create("jobs", title="Engineer", company_id=self.company["id"])
        application = self.create("applications", title="Candidate", job_posting_id=job["id"])
        self.assertEqual(application["company_id"], self.company["id"])
        with self.assertRaises(ValueError):
            self.edit("applications", application["id"], company_id=other["id"])
        with self.assertRaises(ValueError):
            self.edit("jobs", job["id"], company_id=other["id"])
        self.edit("applications", application["id"], job_posting_id=None, company_id=other["id"])
        self.assertEqual(self.edit("jobs", job["id"], company_id=other["id"])["company_id"], other["id"])
        with self.assertRaises(ValueError):
            self.create("applications", title="Wrong", company_id=self.company["id"], job_posting_id=job["id"])

    def test_dates_and_archived_references(self):
        job = self.create("jobs", title="Engineer", company_id=self.company["id"])
        with self.assertRaises(ValueError):
            self.create("jobs", title="Engineer", company_id=self.company["id"], deadline="2026-02-30")
        with self.assertRaises(ValueError):
            self.create("applications", title="Engineer", next_follow_up_at="2026-10-20T09:00")
        app = self.create("applications", title="Engineer", company_id=self.company["id"],
                          application_date="2026-10-11", next_follow_up_at="2026-10-20T09:00:00+02:00")
        self.workspace.project.connection.execute("UPDATE companies SET deleted_at='now' WHERE id=?", (self.company["id"],))
        self.assertEqual(self.edit("applications", app["id"], title="Updated")["company_id"], self.company["id"])
        with self.assertRaises(ValueError):
            self.create("jobs", title="Engineer", company_id=self.company["id"])
        with self.assertRaises(ValueError):
            self.create("applications", title="Engineer", job_posting_id=job["id"])
        with self.assertRaises(ValueError):
            self.edit("companies", self.company["id"], name="Archived")

    def test_job_and_profile_lists_search_pagination_and_counts(self):
        self.create("jobs", title="Engineer 100%", company_id=self.company["id"], location="Berlin")
        self.create("jobs", title="Other", company_id=self.company["id"])
        self.create("applicants", display_name="Ada", email="ada@example.test")
        self.assertEqual(self.workspace.list_records("jobs", search="%")["total"], 1)
        self.assertEqual(self.workspace.list_records("jobs", search="Berlin")["total"], 1)
        self.assertEqual(len(self.workspace.list_records("jobs", limit=1)["rows"]), 1)
        self.assertEqual(self.workspace.list_records("applicants", search="ada@example")["total"], 1)
        self.assertEqual(self.workspace.snapshot()["counts"]["jobs"], 2)
        self.assertEqual(self.workspace.snapshot()["counts"]["applicants"], 1)

    def test_link_upsert_primary_contact_and_unlink_preserve_records(self):
        ada = self.create("contacts", display_name="Ada")
        grace = self.create("contacts", display_name="Grace")
        self.link("companies", self.company["id"], ada["id"], is_primary=True, relationship_type="HR")
        updated = self.link("companies", self.company["id"], ada["id"], is_primary=True, relationship_type="Recruiting")
        self.assertEqual(len(updated["rows"]), 1)
        self.link("companies", self.company["id"], grace["id"], is_primary=True)
        rows = self.workspace.record_links("companies", self.company["id"])["rows"]
        self.assertEqual([r["id"] for r in rows if r["is_primary"]], [grace["id"]])
        application = self.create("applications", title="Candidate")
        self.link("applications", application["id"], ada["id"], relationship_type="Recruiting")
        self.link("applications", application["id"], ada["id"], relationship_type="Hiring manager")
        self.assertEqual(self.workspace.record_links("applications", application["id"])["rows"][0]["relationship_type"], "Hiring manager")
        result = self.link("applications", application["id"], ada["id"], remove=True)
        self.assertEqual(result["rows"], [])
        self.assertEqual(self.workspace.snapshot()["counts"]["contacts"], 2)

    def test_invalid_and_stale_link_changes_roll_back(self):
        ada = self.create("contacts", display_name="Ada")
        original = self.link("companies", self.company["id"], ada["id"], is_primary=True)
        with self.assertRaises(ValueError):
            self.link("companies", self.company["id"], "missing", is_primary=True)
        with self.assertRaises(ValueError):
            self.link("companies", self.company["id"], ada["id"], remove="false")
        self.assertEqual(self.workspace.record_links("companies", self.company["id"])["rows"][0]["is_primary"], 1)
        self.link("companies", self.company["id"], ada["id"], relationship_type="New role")
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.workspace.save_record_link("companies", self.company["id"], ada["id"], expected_version=original["version"], remove=True)
        self.workspace.project.connection.execute("UPDATE contacts SET deleted_at='now' WHERE id=?", (ada["id"],))
        self.assertIsNotNone(self.workspace.record_links("companies", self.company["id"])["rows"][0]["deleted_at"])
        self.assertEqual(self.link("companies", self.company["id"], ada["id"], remove=True)["rows"], [])

    def test_activity_failure_rolls_back_record_and_link_updates(self):
        connection = self.workspace.project.connection
        contact = self.create("contacts", display_name="Ada")
        connection.execute("CREATE TRIGGER fail_activity BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
        with self.assertRaises(Exception):
            self.edit("companies", self.company["id"], name="Unsaved")
        self.assertEqual(self.workspace.record_details("companies", self.company["id"])["record"]["name"], "Example GmbH")
        with self.assertRaises(Exception):
            self.link("companies", self.company["id"], contact["id"])
        self.assertEqual(self.workspace.record_links("companies", self.company["id"])["rows"], [])

    def test_noop_edit_does_not_add_activity_or_change_custom_data(self):
        connection = self.workspace.project.connection
        connection.execute("UPDATE companies SET custom_fields_json=?,address_json=? WHERE id=?", ('{"legacy":"value"}', '{"city":"Berlin"}', self.company["id"]))
        before = self.workspace.record_details("companies", self.company["id"])["record"]
        count = connection.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        self.assertEqual(self.edit("companies", self.company["id"]), before)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0], count)
