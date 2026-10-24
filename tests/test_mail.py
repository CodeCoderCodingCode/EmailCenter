"""No live mail: state machine, MIME, OAuth vault and Gmail transport doubles."""

import base64
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.credentials import WindowsTokenStore
from emailcenter.gmail import API_ROOT, GmailProvider, ProviderError, SCOPES, authorize_desktop
from emailcenter.mail_models import MailError, recipients, schedule_time
from emailcenter.mail_service import MailService
from emailcenter.project import create_project, open_project


class MemoryVault:
    def __init__(self):
        self.values = {}
        self.fail = False

    def get_password(self, service, user):
        return self.values.get((service, user))

    def set_password(self, service, user, value):
        if self.fail and service.endswith("head"):
            raise RuntimeError("fake-secret-must-not-leak")
        if len(value.encode("utf-16-le")) > 2560:
            raise RuntimeError("blob too large")
        self.values[service, user] = value

    def delete_password(self, service, user):
        self.values.pop((service, user), None)


class FakeProvider:
    def __init__(self):
        self.sent = []
        self.drafts = []
        self.matches = []
        self.failure = None
        self.email = "sender@example.test"

    def profile(self):
        return self.email

    def send(self, raw):
        self.sent.append(raw)
        if self.failure:
            raise self.failure
        return "gmail123"

    def save_draft(self, raw, draft_id=None):
        self.drafts.append((raw, draft_id))
        return "draft123"

    def find_sent(self, message_id):
        return self.matches


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.folder = Path(self.temporary.name)
        self.project = create_project(self.folder / "project")
        self.vault = MemoryVault()
        self.tokens = WindowsTokenStore(self.project.project_id, backend=self.vault)
        self.provider = FakeProvider()
        self.clock = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
        self.service = self.make_service()
        self.account = self.service.register_account(self.provider.email, {"refresh_token": "fake-token"})

    def make_service(self):
        return MailService(self.project, token_store=self.tokens, provider_factory=lambda account: self.provider, now=lambda: self.clock)

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def draft(self, **options):
        values = {"provider_account_id": self.account["id"], "subject": "Bewerbung – Entwickler",
                  "body": "Guten Tag,\nmeine Bewerbung.", "recipients_value": {"to": ["target@example.test"]}}
        values.update(options)
        return self.service.save_draft(**values)

    def prepared(self, **options):
        return self.service.prepare_job(self.draft()["id"], **options)

    def approved(self):
        return self.service.approve(self.prepared()["id"])

    def test_snapshot_and_mime_survive_draft_signature_attachment_changes(self):
        attachment = self.folder / "Lebenslauf.txt"
        attachment.write_text("Original", encoding="utf-8")
        signature = self.service.save_signature("Privat", "Mit freundlichen Grüßen\nAda")
        draft = self.draft(signature_id=signature, recipients_value={"to": ["to@example.test"], "cc": ["cc@example.test"], "bcc": ["bcc@example.test"]}, attachments=[{"path": str(attachment)}])
        job = self.service.prepare_job(draft["id"])
        self.service.save_signature("Privat", "Neue Signatur", signature_id=signature)
        attachment.write_text("Changed", encoding="utf-8")
        self.draft(draft_id=draft["id"], subject="Changed", body="Changed")
        self.assertEqual(job["body_snapshot"], "Guten Tag,\nmeine Bewerbung.\n\nMit freundlichen Grüßen\nAda")
        self.service.approve(job["id"])
        result = self.service.send_job(job["id"])
        mime = BytesParser(policy=policy.default).parsebytes(self.provider.sent[0])
        self.assertEqual(mime["Message-ID"], job["message_id_snapshot"])
        self.assertEqual(str(mime["Subject"]), job["subject_snapshot"])
        self.assertEqual(str(mime["Bcc"]), "bcc@example.test")
        self.assertEqual(next(mime.iter_attachments()).get_payload(decode=True), b"Original")
        self.assertEqual(result["status"], "Sent")
        self.assertEqual(result["attempt_count"], 1)

    def test_send_requires_approval_and_does_not_create_an_attempt(self):
        job = self.prepared()
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])
        self.assertEqual(self.provider.sent, [])
        self.assertEqual(self.service.job(job["id"])["attempts"], [])

    def test_draft_saved_before_login_can_choose_sender_when_preparing(self):
        draft = self.draft(provider_account_id=None)
        job = self.service.prepare_job(draft["id"], provider_account_id=self.account["id"])
        self.assertEqual(job["sender_snapshot"], "sender@example.test")
        self.assertEqual(self.service.draft(draft["id"])["provider_account_id"], self.account["id"])
        self.assertEqual(job["body_snapshot"], draft["body"])
        self.assertEqual(self.provider.sent, [])

    def test_sender_assignment_is_atomic_and_does_not_change_existing_jobs(self):
        original = self.draft()
        old_job = self.service.prepare_job(original["id"])
        second = self.service.register_account("second@example.test", {"refresh_token": "fake-second"})
        self.project.connection.execute("CREATE TRIGGER reject_sender_job BEFORE INSERT ON email_jobs BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.prepare_job(original["id"], provider_account_id=second["id"])
        self.assertEqual(self.service.draft(original["id"])["provider_account_id"], self.account["id"])
        self.project.connection.execute("DROP TRIGGER reject_sender_job")
        new_job = self.service.prepare_job(original["id"], provider_account_id=second["id"])
        self.assertEqual(self.service.job(old_job["id"])["sender_snapshot"], "sender@example.test")
        self.assertEqual(new_job["sender_snapshot"], "second@example.test")
        self.assertEqual(self.service.draft(original["id"])["provider_account_id"], second["id"])

    def test_future_job_needs_explicit_immediate_send_and_has_audit_receipt(self):
        job = self.prepared(scheduled_local="2026-10-12T15:00")
        self.service.approve(job["id"])
        self.assertEqual(self.service.process_due(), [])
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])
        self.assertEqual(self.provider.sent, [])
        result = self.service.send_job(job["id"], send_now=True)
        self.assertEqual(result["status"], "Sent")
        receipt = json.loads(self.project.connection.execute("SELECT details_json FROM activity_log WHERE event_type='email_sent'").fetchone()[0])
        self.assertTrue(receipt["sent_before_schedule"])
        self.service.send_job(job["id"], send_now=True)
        self.assertEqual(len(self.provider.sent), 1)

    def test_approve_and_send_clears_approval_after_preflight_failure(self):
        job = self.prepared(scheduled_local="2026-10-12T15:00")
        self.provider.email = "different@example.test"
        with self.assertRaises(MailError):
            self.service.approve_and_send(job["id"])
        result = self.service.job(job["id"])
        self.assertEqual(result["approval_status"], "pending")
        self.assertEqual(result["last_error_code"], "preflight")
        self.assertEqual(result["attempt_count"], 0)
        self.assertEqual(self.provider.sent, [])

    def test_approve_and_send_preserves_uncertainty_and_never_retries_it(self):
        job = self.prepared()
        self.provider.failure = ProviderError("timeout", uncertain=True)
        result = self.service.approve_and_send(job["id"])
        self.assertEqual(result["status"], "Uncertain")
        with self.assertRaises(MailError):
            self.service.approve_and_send(job["id"])
        self.assertEqual(len(self.provider.sent), 1)

    def test_success_is_not_sent_twice_and_has_activity_receipt(self):
        job = self.approved()
        self.service.send_job(job["id"])
        self.service.send_job(job["id"])
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM activity_log WHERE event_type='email_sent'").fetchone()[0], 1)

    def test_unknown_send_result_stays_locked_until_positive_reconciliation(self):
        job = self.approved()
        self.provider.failure = ProviderError("timeout", uncertain=True)
        result = self.service.send_job(job["id"])
        self.assertEqual(result["status"], "Uncertain")
        with self.assertRaises(MailError):
            self.service.retry_failed(job["id"])
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])
        self.assertEqual(self.service.reconcile(job["id"])["status"], "ReconciliationRequired")
        self.provider.matches = [{"id": "gmail123", "message_id": job["message_id_snapshot"]}]
        result = self.service.reconcile(job["id"])
        self.assertEqual(result["status"], "Sent")
        self.assertEqual(result["attempts"][0]["result"], "Reconciled")
        self.assertEqual(len(self.provider.sent), 1)

    def test_multiple_reconciliation_matches_do_not_allow_retry(self):
        job = self.approved()
        self.provider.failure = RuntimeError("unexpected")
        self.service.send_job(job["id"])
        self.provider.matches = [{"id": str(index), "message_id": job["message_id_snapshot"]} for index in range(2)]
        self.assertEqual(self.service.reconcile(job["id"])["status"], "ReconciliationRequired")
        self.assertNotIn("unexpected", self.service.job(job["id"])["last_error_message"])

    def test_definitive_failure_has_explicit_retry_and_same_message_identity(self):
        job = self.approved()
        self.provider.failure = ProviderError("Rejected", code="http_400")
        self.assertEqual(self.service.send_job(job["id"])["status"], "Failed")
        self.assertEqual(self.service.process_due(), [])
        self.provider.failure = None
        self.service.retry_failed(job["id"])
        result = self.service.send_job(job["id"])
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(self.provider.sent[0], self.provider.sent[1])

    def test_attachment_or_payload_tampering_prevents_send(self):
        source = self.folder / "file.txt"
        source.write_bytes(b"fixed")
        draft = self.draft(attachments=[{"path": str(source)}])
        job = self.service.prepare_job(draft["id"])
        self.service.approve(job["id"])
        self.project.file_path(job["attachments"][0]["file_path_snapshot"]).write_bytes(b"changed")
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])
        self.assertEqual(self.provider.sent, [])
        job = self.approved()
        self.project.file_path(job["payload_file_path"]).write_bytes(b"changed")
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])

    def test_job_snapshot_columns_cannot_be_modified(self):
        job = self.prepared()
        with self.assertRaises(sqlite3.IntegrityError):
            self.project.connection.execute("UPDATE email_jobs SET subject_snapshot='changed' WHERE id=?", (job["id"],))

    def test_account_mismatch_and_disconnect_stop_delivery(self):
        job = self.approved()
        self.provider.email = "other@example.test"
        with self.assertRaises(MailError):
            self.service.send_job(job["id"])
        self.service.disconnect(self.account["id"])
        self.assertIsNone(self.tokens.get(self.account["id"]))
        self.assertEqual(self.service.job(job["id"])["approval_status"], "pending")

    def test_scheduled_job_runs_only_when_due(self):
        job = self.prepared(scheduled_local="2026-10-11T15:00")
        self.service.approve(job["id"])
        self.assertEqual(self.service.process_due(), [])
        self.clock += timedelta(hours=1)
        self.assertEqual(self.service.process_due(), [{"id": job["id"], "status": "Sent"}])

    def test_restart_marks_overdue_as_needing_confirmation(self):
        job = self.prepared(scheduled_local="2026-10-11T15:00")
        self.service.approve(job["id"])
        self.clock += timedelta(hours=2)
        self.project.close()
        self.project = open_project(self.folder / "project")
        self.service = self.make_service()
        self.service.recover()
        self.assertEqual(self.service.process_due(), [])
        with self.assertRaises(MailError):
            self.service.approve(job["id"])
        self.service.approve(job["id"], confirm_overdue=True)
        self.assertEqual(self.service.process_due()[0]["status"], "Sent")

    def test_interrupted_sending_is_recovered_without_resend(self):
        job = self.approved()
        now = self.service._timestamp()
        self.project.connection.execute("UPDATE email_jobs SET status='Sending',attempt_count=1 WHERE id=?", (job["id"],))
        self.project.connection.execute("INSERT INTO email_attempts(id,email_job_id,attempt_number,started_at_utc,result) VALUES('interrupted',?,1,?,'Started')", (job["id"], now))
        self.service.recover()
        self.assertEqual(self.service.job(job["id"])["status"], "ReconciliationRequired")
        self.assertEqual(self.service.job(job["id"])["attempts"][0]["result"], "Uncertain")
        self.assertEqual(self.service.process_due(), [])

    def test_cancel_and_batch_cancellation_do_not_send(self):
        job = self.prepared(scheduled_local="2026-10-11T15:00")
        self.service.approve(job["id"])
        self.clock += timedelta(hours=2)
        self.assertEqual(self.service.process_due(cancelled=lambda: True), [])
        self.service.cancel(job["id"])
        self.assertEqual(self.service.process_due(), [])
        self.assertEqual(self.provider.sent, [])

    def test_manual_approved_jobs_are_excluded_from_automatic_scheduler(self):
        job = self.approved()
        self.assertEqual(self.service.process_due(), [])
        self.assertEqual(self.service.job(job["id"])["status"], "Queued")

    def test_sync_creates_and_updates_gmail_draft_without_sending(self):
        draft = self.draft()
        self.service.sync_draft(draft["id"])
        self.draft(draft_id=draft["id"], body="Changed")
        self.service.sync_draft(draft["id"])
        self.assertIsNone(self.provider.drafts[0][1])
        self.assertEqual(self.provider.drafts[1][1], "draft123")
        self.assertEqual(self.provider.sent, [])

    def test_html_and_signature_have_plain_alternative(self):
        signature = self.service.save_signature("Sig", "Ada", "<b>Ada</b>")
        draft = self.draft(body="<p>Hello</p>", body_format="html", signature_id=signature)
        job = self.service.prepare_job(draft["id"])
        raw = self.project.file_path(job["payload_file_path"]).read_bytes()
        mime = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertIn("Hello", mime.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("<b>Ada</b>", mime.get_body(preferencelist=("html",)).get_content())

    def test_partial_attachment_failure_cleans_captured_files(self):
        source = self.folder / "file.txt"
        source.write_bytes(b"one")
        with self.assertRaises(MailError):
            self.draft(attachments=[{"path": str(source)}, {"path": str(self.folder / "missing.txt")}])
        self.assertEqual([p for p in (self.project.path / "exports").rglob("*") if p.is_file()], [])

    def test_snapshot_insert_failure_rolls_back_job_and_files(self):
        draft = self.draft()
        self.project.connection.execute("CREATE TRIGGER reject_job BEFORE INSERT ON email_jobs BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.prepare_job(draft["id"])
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
        self.assertEqual(list((self.project.path / "exports/mail/jobs").rglob("*.eml")), [])

    def test_send_receipt_failure_leaves_reconcilable_job(self):
        job = self.approved()
        self.project.connection.execute("CREATE TRIGGER reject_activity BEFORE INSERT ON activity_log BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.send_job(job["id"])
        self.assertEqual(len(self.provider.sent), 1)
        self.assertEqual(self.service.job(job["id"])["status"], "Sending")
        self.service.recover()
        self.assertEqual(self.service.process_due(), [])

    def test_mail_metadata_does_not_contain_oauth_secrets(self):
        self.draft()
        snapshot = self.service.snapshot()
        self.assertNotIn("fake-token", json.dumps(snapshot))
        self.assertNotIn("fake-token", "\n".join(self.project.connection.iterdump()))
        archive = self.project.create_backup()
        import zipfile
        with zipfile.ZipFile(archive) as backup:
            self.assertNotIn(b"fake-token", backup.read("emailcenter.sqlite3"))

    def test_attempt_insert_failure_prevents_provider_send_and_rolls_back_claim(self):
        job = self.approved()
        self.project.connection.execute("CREATE TRIGGER reject_attempt BEFORE INSERT ON email_attempts BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.send_job(job["id"])
        result = self.service.job(job["id"])
        self.assertEqual((result["status"], result["attempt_count"]), ("Queued", 0))
        self.assertEqual(self.provider.sent, [])

    def test_second_connection_cannot_send_job_already_claimed(self):
        job = self.approved()
        second = open_project(self.project.path)
        service = MailService(second, token_store=self.tokens, provider_factory=lambda account: self.provider, now=lambda: self.clock)
        send = self.provider.send
        def competing_send(raw):
            with self.assertRaises(MailError):
                service.send_job(job["id"])
            return send(raw)
        self.provider.send = competing_send
        try:
            self.service.send_job(job["id"])
            self.assertEqual(len(self.provider.sent), 1)
        finally:
            second.close()


class MailValueTests(unittest.TestCase):
    def test_dst_nonexistent_and_ambiguous_times_require_correction(self):
        for value in ("2026-03-29T02:30", "2026-10-25T02:30"):
            with self.assertRaises(MailError):
                schedule_time(value, "Europe/Berlin")
        self.assertEqual(schedule_time("2026-10-25T02:30+01:00", "Europe/Berlin"), "2026-10-25T01:30:00Z")

    def test_recipients_reject_injection_duplicates_and_empty_to(self):
        for value in ({"to": ["x@example.test\r\nBcc: victim@example.test"]}, {"to": ["x@example.test"], "bcc": ["X@example.test"]}, {"cc": ["x@example.test"]}):
            with self.assertRaises(MailError):
                recipients(value)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryVault()
        self.store = WindowsTokenStore("project", backend=self.backend)

    def test_large_credentials_chunked_updated_and_deleted(self):
        info = {"refresh_token": "x" * 6000, "name": "ä" * 1000}
        self.store.put("account", info)
        self.assertEqual(self.store.get("account"), info)
        self.store.put("account", {"refresh_token": "new"})
        self.assertEqual(len(self.backend.values), 2)
        self.assertEqual(self.store.get("account")["refresh_token"], "new")
        self.store.delete("account")
        self.assertEqual(self.backend.values, {})

    def test_failed_generation_keeps_old_credentials_and_redacts_error(self):
        self.store.put("account", {"refresh_token": "old"})
        self.backend.fail = True
        with self.assertRaises(MailError) as error:
            self.store.put("account", {"refresh_token": "new"})
        self.assertNotIn("fake-secret", str(error.exception))
        self.assertEqual(self.store.get("account")["refresh_token"], "old")
        self.assertEqual(len(self.backend.values), 2)

    def test_different_projects_do_not_share_credentials(self):
        self.store.put("account", {"refresh_token": "one"})
        self.assertIsNone(WindowsTokenStore("other", backend=self.backend).get("account"))

    def test_new_authorization_replaces_corrupt_manifest(self):
        self.backend.values[self.store._service("account"), "oauth"] = "broken"
        with self.assertRaises(MailError):
            self.store.get("account")
        self.store.put("account", {"refresh_token": "new"})
        self.assertEqual(self.store.get("account")["refresh_token"], "new")

    @unittest.skipUnless(os.name == "nt" and os.environ.get("EMAILCENTER_NATIVE_VAULT_TEST") == "1", "Native vault check is opt-in outside the restricted runner")
    def test_native_windows_vault_roundtrip_only_uses_temporary_test_identity(self):
        store = WindowsTokenStore(str(uuid4()))
        identifier = str(uuid4())
        try:
            store.put(identifier, {"refresh_token": "synthetic-test-value" * 200})
            self.assertEqual(store.get(identifier)["refresh_token"], "synthetic-test-value" * 200)
        finally:
            store.delete(identifier)
        self.assertIsNone(store.get(identifier))


class FakeResponse:
    def __init__(self, value=None, status=200):
        self.status_code, self.value = status, value

    def json(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        pass


class FakeCredentials:
    valid = True
    token = "fake-access-token"

    def refresh(self, request):
        self.valid = True
        self.token = "renewed-fake-token"

    def to_json(self):
        return '{"token":"renewed-fake-token"}'


class ProviderTests(unittest.TestCase):
    def provider(self, responses):
        session = FakeSession(responses)
        return GmailProvider({}, session=session, credentials=FakeCredentials()), session

    def test_success_posts_once_and_base64_encodes_payload(self):
        provider, session = self.provider([FakeResponse({"id": "123"})])
        self.assertEqual(provider.send(b"MIME"), "123")
        self.assertEqual(len(session.calls), 1)
        method, url, options = session.calls[0]
        self.assertEqual((method, url), ("POST", API_ROOT + "/messages/send"))
        self.assertEqual(base64.urlsafe_b64decode(options["json"]["raw"]), b"MIME")
        self.assertFalse(options["allow_redirects"])

    def test_timeouts_429_5xx_bad_json_missing_id_are_uncertain_without_retry(self):
        for response in (TimeoutError("token secret"), FakeResponse({}, 429), FakeResponse({}, 503), FakeResponse(ValueError()), FakeResponse({})):
            provider, session = self.provider([response])
            with self.assertRaises(ProviderError) as error:
                provider.send(b"MIME")
            self.assertTrue(error.exception.uncertain)
            self.assertNotIn("token secret", str(error.exception))
            self.assertEqual(len(session.calls), 1)

    def test_4xx_is_definitive_and_draft_update_uses_put(self):
        provider, session = self.provider([FakeResponse({}, 400), FakeResponse({"id": "draft"})])
        with self.assertRaises(ProviderError) as error:
            provider.send(b"MIME")
        self.assertFalse(error.exception.uncertain)
        self.assertEqual(provider.save_draft(b"MIME", "draft"), "draft")
        self.assertEqual(session.calls[-1][0], "PUT")

    def test_reconciliation_only_accepts_sent_label_and_exact_message_id(self):
        provider, session = self.provider([FakeResponse({"messages": [{"id": "123"}, {"id": "456"}]}),
                                          FakeResponse({"id": "123", "labelIds": ["SENT"], "payload": {"headers": [{"name": "Message-ID", "value": "<one@emailcenter.local>"}]}}),
                                          FakeResponse({"id": "456", "labelIds": ["DRAFT"], "payload": {"headers": [{"name": "Message-ID", "value": "<one@emailcenter.local>"}]}})])
        matches = provider.find_sent("<one@emailcenter.local>")
        self.assertEqual([match["id"] for match in matches], ["123"])
        self.assertEqual(session.calls[0][2]["params"]["q"], "in:sent rfc822msgid:one@emailcenter.local")

    def test_invalid_client_json_is_rejected_before_browser_or_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "client.json"
            path.write_text('{"web":{}}', encoding="utf-8")
            with self.assertRaises(MailError):
                authorize_desktop(path)

    def test_authorization_uses_loopback_pkce_browser_and_both_scopes(self):
        info = {"installed": {"client_id": "fake.apps.googleusercontent.com", "client_secret": "fake-client-secret",
                              "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
        credentials = MagicMock()
        credentials.refresh_token = "synthetic-refresh"
        credentials.has_scopes.return_value = True
        credentials.to_json.return_value = '{"refresh_token":"synthetic-refresh"}'
        flow = MagicMock()
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "client.json"
            path.write_text(json.dumps(info), encoding="utf-8")
            with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config", return_value=flow) as create, patch("emailcenter.gmail.run_local_oauth", return_value=credentials) as callback:
                result = authorize_desktop(path)
            self.assertEqual(result["refresh_token"], "synthetic-refresh")
            self.assertEqual(create.call_args.args[1], SCOPES)
            self.assertTrue(create.call_args.kwargs["autogenerate_code_verifier"])
            self.assertIs(callback.call_args.args[0], flow)
            self.assertEqual(callback.call_args.kwargs["timeout_seconds"], 180)

    def test_refresh_persists_securely_before_single_send(self):
        provider, session = self.provider([FakeResponse({"id": "123"})])
        provider.credentials.valid = False
        values = []
        provider.persist = lambda info: values.append(info)
        self.assertEqual(provider.send(b"MIME"), "123")
        self.assertEqual(values, [{"token": "renewed-fake-token"}])
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][2]["headers"]["Authorization"], "Bearer renewed-fake-token")

    def test_refresh_or_vault_failure_prevents_send(self):
        provider, session = self.provider([])
        provider.credentials.valid = False
        provider.persist = MagicMock(side_effect=RuntimeError("synthetic-secret"))
        with self.assertRaises(ProviderError) as error:
            provider.send(b"MIME")
        self.assertFalse(error.exception.uncertain)
        self.assertEqual(session.calls, [])
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_paginated_reconciliation_results_are_never_treated_as_unique(self):
        provider, session = self.provider([FakeResponse({"nextPageToken": "next", "messages": [{"id": "123"}]})])
        with self.assertRaises(ProviderError):
            provider.find_sent("<one@emailcenter.local>")
        self.assertEqual(len(session.calls), 1)

    def test_draft_id_cannot_change_request_path(self):
        provider, session = self.provider([])
        with self.assertRaises(ProviderError):
            provider.save_draft(b"MIME", "../messages/send")
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
