"""Project defaults, recipient collections, policies and resumable DOCX work."""

from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

import test_bulk_delivery as delivery_fixture
import test_workflow_expansion as workflow_fixture
from emailcenter.document_service import DocumentService
from emailcenter.documents import extract_docx_text
from emailcenter.gmail import ProviderError
from emailcenter.mail_bulk import BulkMailService
from emailcenter.project import create_project, open_project
from emailcenter.project_defaults import ProjectDefaultsService
from emailcenter.recipient_library import RecipientLibrary
from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.word_replace import WordReplaceService, replace_docx, file_hash
from emailcenter.word_replace_runs import WordReplaceRuns
from emailcenter.filename_patterns import output_name, validate_pattern

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def simple_docx(path, text="Hallo {{NAME}}"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:rPr><w:i/></w:rPr><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')


class ExpansionTests(unittest.TestCase):
    setUp = workflow_fixture.ProjectFixture.setUp
    tearDown = workflow_fixture.ProjectFixture.tearDown
    saved_list = workflow_fixture.ProjectFixture.saved_list
    contact = workflow_fixture.ProjectFixture.contact

    def document(self, name="Brief", text="Hallo {{NAME}}"):
        path = self.root / (name + ".docx")
        simple_docx(path, text)
        return DocumentService(self.project).import_template(path, name=name, mapping={"NAME": "contact.display_name"}, required_placeholders=["NAME"])["version"]

    def rules(self):
        return [{"find": "{{NAME}}", "replacement": "", "field": "contact.display_name"}]

    def begin_run(self, **changes):
        simple_docx(self.source)
        options = {"source_path": str(self.source), "rules": self.rules(), "sources": [
            {"kind": "manual", "fields": {"contact.display_name": name, "company.name": name + " GmbH"}} for name in ("Ada", "Grace")]}
        options.update(changes)
        preview = WordReplaceService(self.project).preview(**options)
        service = WordReplaceRuns(self.project)
        run = service.begin(expected_fingerprint=preview["fingerprint"], output_directory=str(self.project.path / "exports/result"), prefix="Brief", **options)
        return service, run

    def test_project_creation_imports_defaults_atomically_and_reopens(self):
        source = self.root / "setup.docx"
        simple_docx(source)
        project = create_project(self.root / "configured", goal="Bewerbungen", initial_profile={"display_name": "Timon", "email": "timon@example.test", "phone": "123", "custom_fields_json": '{"skills":"Python"}', "address_json": '{"city":"Berlin"}'},
            defaults={"account_email": "sender@example.test", "body_format": "html"}, initial_document={"source_path": str(source), "name": "Anschreiben"},
            initial_source={"name": "Empfänger", "rows": [{"fields": {"contact.display_name": "Ada"}}]})
        path = project.path
        settings = ProjectDefaultsService(project).details()
        self.assertEqual(settings["defaults"]["body_format"], "html")
        for key in ("document_version_id", "applicant_profile_id", "source_list_id"):
            self.assertTrue(settings["defaults"][key])
        self.assertIn("Python", project.connection.execute("SELECT custom_fields_json FROM applicant_profiles").fetchone()[0])
        project.close()
        with open_project(path) as reopened:
            self.assertEqual(ProjectDefaultsService(reopened).details()["defaults"], settings["defaults"])

    def test_failed_initial_template_keeps_target_absent(self):
        target = self.root / "broken"
        with self.assertRaises(Exception):
            create_project(target, initial_document={"source_path": str(self.root / "missing.docx"), "name": "Brief"})
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".broken.creating-*")), [])

    def test_project_defaults_revision_and_deleted_references(self):
        version = self.document()
        profile = self.workspace.create_record("applicants", {"display_name": "Timon"})
        service = ProjectDefaultsService(self.project)
        first = service.details()
        values = {"document_version_id": version["id"], "applicant_profile_id": profile["id"], "body_format": "html"}
        saved = service.save("Ziel", "mail", values, first["version"])
        self.assertEqual(saved["goal"], "Ziel")
        with self.assertRaisesRegex(ValueError, "geändert"):
            service.save("Alt", "mail", values, first["version"])
        self.db.execute("UPDATE templates SET deleted_at='now' WHERE id=?", (version["template_id"],))
        self.assertIsNone(service.details()["defaults"]["document_version_id"])

    def test_recipient_groups_filters_and_invalid_sources(self):
        contact = self.contact()
        library = RecipientLibrary(self.db)
        values = library.save("group", "Partner", contact_ids=[contact["id"]])
        group = values["recipient_groups"][0]
        values = library.save("filter", "Ada", configuration={"search": "Ada", "group_id": group["id"], "valid_only": True})
        self.assertEqual(values["recipient_filters"][0]["configuration"]["search"], "Ada")
        with self.assertRaises(ValueError):
            library.save("group", "Fremde Liste", contact_ids=["manual:123"])
        library.delete("group", group["id"])
        self.assertTrue(self.db.execute("SELECT 1 FROM contacts WHERE id=?", (contact["id"],)).fetchone())
        with self.assertRaises(ValueError):
            library.validate(values["recipient_filters"][0]["configuration"])

    def test_distinct_docx_versions_per_row_and_optional_domain_applications(self):
        from emailcenter.mail_templates import MailTemplateService
        a, b = self.document("A", "A {{NAME}}"), self.document("B", "B {{NAME}}")
        template = MailTemplateService(self.db).save(name="Mail", subject="Bewerbung", body="Hallo {{contact.display_name}}")
        contacts = [self.contact(name) for name in ("Ada", "Grace")]
        options = {"version_id": template["id"], "items": [{"contact_id": c["id"], "document_version_id": v["id"], "create_application": True} for c, v in zip(contacts, (a, b))]}
        service = BulkMailService(self.project)
        preview = service.preview(**options)
        self.assertTrue(preview["ready"], preview)
        self.assertIn("A Ada", preview["rows"][0]["generated_document"]["text"])
        self.assertIn("B Grace", preview["rows"][1]["generated_document"]["text"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 0)
        saved = service.create(name="Bewerbungen", expected_fingerprint=preview["fingerprint"], **options)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM application_contacts").fetchone()[0], 2)
        self.assertTrue(all(service.mail.draft(i["draft_id"])["application_id"] for i in saved["batch"]["items"]))

    def test_word_run_resumes_with_captured_source_and_values(self):
        service, run = self.begin_run()
        first = service.next(run["id"])
        self.assertEqual(first["completed"], 1)
        first_hash = first["items"][0]["output_hash"]
        simple_docx(self.source, "Geändert {{NAME}}")
        path = self.project.path
        self.workspace.close()
        self.workspace.open(str(path))
        self.project, self.db = self.workspace.project, self.workspace.project.connection
        service = WordReplaceRuns(self.project)
        result = service.next(run["id"])
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["items"][0]["output_hash"], first_hash)
        self.assertTrue(extract_docx_text(result["items"][1]["output_path"]).endswith("Hallo Grace"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents WHERE document_type='word_replace'").fetchone()[0], 2)

    def test_word_run_completed_file_change_stops_without_overwriting(self):
        service, run = self.begin_run()
        result = service.next(run["id"])
        target = Path(result["items"][0]["output_path"])
        target.write_bytes(b"manuell geaendert")
        with self.assertRaisesRegex(ValueError, "fertige Ausgabe"):
            service.next(run["id"])
        self.assertEqual(target.read_bytes(), b"manuell geaendert")
        self.assertFalse(Path(run["items"][1]["output_path"]).exists())

    def test_word_publication_recovers_without_duplicate_document(self):
        service, run = self.begin_run()
        with patch.object(service, "_complete", side_effect=RuntimeError("simulierter Neustart")):
            with self.assertRaises(RuntimeError):
                service.next(run["id"])
        self.assertTrue(Path(run["items"][0]["output_path"]).exists())
        result = service.next(run["id"])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)

    def test_word_run_cancel_preserves_pending_and_completed_rows(self):
        service, run = self.begin_run()
        self.assertEqual(service.next(run["id"], cancelled=lambda: True)["completed"], 0)
        self.assertFalse(Path(run["items"][0]["output_path"]).exists())
        self.assertEqual(service.next(run["id"])["completed"], 1)
        result = service.next(run["id"], cancelled=lambda: True)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["status"], "Paused")

    def test_filename_patterns_safe_values_and_validation(self):
        self.assertEqual(output_name("Brief", 2, "Ada", {"company.name": "Firma/A"}, "pdf", "{prefix}-{number:03d}-{company.name}"), "Brief-002-Firma_A.pdf")
        for value in ("../{name}", "{name!r}", "{number:999999999d}", "{fields[0]}", "{name"):
            with self.assertRaises(ValueError, msg=value):
                validate_pattern(value)
        with self.assertRaises(ValueError):
            output_name("Brief", 1, "Ada", {}, "docx", "{company.name}")

    def test_word_live_owner_blocks_second_window_and_dead_owner_recovers(self):
        service, run = self.begin_run()
        claimed = service._claim(run["id"])
        from emailcenter.process_identity import owner_is_alive
        self.assertTrue(owner_is_alive(claimed))
        with open_project(self.project.path) as second:
            other = WordReplaceRuns(second)
            with self.assertRaisesRegex(ValueError, "anderen Fenster"):
                other.next(run["id"])
            with self.assertRaisesRegex(ValueError, "anderen Fenster"):
                other.pause(run["id"])
            with patch("emailcenter.word_replace_runs.owner_is_alive", return_value=False):
                recovered = other.next(run["id"])
            self.assertEqual(recovered["completed"], 1)
            self.assertIsNone(recovered["owner_token"])
        self.assertEqual(service.next(run["id"])["status"], "Completed")

    def test_cancelled_document_generation_does_not_publish_or_register(self):
        version = self.document()
        from emailcenter.document_service import DocumentServiceError
        with self.assertRaisesRegex(DocumentServiceError, "abgebrochen"):
            DocumentService(self.project).generate_document(version["id"], {"NAME": "Ada"}, output_filename="Brief.docx", cancelled=lambda: True)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
        self.assertEqual(list((self.project.path / "documents/generated").glob("*.docx")), [])

    def test_pdf_cancel_stops_only_owned_converter_and_keeps_original(self):
        import subprocess
        from unittest.mock import MagicMock
        from emailcenter.document_service import convert_docx_to_pdf, DocumentServiceError
        simple_docx(self.source)
        before = file_hash(self.source)
        process = MagicMock()
        process.pid = 424242
        process.poll.side_effect = [None, None]
        checks = iter((False, True))
        target = self.root / "cancel.pdf"
        with patch("emailcenter.document_service.subprocess.Popen", return_value=process), patch("emailcenter.document_service.subprocess.run") as kill:
            with self.assertRaisesRegex(DocumentServiceError, "abgebrochen"):
                convert_docx_to_pdf(self.source, target, executable="isolated-test-converter", cancelled=lambda: next(checks))
            if __import__("os").name == "nt":
                self.assertEqual(kill.call_args.args[0], ["taskkill", "/PID", "424242", "/T", "/F"])
        process.kill.assert_called_once()
        self.assertFalse(target.exists())
        self.assertEqual(file_hash(self.source), before)

    def test_word_replacement_styles_affect_only_replacement(self):
        simple_docx(self.source, "Start {{NAME}} Ende {{NAME}}")
        for style in ("plain", "bold", "italic"):
            target = self.root / (style + ".docx")
            replace_docx(self.source, target, [{"find": "{{NAME}}", "replacement": "Ada", "field": ""}], replacement_style=style)
            self.assertTrue(extract_docx_text(target).endswith("Start Ada Ende Ada"))
            with zipfile.ZipFile(target) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
            runs = list(root.iter(f"{{{W}}}r"))
            replaced = [r for r in runs if "".join(t.text or "" for t in r.iter(f"{{{W}}}t")) == "Ada"]
            self.assertEqual(len(replaced), 2)
            self.assertTrue(runs[0].find(f"{{{W}}}rPr/{{{W}}}i") is not None)
            if style == "plain":
                self.assertTrue(all(r.find(f"{{{W}}}rPr") is None for r in replaced))
            else:
                tag = "b" if style == "bold" else "i"
                self.assertTrue(all(r.find(f"{{{W}}}rPr/{{{W}}}{tag}") is not None for r in replaced))

    def test_preferences_new_options_roundtrip_and_validation(self):
        preferences = Preferences.validate({**Preferences().values(), "reduced_motion": True, "toast_seconds": 12,
            "builder_palette_width": 280, "word_replace_style": "bold", "word_replace_filename_pattern": "{prefix}-{number:03d}"})
        store = PreferencesStore(self.root / "prefs.json")
        store.load()
        store.save(preferences)
        self.assertEqual(store.load()[0], preferences)
        for changes in ({"toast_seconds": 0}, {"builder_palette_width": 100}, {"reduced_motion": 1}, {"word_replace_filename_pattern": "../x"}):
            with self.assertRaises(ValueError):
                Preferences.validate({**preferences.values(), **changes})


class DispatchPolicyTests(unittest.TestCase):
    setUp = delivery_fixture.BulkDeliveryTests.setUp
    tearDown = delivery_fixture.BulkDeliveryTests.tearDown
    make_service = delivery_fixture.BulkDeliveryTests.make_service
    begin = delivery_fixture.BulkDeliveryTests.begin
    ready = delivery_fixture.BulkDeliveryTests.ready
    approved = delivery_fixture.BulkDeliveryTests.approved
    running = delivery_fixture.BulkDeliveryTests.running

    def test_daily_budget_counts_attempts_across_group_and_resume(self):
        value = self.running(daily_budget=1)
        first = self.service.next(value["id"])
        self.assertEqual(first["counts"]["sent"], 1)
        self.clock += timedelta(seconds=2)
        waiting = self.service.next(value["id"])
        self.assertIn("Tagesbudget", waiting["wait_reason"])
        self.assertEqual(len(self.provider.sent), 1)
        self.clock += timedelta(days=1)
        final = self.service.next(value["id"])
        self.assertEqual(final["status"], "Completed")
        self.assertEqual(len(self.provider.sent), 2)

    def test_send_window_and_overnight_window(self):
        value = self.running(window_start="09:00", window_end="12:00", timezone_id="Europe/Berlin")
        waiting = self.service.next(value["id"])
        self.assertTrue(waiting["wait_until"])
        self.assertEqual(self.provider.sent, [])
        self.assertIn("Versandfenster", waiting["wait_reason"])
        from emailcenter.delivery_policy import policy_wait
        overnight = {**value, "window_start": "22:00", "window_end": "06:00"}
        self.clock = self.clock.replace(hour=22)
        self.assertIsNone(policy_wait(self.db, overnight, self.clock)["wait_until"])

    def test_background_uses_same_approved_jobs_and_pauses_after_gap(self):
        value = self.approved()
        value = self.service.start(value["id"], value["fingerprint"], background=True)
        result = self.service.background_next()
        self.assertEqual(result["dispatch"]["counts"]["sent"], 1)
        paused = self.service.background_next(require_review=True)
        self.assertEqual(paused["groups"][0]["status"], "Paused")
        self.assertEqual(len(self.provider.sent), 1)
        self.assertTrue(self.service.snapshot(value["id"])["items"][1]["job"]["requires_overdue_confirmation"])

    def test_quota_hold_persists_and_uncertain_job_is_not_retried(self):
        value = self.running()
        self.provider.failure = ProviderError("Limit", code="quota_429", uncertain=True, retry_after=300)
        result = self.service.next(value["id"])
        self.assertEqual(result["status"], "Paused")
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertTrue(self.db.execute("SELECT 1 FROM email_account_holds").fetchone())
        self.service.background_next()
        self.assertEqual(len(self.provider.sent), 1)

    def test_receipts_update_application_only_after_confirmed_send(self):
        application = self.workspace.create_record("applications", {"title": "Bewerbung"})
        draft_id = self.batch["items"][0]["draft_id"]
        self.db.execute("UPDATE email_drafts SET application_id=? WHERE id=?", (application["id"], draft_id))
        value = self.running()
        before = self.workspace.list_records("applications")["rows"][0]
        self.assertEqual(before["status_code"], "draft")
        self.service.next(value["id"])
        after = self.workspace.list_records("applications")["rows"][0]
        self.assertEqual(after["status_code"], "sent")
        self.assertEqual(after["mail_status"], "Sent")

    def test_policy_validation_rejects_bad_times_and_budget(self):
        for options in ({"daily_budget": 0}, {"daily_budget": True}, {"window_start": "25:00"}, {"window_end": "9:00"}):
            with self.assertRaises(ValueError):
                self.begin(**options)

    def test_profile_quota_pauses_before_any_send_attempt(self):
        value = self.running()
        with patch.object(self.provider, "profile", side_effect=ProviderError("Tageslimit", code="quota_dailyLimitExceeded", retry_after=86400)):
            result = self.service.next(value["id"])
        self.assertEqual(result["status"], "Paused")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_attempts").fetchone()[0], 0)
        self.assertEqual(self.provider.sent, [])
        draft = self.service.mail.save_draft(subject="Einzelauftrag", body="Test", recipients_value={"to": ["other@example.test"]}, provider_account_id=self.account["id"])
        job = self.service.mail.prepare_job(draft["id"])
        self.service.mail.approve(job["id"])
        with patch.object(self.provider, "profile") as profile:
            with self.assertRaisesRegex(ValueError, "Anbietersperre"):
                self.service.mail.send_job(job["id"])
            profile.assert_not_called()

    def test_confirmed_mail_does_not_overwrite_later_application_status(self):
        application = self.workspace.create_record("applications", {"title": "Gespräch", "status_code": "interview"})
        self.db.execute("UPDATE email_drafts SET application_id=? WHERE id=?", (application["id"], self.batch["items"][0]["draft_id"]))
        value = self.running()
        self.service.next(value["id"])
        after = self.workspace.list_records("applications")["rows"][0]
        self.assertEqual(after["status_code"], "interview")
        self.assertEqual(after["mail_status"], "Sent")


class QuotaTransportTests(unittest.TestCase):
    def test_provider_quota_codes_retry_header_and_uncertain_result(self):
        from test_mail import FakeSession, FakeResponse, FakeCredentials
        from emailcenter.gmail import GmailProvider
        for status, reason, delay, uncertain in ((403, "dailyLimitExceeded", 86400, False), (403, "userRateLimitExceeded", 600, False), (429, "", 600, True)):
            response = FakeResponse({"error": {"errors": [{"reason": reason}]}}, status)
            response.headers = {"Retry-After": "600"}
            session = FakeSession([response])
            with self.assertRaises(ProviderError) as failure:
                GmailProvider({}, session=session, credentials=FakeCredentials()).send(b"test")
            self.assertEqual(failure.exception.retry_after, delay)
            self.assertEqual(failure.exception.uncertain, uncertain)
            self.assertTrue(failure.exception.code.startswith("quota_"))
            self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
