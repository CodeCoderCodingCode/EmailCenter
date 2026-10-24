"""Reminder persistence, offsets, DST boundaries and atomic lifecycle tests."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.reminder_service import ReminderService, local_reminder_time


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.workspace = WorkspaceService()
        self.path = str(Path(self.temporary.name) / "project")
        self.workspace.create(self.path, "Reminders")
        self.service = ReminderService(self.workspace.project.connection, clock=lambda: datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc))

    def tearDown(self):
        self.workspace.close()
        self.temporary.cleanup()

    def create(self, title="Call HR", due="2026-10-11T11:00:00+02:00", **fields):
        return self.service.save(title=title, due_at_utc=due, **fields)

    def test_create_normalizes_utc_and_survives_reopen(self):
        record = self.create(description="Line one\nLine two")
        self.assertEqual(record["due_at_utc"], "2026-10-11T09:00:00Z")
        self.assertEqual(self.service.summary(), {"due": 1, "pending": 1})
        self.workspace.close()
        self.workspace.open(self.path)
        self.assertEqual(self.workspace.reminder_details(record_id=record["id"])["record"], record)

    def test_application_followups_do_not_create_duplicate_reminder_rows(self):
        app = self.workspace.create_record("applications", {"title": "Engineer", "next_follow_up_at": "2026-10-11T11:00:00+02:00"})
        rows = self.service.list()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "application")
        self.assertEqual(rows[0]["record_id"], app["id"])
        self.assertEqual(rows[0]["due_label"], "11.10.2026 11:00 CEST")
        self.assertEqual(self.workspace.project.connection.execute("SELECT COUNT(*) FROM reminders").fetchone()[0], 0)
        self.service.finish("application", app["id"], rows[0]["version"])
        self.assertEqual(self.service.summary()["pending"], 0)
        self.assertIsNone(self.workspace.record_details("applications", app["id"])["record"]["next_follow_up_at"])
        self.assertEqual(self.workspace.project.connection.execute("SELECT COUNT(*) FROM activity_log WHERE event_type='followup.completed'").fetchone()[0], 1)

    def test_explicit_reminder_statuses_history_and_double_completion_guard(self):
        for status in ("Completed", "Dismissed", "Cancelled"):
            record = self.create(title=status)
            details = self.service.details(record_id=record["id"])
            self.service.finish("reminder", record["id"], details["version"], status=status)
            updated = self.service.details(record_id=record["id"])["record"]
            self.assertEqual(updated["status"], status)
            self.assertEqual(updated["completed_at_utc"] is not None, status == "Completed")
            with self.assertRaises(ValueError):
                self.service.finish("reminder", record["id"], details["version"])
        self.assertEqual(self.service.list(view="due")["total"], 0)
        self.assertEqual(self.service.list(view="history")["total"], 3)

    def test_reschedule_edit_conflict_and_no_implicit_changes_to_application(self):
        app = self.workspace.create_record("applications", {"title": "Engineer"})
        record = self.create(application_id=app["id"])
        old = self.service.details(record_id=record["id"])
        updated = self.service.save(title="Call manager", due_at_utc="2026-10-20T09:00:00Z", application_id=app["id"],
                                    record_id=record["id"], expected_version=old["version"], description="Notes")
        self.assertEqual(updated["description"], "Notes")
        self.assertEqual(self.service.summary(), {"due": 0, "pending": 1})
        self.assertIsNone(self.workspace.record_details("applications", app["id"])["record"]["next_follow_up_at"])
        with self.assertRaisesRegex(ValueError, "zwischenzeitlich"):
            self.service.finish("reminder", record["id"], old["version"])

    def test_followup_reschedule_updates_same_application(self):
        app = self.workspace.create_record("applications", {"title": "Engineer", "notes": "Preserved", "next_follow_up_at": "2026-10-11T09:00:00Z"})
        details = self.service.details("application", app["id"])
        updated = self.service.save(source="application", record_id=app["id"], expected_version=details["version"],
                                    title=app["title"], due_at_utc="2026-10-20T09:00:00Z")
        self.assertEqual(updated["next_follow_up_at"], "2026-10-20T09:00:00Z")
        self.assertEqual(updated["notes"], "Preserved")
        self.assertEqual(self.service.list(view="due")["total"], 0)

    def test_closed_and_archived_applications_suppress_automatic_followups(self):
        app = self.workspace.create_record("applications", {"title": "Engineer", "next_follow_up_at": "2026-10-11T09:00:00Z"})
        self.create(title="Explicit task", application_id=app["id"])
        old = next(row for row in self.service.list()["rows"] if row["source"] == "application")
        self.workspace.change_status(app["id"], "accepted")
        rows = self.service.list()["rows"]
        self.assertEqual([row["title"] for row in rows], ["Explicit task"])
        with self.assertRaises(ValueError):
            self.service.finish("application", app["id"], old["version"])
        self.workspace.project.connection.execute("UPDATE applications SET deleted_at='now' WHERE id=?", (app["id"],))
        self.assertEqual(self.service.list()["total"], 1)
        with self.assertRaises(ValueError):
            self.create(application_id=app["id"])

    def test_invalid_values_are_rejected(self):
        for changes in ({"title": " "}, {"due_at_utc": "2026-10-11T10:00"}, {"due_at_utc": "invalid"},
                        {"timezone_id": "Unknown/Place"}, {"application_id": "missing"}, {"description": 17}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.save(**{ "title": "Call", "due_at_utc": "2026-10-11T10:00:00Z", **changes})
        for changes in ({"view": "unknown"}, {"limit": 0}, {"offset": -1}, {"timezone_id": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.list(**changes)

    def test_offset_comparison_search_and_page_clamping(self):
        self.create(title="100%", due="2026-10-11T12:00:00+02:00")
        self.create(title="1000", due="2026-10-11T09:30:00Z")
        self.create(title="_value", due="2026-10-11T15:00:00+02:00")
        rows = self.service.list()["rows"]
        self.assertEqual([row["title"] for row in rows], ["1000", "100%"])
        self.assertEqual(self.service.list(view="pending", search="%")["total"], 1)
        self.assertEqual(self.service.list(view="pending", search="_")["total"], 1)
        self.assertEqual(self.service.list(view="pending", search="' OR 1=1 --")["total"], 0)
        last = self.service.list(offset=1, limit=1)["rows"][0]
        self.service.finish(last["source"], last["record_id"], last["version"])
        self.assertEqual(self.service.list(offset=1, limit=1)["offset"], 0)

    def test_dst_nonexistent_and_ambiguous_local_time(self):
        with self.assertRaises(ValueError):
            local_reminder_time("2026-03-29T02:30:00", "Europe/Berlin")
        with self.assertRaises(ValueError):
            local_reminder_time("2026-03-29T02:30:00", "Europe/Berlin", 0)
        with self.assertRaisesRegex(ValueError, "doppeldeutig"):
            local_reminder_time("2026-10-25T02:30:00", "Europe/Berlin")
        self.assertEqual(local_reminder_time("2026-10-25T02:30:00", "Europe/Berlin", 0), "2026-10-25T00:30:00Z")
        self.assertEqual(local_reminder_time("2026-10-25T02:30:00", "Europe/Berlin", 1), "2026-10-25T01:30:00Z")

    def test_today_filter_uses_local_day_on_dst_change(self):
        self.service.clock = lambda: datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
        for title, due in (("start", "2026-10-24T22:00:00Z"), ("first", "2026-10-25T00:30:00Z"),
                           ("second", "2026-10-25T01:30:00Z"), ("end", "2026-10-25T22:59:59Z"), ("tomorrow", "2026-10-25T23:00:00Z")):
            self.create(title=title, due=due)
        self.assertEqual(self.service.list(view="today")["total"], 4)

    def test_display_timezone_changes_today_filter_without_changing_instants(self):
        self.service.clock = lambda: datetime(2026, 10, 11, 23, 30, tzinfo=timezone.utc)
        app = self.workspace.create_record("applications", {"title": "Engineer", "next_follow_up_at": "2026-10-11T10:00:00Z"})
        self.assertEqual(self.service.list(view="today", timezone_id="UTC")["total"], 1)
        self.assertEqual(self.service.list(view="today", timezone_id="Europe/Berlin")["total"], 0)
        row = self.service.list(view="pending", timezone_id="Asia/Tokyo")["rows"][0]
        self.assertEqual(row["due_label"], "11.10.2026 19:00 JST")
        self.assertEqual(self.workspace.record_details("applications", app["id"])["record"]["next_follow_up_at"], "2026-10-11T10:00:00Z")

    def test_invalid_imported_followup_is_visible_for_repair(self):
        app = self.workspace.create_record("applications", {"title": "Legacy"})
        self.workspace.project.connection.execute("UPDATE applications SET next_follow_up_at='2026-10-20T09:00' WHERE id=?", (app["id"],))
        row = self.service.list()["rows"][0]
        self.assertEqual(row["status_label"], "Termin / Zeitzone prüfen")
        details = self.service.details("application", app["id"])
        self.service.save(source="application", record_id=app["id"], expected_version=details["version"],
                          title="Legacy", due_at_utc="2026-10-20T09:00:00Z")
        self.assertEqual(self.service.list()["total"], 0)

    def test_activity_failure_rolls_back_save_and_finish(self):
        record = self.create()
        details = self.service.details(record_id=record["id"])
        self.workspace.project.connection.execute("CREATE TRIGGER fail_reminder_activity BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(Exception):
            self.create(title="Unsaved")
        with self.assertRaises(Exception):
            self.service.finish("reminder", record["id"], details["version"])
        self.assertEqual(self.service.details(record_id=record["id"])["record"]["status"], "Pending")
        self.assertEqual(self.service.list()["total"], 1)
