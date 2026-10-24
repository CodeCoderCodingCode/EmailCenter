"""Offscreen integration of persisted endspurt settings and restore workflows."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_ui as harness
import test_builder_ui as builder_fixture
from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.ui.backup_dialog import RestoreDialog
from emailcenter.language import translate_tree
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QLabel, QPushButton, QMessageBox


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class EndspurtDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    action_result = harness.DesktopTests.action_result
    open_test_project = harness.DesktopTests.open_test_project
    enable_fake_gmail = harness.DesktopTests.enable_fake_gmail
    bulk_fixture = harness.DesktopTests.bulk_fixture
    builder = builder_fixture.BuilderDesktopTests.builder
    sources = builder_fixture.BuilderDesktopTests.sources

    def settings(self, **changes):
        self.window.save_preferences({**self.window.preferences.values(), **changes})
        self.assertEqual(self.errors, [])

    def test_new_settings_controls_save_reload_and_reset(self):
        page = self.window.pages["settings"]
        page.controls["language"].setCurrentIndex(page.controls["language"].findData("en"))
        page.controls["mail_account_email"].setText("sender@example.test")
        page.controls["backup_directory"].setText(str(self.directory))
        page.controls["backup_retention"].setValue(2)
        page.controls["list_page_size"].setValue(100)
        page.save_button.click()
        self.assertEqual(self.errors, [])
        reloaded, warning = PreferencesStore(self.directory / "preferences.json").load()
        self.assertIsNone(warning)
        self.assertEqual(reloaded.language, "en")
        self.assertEqual(reloaded.backup_retention, 2)
        self.assertEqual(reloaded.list_page_size, 100)
        page.defaults_button.click()
        self.assertEqual(page.values(), Preferences().values())
        page.discard_button.click()
        self.assertEqual(page.values(), reloaded.values())

    def test_language_changes_navigation_preserves_inputs_and_switches_back(self):
        page = self.window.pages["settings"]
        page.controls["mail_signature_name"].setText("Name")
        self.settings(language="en")
        self.assertEqual(self.window.navigation.item(self.window.page_order.index("workspace")).text(), "Workspace")
        self.assertEqual(page.save_button.text(), "Save and apply")
        page.controls["mail_signature_name"].setText("Name")
        translate_tree(self.window)
        self.assertEqual(page.controls["mail_signature_name"].text(), "Name")
        self.settings(language="de")
        self.assertEqual(self.window.navigation.item(self.window.page_order.index("workspace")).text(), "Arbeitsbereich")
        self.assertEqual(page.save_button.text(), "Speichern und anwenden")

    def test_project_wizard_uses_new_project_preferences(self):
        self.settings(workspace_mode="mail", mail_body_format="html", mail_account_email="test@example.test")
        self.window.show_project_wizard()
        dialog = self.window._project_dialog
        self.assertEqual(dialog.fields["workspace_mode"].currentData(), "mail")
        self.assertEqual(dialog.body_format.currentData(), "html")
        self.assertEqual(dialog.account_email.currentText(), "test@example.test")
        dialog.reject()

    def test_project_open_start_page_and_list_options(self):
        self.settings(start_page="builder", list_page_size=100, list_word_wrap=False, list_alternating_rows=False, list_compact_rows=True)
        self.open_test_project()
        self.wait_idle()
        self.assertIs(self.window.current_page(), self.window.pages["builder"])
        page = self.window.pages["contacts"]
        self.assertEqual(page.limit, 100)
        self.assertFalse(page.table.wordWrap())
        self.assertFalse(page.table.alternatingRowColors())
        self.window.navigate("contacts")
        self.wait_idle()
        self.assertEqual(page.offset, 0)

    def test_new_graph_defaults_and_planning_are_used(self):
        self.settings(builder_default_blocks=["greeting", "description", "closing"], mail_delivery_mode="scheduled",
                      mail_interval_seconds=7, mail_timezone_id="UTC", mail_daily_budget=3,
                      mail_window_start="08:30", mail_window_end="19:00")
        self.assertEqual(self.window.pages["settings"].values()["builder_default_blocks"], ["greeting", "description", "closing"])
        page = self.builder()
        self.assertEqual([n["kind"] for n in page.graph["nodes"]], ["data", "subject", "greeting", "description", "closing", "email"])
        self.assertEqual(page.delivery_mode.currentData(), "scheduled")
        self.assertEqual(page.timezone.currentText(), "UTC")
        self.assertEqual(page.interval.value(), 7)
        self.assertEqual(page.daily_budget.value(), 3)
        self.assertEqual(page.window_start.time().toString("HH:mm"), "08:30")

    def test_undo_redo_survive_project_close_and_open(self):
        page = self.builder()
        original = deepcopy(page.graph)
        changed = deepcopy(page.graph)
        changed["nodes"][1]["config"]["text"] = "Zwischenschritt"
        page.commit(changed)
        last = deepcopy(page.graph)
        last["nodes"][1]["config"]["text"] = "Letzter Schritt"
        page.commit(last)
        page.undo()
        self.assertEqual(page.graph, changed)
        self.submit("close_project", {})
        self.submit("open_project", {"path": str(self.directory / "project")})
        self.window.navigate("builder")
        self.wait_idle()
        self.assertEqual(page.graph, changed)
        self.assertEqual(len(page.history), 1)
        self.assertEqual(len(page.future), 1)
        page.redo()
        self.assertEqual(page.graph["nodes"][1]["config"]["text"], "Letzter Schritt")
        page.undo()
        page.undo()
        self.assertEqual(page.graph, original)

    def test_persistent_history_is_bounded_for_large_graphs(self):
        from emailcenter.ui.email_builder_page import EmailBuilderPage
        graph = {"nodes": [], "edges": [], "padding": "a" * 1_000_000}
        history = EmailBuilderPage.persisted_history([graph] * 100)
        self.assertLessEqual(len(history), 3)

    def test_preferred_account_signature_and_delivery_defaults_for_new_work(self):
        self.open_test_project()
        self.enable_fake_gmail()
        account = self.action_result("mail_snapshot", {})["accounts"][0]
        self.action_result("mail_save_signature", {"name": "Privat", "content_text": "Gruß"})
        self.settings(mail_account_email=account["account_email"], mail_signature_name="Privat", mail_daily_budget=2,
                      mail_interval_seconds=9, mail_timezone_id="UTC", mail_window_start="10:00", mail_window_end="18:00")
        self.submit("mail_compose_details", {})
        compose = self.window._mail_dialog
        self.assertEqual(compose.account.currentData(), account["id"])
        self.assertEqual(compose.signature.currentText(), "Privat")
        compose.reject()
        dialog, _, _ = self.bulk_fixture()
        self.assertEqual(dialog.signature.currentText(), "Privat")
        dialog.preview_button.click()
        self.wait_idle()
        dialog.confirm.setChecked(True)
        dialog.name.setText("Test")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dialog.create_button.click()
        self.wait_idle()
        self.window.controller.submit("mail_bulk_delivery_details", {"batch_id": dialog.batch["id"]})
        self.wait_idle()
        delivery = self.window._bulk_delivery_dialog
        self.assertEqual(delivery.interval.value(), 9)
        self.assertEqual(delivery.daily_budget.value(), 2)
        self.assertEqual(delivery.timezone.currentText(), "UTC")
        delivery.reject()
        self.wait_idle()
        dialog.reject()

    def test_backup_and_restore_work_through_the_worker_without_closing_original(self):
        self.assertTrue(self.window.actions["restore"].isEnabled())
        self.open_test_project()
        archive = self.action_result("backup", {"directory": str(self.directory / "archives"), "retention": 2})
        review = self.action_result("backup_inspect", {"path": archive})
        dialog = self.window._record_dialog
        self.assertIsInstance(dialog, RestoreDialog)
        dialog.parent_path.setText(str(self.directory))
        dialog.folder.setText("restored")
        dialog.restore_button.click()
        self.wait_idle()
        self.assertTrue((self.directory / "restored" / "emailcenter.json").is_file())
        self.assertEqual(self.window.snapshot["path"], str(self.directory / "project"))
        self.assertEqual(self.errors, [])

    def test_restore_form_rejects_existing_or_escaping_destination(self):
        review = {"name": "Backup", "created_at": "2026", "files": 2, "bytes": 100, "verified_index": True, "path": "source", "hash": "hash"}
        dialog = RestoreDialog(review, self.window)
        submissions = []
        dialog.operation_requested.connect(lambda *args: submissions.append(args))
        dialog.parent_path.setText(str(self.directory))
        dialog.folder.setText("../escape")
        dialog.restore()
        self.assertEqual(submissions, [])
        dialog.folder.setText(self.directory.name)
        dialog.parent_path.setText(str(self.directory.parent))
        dialog.restore()
        self.assertEqual(submissions, [])
        dialog.reject()

    def test_restore_cancel_stays_accessible_and_diagnostic_runs_without_project(self):
        report_path = self.action_result("diagnostic_export", {"directory": str(self.directory)})
        self.assertTrue(Path(report_path).is_file())
        review = {"name": "Backup", "created_at": "2026", "files": 2, "bytes": 100, "verified_index": True, "path": "source", "hash": "hash"}
        dialog = RestoreDialog(review, self.window)
        cancellations = []
        dialog.operation_cancel_requested.connect(lambda: cancellations.append(True))
        dialog.set_busy(True)
        self.assertFalse(dialog.restore_button.isEnabled())
        self.assertTrue(dialog.close_button.isEnabled())
        dialog.close_button.click()
        self.assertEqual(cancellations, [True])
        dialog.set_busy(False)
        self.assertTrue(dialog.restore_button.isEnabled())
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
