"""Tests for the application domain repositories and status history."""

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.database import (  # noqa: E402
    ApplicationRepository,
    ApplicationStatusRepository,
    CompanyRepository,
    ContactRepository,
    JobPostingRepository,
    apply_migrations,
    connect,
)

MIGRATIONS = ROOT / "migrations"


class ApplicationDomainTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        apply_migrations(self.db, MIGRATIONS)
        self.companies = CompanyRepository(self.db)
        self.contacts = ContactRepository(self.db)
        self.jobs = JobPostingRepository(self.db)
        self.statuses = ApplicationStatusRepository(self.db)
        self.applications = ApplicationRepository(self.db)
        self.company = self.companies.create("Example GmbH")
        self.contact = self.contacts.create("Ada Example", email="ada@example.test")

    def tearDown(self):
        self.db.close()

    def test_application_can_be_created_for_company_and_job(self):
        job = self.jobs.create(str(self.company["id"]), "Python Developer")
        application = self.applications.create(
            "Python Developer at Example GmbH",
            job_posting_id=str(job["id"]),
            custom_fields={"remote": True, "level": "senior"},
        )
        self.assertEqual(application["company_id"], self.company["id"])
        self.assertEqual(application["job_posting_id"], job["id"])
        self.assertEqual(application["status_code"], "draft")
        self.assertEqual(application["custom_fields_json"], '{"level": "senior", "remote": true}')

    def test_application_rejects_mismatched_company_and_job(self):
        other_company = self.companies.create("Other GmbH")
        job = self.jobs.create(str(self.company["id"]), "Engineer")
        with self.assertRaisesRegex(ValueError, "must match"):
            self.applications.create(
                "Engineer application",
                company_id=str(other_company["id"]),
                job_posting_id=str(job["id"]),
            )

    def test_contacts_can_be_linked_to_companies_and_applications(self):
        self.companies.link_contact(
            str(self.company["id"]), str(self.contact["id"]),
            relationship_type="recruiter", is_primary=True,
        )
        application = self.applications.create(
            "Engineer", company_id=str(self.company["id"])
        )
        self.applications.link_contact(
            str(application["id"]), str(self.contact["id"]),
            relationship_type="hiring_manager",
        )
        self.assertEqual(
            self.companies.list_contacts(str(self.company["id"]))[0]["relationship_type"],
            "recruiter",
        )
        self.assertEqual(
            self.applications.list_contacts(str(application["id"]))[0]["relationship_type"],
            "hiring_manager",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.applications.link_contact(str(application["id"]), "unknown-contact")

    def test_status_changes_are_logged_and_terminal_statuses_cannot_change(self):
        application = self.applications.create("Engineer")
        application_id = str(application["id"])
        self.assertEqual(self.applications.change_status(application_id, "sent")["status_code"], "sent")
        self.assertEqual(self.applications.change_status(application_id, "sent")["status_code"], "sent")
        self.applications.change_status(application_id, "rejected")
        with self.assertRaisesRegex(ValueError, "terminal status"):
            self.applications.change_status(application_id, "accepted")

        activity = self.db.execute(
            "SELECT event_type, details_json FROM activity_log "
            "WHERE entity_id = ? ORDER BY created_at, event_type",
            (application_id,),
        ).fetchall()
        self.assertEqual(len(activity), 3)
        self.assertEqual(
            [row[0] for row in activity].count("application.status_changed"), 2
        )
        self.assertTrue(any('"to": "rejected"' in row[1] for row in activity))

    def test_custom_statuses_are_configurable_and_can_be_used(self):
        status = self.statuses.create("waiting_for_reply", "Warten auf Rückmeldung", sort_order=25)
        self.assertEqual(status["is_system"], 0)
        self.statuses.rename("waiting_for_reply", "Rückmeldung ausstehend")
        application = self.applications.create("Engineer")
        updated = self.applications.change_status(str(application["id"]), "waiting_for_reply")
        self.assertEqual(updated["status_label"], "Rückmeldung ausstehend")

    def test_invalid_status_and_json_values_are_rejected(self):
        with self.assertRaises(KeyError):
            self.applications.create("Engineer", status_code="does_not_exist")
        with self.assertRaises(ValueError):
            self.applications.create("Engineer", custom_fields={"bad": object()})
        with self.assertRaises(ValueError):
            self.applications.create("Engineer", custom_fields=[])  # type: ignore[arg-type]

    def test_foreign_key_failure_rolls_back_application_and_activity(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.applications.create("Engineer", company_id="missing-company")
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 0
        )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
