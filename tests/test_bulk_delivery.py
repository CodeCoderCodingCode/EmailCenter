"""Group delivery uses a fake provider only; interruption and snapshots stay durable."""

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.application.workspace import WorkspaceService
from emailcenter.bulk_delivery import BulkDeliveryService
from emailcenter.credentials import WindowsTokenStore
from emailcenter.gmail import ProviderError
from emailcenter.mail_bulk import BulkMailService
from emailcenter.mail_service import MailService
from emailcenter.mail_templates import MailTemplateService
from test_mail import FakeProvider, MemoryVault


class BulkDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.root / "project"), "Dispatch")
        self.clock = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
        self.provider, self.vault = FakeProvider(), MemoryVault()
        self.make_service()
        self.account = self.mail.register_account(self.provider.email, {"refresh_token": "fake"})
        template = MailTemplateService(self.db).save(name="Bulk", subject="An {{contact.display_name}}", body="Hallo {{contact.display_name}}")
        contacts = [self.workspace.create_record("contacts", {"display_name": name, "email": name.lower() + "@example.test"}) for name in ("Ada", "Grace")]
        self.attachment = self.root / "Anhang.txt"
        self.attachment.write_text("Feste Datei", encoding="utf-8")
        options = {"version_id": template["id"], "items": [{"contact_id": c["id"]} for c in contacts],
                   "attachments": [{"path": str(self.attachment)}]}
        bulk = BulkMailService(self.workspace.project)
        self.batch = bulk.create(name="Testgruppe", expected_fingerprint=bulk.preview(**options)["fingerprint"], **options)["batch"]

    def make_service(self):
        project = self.workspace.project
        self.db = project.connection
        self.mail = MailService(project, token_store=WindowsTokenStore(project.project_id, backend=self.vault),
                                provider_factory=lambda account: self.provider, now=lambda: self.clock)
        self.service = BulkDeliveryService(project, mail=self.mail)

    def tearDown(self):
        self.workspace.close()
        self.temp.cleanup()

    def begin(self, **options):
        return self.service.begin(self.batch["id"], self.account["id"], **options)

    def ready(self, **options):
        result = self.begin(**options)
        for _ in self.batch["items"]:
            result = self.service.prepare_next(result["id"])
        self.assertEqual(result["status"], "Ready")
        return result

    def approved(self, **options):
        result = self.ready(**options)
        return self.service.approve(result["id"], result["fingerprint"])

    def running(self, **options):
        result = self.approved(**options)
        return self.service.start(result["id"], result["fingerprint"])

    def test_details_and_preparation_are_local_and_jobs_are_not_approved(self):
        self.assertIsNone(self.service.details(self.batch["id"])["dispatch"])
        with patch.object(self.mail, "_provider", side_effect=AssertionError("No provider before send")):
            value = self.ready()
        self.assertEqual([item["job"]["status"] for item in value["items"]], ["Draft", "Draft"])
        self.assertTrue(all(item["job"]["approval_status"] == "pending" for item in value["items"]))
        self.assertTrue(all(item["job"]["batch_id"] == self.batch["id"] for item in value["items"]))
        self.assertEqual(self.provider.sent, [])
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])

    def test_partial_preparation_resumes_without_duplicate_jobs_or_files(self):
        value = self.begin()
        value = self.service.prepare_next(value["id"])
        first_id = value["items"][0]["job_id"]
        self.db.execute("CREATE TRIGGER fail_dispatch BEFORE UPDATE OF job_id ON email_bulk_dispatch_items WHEN NEW.position=1 BEGIN SELECT RAISE(ABORT,'failure'); END")
        value = self.service.prepare_next(value["id"])
        self.assertEqual(value["status"], "Preparing")
        self.assertIn("failure", value["last_error"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 1)
        files = [p for p in (self.root / "project/exports/mail/jobs").rglob("*") if p.is_file()]
        self.assertEqual(len(files), 2)
        self.db.execute("DROP TRIGGER fail_dispatch")
        value = self.service.prepare_next(value["id"])
        self.assertEqual(value["status"], "Ready")
        self.assertEqual(value["items"][0]["job_id"], first_id)
        self.assertEqual(self.service.prepare_next(value["id"])["fingerprint"], value["fingerprint"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 2)
        with self.assertRaisesRegex(ValueError, "bereits"):
            self.begin()

    def test_common_approval_rolls_back_if_any_payload_or_attachment_changed(self):
        value = self.ready()
        job = value["items"][1]["job"]
        self.workspace.project.file_path(job["attachments"][0]["file_path_snapshot"]).write_text("tampered")
        with self.assertRaises(ValueError):
            self.service.approve(value["id"], value["fingerprint"])
        value = self.service.snapshot(value["id"])
        self.assertEqual(value["status"], "Ready")
        self.assertTrue(all(item["job"]["approval_status"] == "pending" for item in value["items"]))
        self.assertTrue(all(item["job"]["status"] == "Draft" for item in value["items"]))

    def test_stale_review_or_account_changes_block_approval_and_start(self):
        value = self.ready()
        self.mail.cancel(value["items"][0]["job_id"])
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.service.approve(value["id"], value["fingerprint"])
        value = self.service.snapshot(value["id"])
        value = self.service.approve(value["id"], value["fingerprint"])
        self.db.execute("UPDATE email_provider_accounts SET is_enabled=0 WHERE id=?", (self.account["id"],))
        with self.assertRaisesRegex(ValueError, "Gmail"):
            self.service.start(value["id"], value["fingerprint"])
        self.assertEqual(self.provider.sent, [])

    def test_pause_resume_and_interval_do_not_resend_sent_jobs(self):
        value = self.running(interval_seconds=5)
        value = self.service.next(value["id"])
        self.assertEqual(value["counts"]["sent"], 1)
        wait = self.service.next(value["id"])
        self.assertIn("wait_until", wait)
        value = self.service.pause(value["id"])
        self.clock += timedelta(seconds=10)
        self.assertEqual(self.service.next(value["id"])["counts"]["sent"], 1)
        value = self.service.start(value["id"], value["fingerprint"])
        value = self.service.next(value["id"])
        self.assertEqual(value["status"], "Completed")
        self.assertEqual(len(self.provider.sent), 2)
        self.service.next(value["id"])
        self.assertEqual(len(self.provider.sent), 2)
        messages = [BytesParser(policy=policy.default).parsebytes(raw) for raw in self.provider.sent]
        self.assertEqual([message["To"] for message in messages], ["ada@example.test", "grace@example.test"])
        self.assertEqual([message.get_body().get_content().strip() for message in messages], ["Hallo Ada", "Hallo Grace"])
        self.assertEqual(list(messages[0].iter_attachments())[0].get_payload(decode=True), b"Feste Datei")

    def test_shared_scheduler_and_individual_send_cannot_bypass_group_control(self):
        value = self.approved(scheduled_local="2026-10-12T15:00:00")
        self.clock += timedelta(hours=2)
        self.assertEqual(self.mail.process_due(), [])
        with self.assertRaisesRegex(ValueError, "Gruppe"):
            self.mail.send_job(value["items"][0]["job_id"])
        value = self.service.start(value["id"], value["fingerprint"])
        with self.assertRaises(ValueError):
            self.mail.send_job(value["items"][0]["job_id"], send_now=True)
        self.assertEqual(self.mail.process_due(), [])
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.service.next(value["id"])["counts"]["sent"], 1)

    def test_planned_group_waits_for_schedule_before_first_send(self):
        value = self.running(scheduled_local="2026-10-12T15:00:00", timezone_id="Europe/Berlin")
        value = self.service.next(value["id"])
        self.assertEqual(value["wait_until"], "2026-10-12T13:00:00Z")
        self.assertEqual(self.provider.sent, [])
        self.clock += timedelta(hours=1)
        self.assertEqual(self.service.next(value["id"])["counts"]["sent"], 1)

    def test_cancel_preserves_sent_and_stops_all_remaining(self):
        value = self.running()
        value = self.service.next(value["id"])
        value = self.service.cancel(value["id"])
        self.assertEqual(value["status"], "Cancelled")
        self.assertEqual([item["job"]["status"] for item in value["items"]], ["Sent", "Cancelled"])
        self.assertEqual(self.service.cancel(value["id"])["fingerprint"], value["fingerprint"])
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])
        self.clock += timedelta(hours=1)
        self.service.next(value["id"])
        self.assertEqual(len(self.provider.sent), 1)

    def test_cancel_during_partial_preparation_leaves_no_new_jobs(self):
        value = self.begin()
        value = self.service.prepare_next(value["id"])
        value = self.service.cancel(value["id"])
        self.assertEqual(value["counts"]["prepared"], 1)
        self.assertEqual(value["counts"]["cancelled"], 1)
        self.service.prepare_next(value["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 1)

    def test_uncertain_send_stops_group_and_reconciliation_does_not_repeat_it(self):
        value = self.running()
        self.provider.failure = ProviderError("timeout", uncertain=True)
        value = self.service.next(value["id"])
        self.assertEqual(value["status"], "Paused")
        self.assertEqual(value["items"][0]["job"]["status"], "Uncertain")
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])
        job = value["items"][0]["job"]
        value = self.service.item_action(value["id"], job["id"], "reconcile")
        self.assertEqual(value["items"][0]["job"]["status"], "ReconciliationRequired")
        self.provider.matches = [{"id": "confirmed", "message_id": job["message_id_snapshot"]}]
        value = self.service.item_action(value["id"], job["id"], "reconcile")
        self.provider.failure = None
        self.clock += timedelta(seconds=3)
        value = self.service.start(value["id"], value["fingerprint"])
        self.assertEqual(self.service.next(value["id"])["status"], "Completed")
        self.assertEqual(len(self.provider.sent), 2)  # one uncertain POST, one different recipient

    def test_definitive_failure_requires_explicit_item_retry_with_same_identity(self):
        value = self.running()
        self.provider.failure = ProviderError("rejected", uncertain=False)
        value = self.service.next(value["id"])
        job = value["items"][0]["job"]
        self.assertEqual(job["status"], "Failed")
        with self.assertRaises(ValueError):
            self.service.approve(value["id"], value["fingerprint"])
        value = self.service.item_action(value["id"], job["id"], "retry")
        value = self.service.approve(value["id"], value["fingerprint"])
        self.provider.failure = None
        self.clock += timedelta(seconds=3)
        value = self.service.start(value["id"], value["fingerprint"])
        value = self.service.next(value["id"])
        self.assertEqual(value["items"][0]["job"]["message_id_snapshot"], job["message_id_snapshot"])
        self.assertEqual(value["items"][0]["job"]["attempt_count"], 2)
        self.assertEqual(self.provider.sent[0], self.provider.sent[1])

    def test_preflight_failure_revokes_approval_without_recording_a_post(self):
        value = self.running()
        self.provider.email = "different@example.test"
        value = self.service.next(value["id"])
        self.assertEqual(value["status"], "Paused")
        job = value["items"][0]["job"]
        self.assertEqual(job["approval_status"], "pending")
        self.assertEqual(job["attempt_count"], 0)
        self.assertEqual(self.provider.sent, [])
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])

    def test_reopen_requires_new_approval_and_never_resends_finished_jobs(self):
        value = self.running()
        value = self.service.next(value["id"])
        identifier = value["id"]
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        self.make_service()
        value = self.service.snapshot(identifier)
        self.assertEqual(value["status"], "Paused")
        self.assertEqual(value["counts"]["sent"], 1)
        with self.assertRaises(ValueError):
            self.service.start(identifier, value["fingerprint"])
        with self.assertRaisesRegex(ValueError, "Überfälligen"):
            self.service.approve(identifier, value["fingerprint"])
        value = self.service.approve(identifier, value["fingerprint"], confirm_overdue=True)
        self.clock += timedelta(seconds=3)
        value = self.service.start(identifier, value["fingerprint"])
        self.assertEqual(self.service.next(identifier)["status"], "Completed")
        self.assertEqual(len(self.provider.sent), 2)

    def test_crash_during_sending_recovers_uncertain_job_and_paused_group(self):
        value = self.running()
        job = value["items"][0]["job"]
        self.db.execute("UPDATE email_jobs SET status='Sending',attempt_count=1 WHERE id=?", (job["id"],))
        self.db.execute("INSERT INTO email_attempts(id,email_job_id,attempt_number,started_at_utc,result) VALUES('interrupted',?,1,?,'Started')", (job["id"], self.mail._timestamp()))
        self.mail.recover()
        value = self.service.snapshot(value["id"])
        self.assertEqual(value["status"], "Paused")
        self.assertEqual(value["items"][0]["job"]["status"], "ReconciliationRequired")
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])
        self.assertEqual(self.provider.sent, [])

    def test_draft_and_original_attachment_edits_do_not_change_prepared_payloads(self):
        value = self.ready()
        job = value["items"][0]["job"]
        self.mail.save_draft(draft_id=job["draft_id"], subject="Neue Version", body="Anders", recipients_value={"to": ["changed@example.test"]})
        self.attachment.write_text("Changed", encoding="utf-8")
        value = self.service.approve(value["id"], value["fingerprint"])
        value = self.service.start(value["id"], value["fingerprint"])
        self.service.next(value["id"])
        message = BytesParser(policy=policy.default).parsebytes(self.provider.sent[0])
        self.assertEqual(message["To"], "ada@example.test")
        self.assertEqual(message["Subject"], "An Ada")
        self.assertEqual(list(message.iter_attachments())[0].get_payload(decode=True), b"Feste Datei")

    def test_bulk_requires_one_unique_recipient_and_valid_interval_account_and_schedule(self):
        for interval in (0, 3601, True, "2"):
            with self.assertRaises(ValueError):
                self.begin(interval_seconds=interval)
        with self.assertRaises(ValueError):
            self.service.begin(self.batch["id"], "missing")
        with self.assertRaises(ValueError):
            self.begin(scheduled_local="2020-01-01T00:00:00")
        for targets in ({"to": ["a@example.test", "b@example.test"]}, {"to": ["a@example.test"], "bcc": ["hidden@example.test"]}):
            self.mail.save_draft(draft_id=self.batch["items"][0]["draft_id"], subject="Test", body="Hi", recipients_value=targets)
            with self.assertRaisesRegex(ValueError, "genau einen"):
                self.begin()
        for item in self.batch["items"]:
            self.mail.save_draft(draft_id=item["draft_id"], subject="Test", body="Hi", recipients_value={"to": ["same@example.test"]})
        with self.assertRaisesRegex(ValueError, "Doppelte"):
            self.begin()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_bulk_dispatches").fetchone()[0], 0)

    def test_item_actions_cannot_touch_another_group_or_running_dispatch(self):
        value = self.running()
        job_id = value["items"][0]["job_id"]
        with self.assertRaises(ValueError):
            self.service.item_action(value["id"], job_id, "cancel")
        value = self.service.pause(value["id"])
        with self.assertRaises(ValueError):
            self.service.item_action(value["id"], "unrelated", "reconcile")
        with self.assertRaises(ValueError):
            self.service.item_action(value["id"], job_id, "send")
        value = self.service.item_action(value["id"], job_id, "cancel")
        self.assertEqual(value["counts"]["cancelled"], 1)

    def test_job_link_failure_does_not_leave_an_orphaned_job_or_payload(self):
        value = self.begin()
        self.db.execute("CREATE TRIGGER fail_dispatch BEFORE UPDATE OF job_id ON email_bulk_dispatch_items BEGIN SELECT RAISE(ABORT,'link failure'); END")
        value = self.service.prepare_next(value["id"])
        self.assertEqual(value["counts"]["prepared"], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
        self.assertEqual([p for p in (self.root / "project/exports/mail/jobs").rglob("*") if p.is_file()], [])

    def test_long_gap_requires_explicit_overdue_review_of_remaining_due_jobs(self):
        value = self.running()
        value = self.service.next(value["id"])
        value = self.service.pause(value["id"], require_review=True)
        self.assertEqual(value["counts"]["sent"], 1)
        self.assertEqual(value["items"][1]["job"]["requires_overdue_confirmation"], 1)
        with self.assertRaises(ValueError):
            self.service.start(value["id"], value["fingerprint"])
        with self.assertRaises(ValueError):
            self.service.approve(value["id"], value["fingerprint"])
        value = self.service.approve(value["id"], value["fingerprint"], confirm_overdue=True)
        self.clock += timedelta(seconds=3)
        value = self.service.start(value["id"], value["fingerprint"])
        self.assertEqual(self.service.next(value["id"])["status"], "Completed")

    def test_stopping_last_pending_item_completes_group_with_its_results(self):
        value = self.running()
        value = self.service.next(value["id"])
        value = self.service.pause(value["id"])
        value = self.service.item_action(value["id"], value["items"][1]["job_id"], "cancel")
        self.assertEqual(value["status"], "Completed")
        self.assertEqual(value["counts"]["sent"], 1)
        self.assertEqual(value["counts"]["cancelled"], 1)
        self.assertEqual(self.service.cancel(value["id"])["status"], "Completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
