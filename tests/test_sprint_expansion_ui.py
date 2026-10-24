"""Qt integration for defaults, bulk policies, durable documents and presentation."""

from copy import deepcopy
from contextlib import closing
import unittest
from unittest.mock import patch
import test_ui as harness
import test_builder_ui as builder_harness
from test_sprint_expansion import simple_docx

if harness.QT_AVAILABLE:
    from PySide6.QtCore import QTime
    from PySide6.QtWidgets import QMessageBox
    from emailcenter.ui.project_settings_dialog import ProjectSettingsDialog
    from emailcenter.preferences import Preferences
    from emailcenter.database import connect


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class ExpansionDesktopTests(unittest.TestCase):
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
    delivery_fixture = harness.DesktopTests.delivery_fixture
    approve_delivery = harness.DesktopTests.approve_delivery
    builder = builder_harness.BuilderDesktopTests.builder
    sources = builder_harness.BuilderDesktopTests.sources

    def db(self):
        return connect(self.directory / "project/emailcenter.sqlite3")

    def test_edit_project_defaults_are_used_by_new_application_and_mail(self):
        self.open_test_project()
        self.submit("create_record", {"entity": "applicants", "fields": {"display_name": "Timon"}})
        self.window.workspace_action("project_settings", None)
        self.wait_idle()
        dialog = self.window._record_dialog
        self.assertIsInstance(dialog, ProjectSettingsDialog)
        dialog.goal.setPlainText("Gezielte Bewerbungen")
        dialog.controls["applicant_profile_id"].setCurrentIndex(1)
        dialog.format.setCurrentIndex(1)
        dialog.save()
        self.wait_idle()
        self.assertIsNone(self.window._record_dialog)
        self.assertEqual(self.window.pages["workspace"].goal.text(), "Gezielte Bewerbungen")
        self.window.create_record("applications")
        self.wait_idle()
        self.assertIsNotNone(self.window._record_dialog.fields["applicant_profile_id"].currentData())
        self.window._record_dialog.reject()
        self.submit("mail_compose_details", {})
        self.assertEqual(self.window._mail_dialog.format.currentData(), "html")
        self.window._mail_dialog.reject()

    def test_wizard_overrides_and_copies_profile_template_and_list(self):
        self.open_test_project()
        self.submit("create_record", {"entity": "applicants", "fields": {"display_name": "Timon", "email": "timon@example.test"}})
        source = self.directory / "setup.docx"
        simple_docx(source)
        self.submit("import_template", {"source_path": str(source), "name": "Standard", "mapping": {}, "required_placeholders": []})
        self.submit("source_list_save", {"name": "Empfänger", "rows": [{"fields": {"contact.display_name": "Ada", "contact.email": "ada@example.test"}}]})
        self.window.create_project()
        self.wait_idle()
        dialog = self.window._project_dialog
        dialog.fields["name"].setText("Nachfolge")
        dialog.fields["folder"].setText("configured")
        dialog.parent_path.setText(str(self.directory))
        dialog.next()
        dialog.add_profile.setChecked(True)
        dialog.profile_choice.setCurrentIndex(1)
        dialog.document_choice.setCurrentIndex(1)
        dialog.source_choice.setCurrentIndex(1)
        dialog.body_format.setCurrentIndex(1)
        dialog.account_email.setCurrentText("sender@example.test")
        dialog.next()
        self.assertIn("Standard", dialog.summary.toPlainText())
        dialog.accept()
        self.wait_idle()
        self.assertEqual(self.window.snapshot["name"], "Nachfolge")
        values = self.window.snapshot["project_settings"]["defaults"]
        self.assertTrue(values["document_version_id"])
        self.assertTrue(values["source_list_id"])
        self.assertEqual(values["account_email"], "sender@example.test")
        self.assertEqual(self.window.pages["workspace"].templates.currentData()["id"], values["document_version_id"])

    def test_default_recipient_list_loads_into_bulk(self):
        self.open_test_project()
        self.submit("source_list_save", {"name": "Standardliste", "rows": [{"fields": {"contact.display_name": "Ada", "contact.email": "ada@example.test"}}]})
        with closing(self.db()) as db:
            list_id = db.execute("SELECT id FROM data_source_lists").fetchone()[0]
        settings = self.window.snapshot["project_settings"]
        self.submit("project_setup_save", {"goal": "", "mode": "mail", "defaults": {"source_list_id": list_id}, "expected_version": settings["version"]})
        self.submit("mail_bulk_details", {})
        dialog = self.window._bulk_dialog
        self.wait_for(lambda: len(dialog.selected) == 1)
        self.wait_idle()
        self.assertEqual(dialog.recipient.count(), 1)
        dialog.reject()

    def test_bulk_collection_and_per_row_template_controls(self):
        self.open_test_project()
        source = self.directory / "row.docx"
        simple_docx(source)
        self.submit("import_template", {"source_path": str(source), "name": "Persönlich", "mapping": {"NAME": "contact.display_name"}, "required_placeholders": ["NAME"]})
        dialog, _, _ = self.bulk_fixture()
        self.assertEqual(len(dialog.selected), 2)
        identifier = dialog.recipient.currentData()
        dialog.personal_document.setCurrentIndex(2)
        dialog.new_application.setChecked(True)
        dialog.request_preview()
        self.wait_idle()
        row = next(r for r in dialog.preview["rows"] if r["contact_id"] == identifier)
        self.assertTrue(row.get("new_application"))
        self.assertTrue(row.get("generated_document"))
        self.submit("recipient_library_save", {"kind": "group", "name": "Partner", "contact_ids": sorted(dialog.selected)})
        dialog.group_filter.setCurrentIndex(1)
        self.assertEqual(dialog.contacts.count(), 2)
        dialog.search.setText("Ada")
        self.submit("recipient_library_save", {"kind": "filter", "name": "Nur Ada", "configuration": {"search": "Ada", "group_id": dialog.group_filter.currentData(), "valid_only": True}})
        dialog.search.clear()
        dialog.saved_filter.setCurrentIndex(1)
        dialog.apply_filter()
        self.assertEqual(dialog.contacts.count(), 1)
        self.assertEqual(len(dialog.selected), 2)
        dialog.reject()

    def test_bulk_background_window_can_close_and_workspace_can_pause(self):
        bulk, delivery = self.delivery_fixture(scheduled=True)
        self.approve_delivery(delivery)
        delivery.background.setChecked(True)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            delivery.start()
        self.wait_idle()
        self.assertEqual(delivery.dispatch["status"], "Running")
        self.assertFalse(delivery.auto)
        self.assertTrue(delivery.dispatch["background"])
        group_id = delivery.dispatch["id"]
        delivery.reject()
        self.assertIsNone(self.window._bulk_delivery_dialog)
        bulk.reject()
        self.window.navigate("workspace")
        self.wait_idle()
        page = self.window.pages["workspace"]
        self.assertTrue(page.bulk_panel.isVisible())
        group = next(g for g in self.window._background_groups if g["id"] == group_id)
        self.window.workspace_action("bulk_pause", group)
        self.wait_idle()
        self.assertEqual(next(g for g in self.window._background_groups if g["id"] == group_id)["status"], "Paused")
        self.assertEqual(self.fake_provider.sent, [])

    def test_bulk_delivery_buttons_wrap_in_small_dialog(self):
        bulk, delivery = self.delivery_fixture()
        delivery.resize(760, 620)
        self.application.processEvents()
        self.assertLessEqual(delivery.skip_button.mapTo(delivery, delivery.skip_button.rect().bottomRight()).x(), delivery.width())
        self.assertLess(delivery.close_button.mapTo(delivery, delivery.close_button.rect().bottomRight()).y(), delivery.height())
        self.assertTrue(delivery.close_button.isVisible())
        delivery.reject()
        bulk.reject()

    def test_word_replace_saved_run_pause_load_resume_through_ui(self):
        self.open_test_project()
        self.window.navigate("word_replace")
        self.wait_idle()
        page = self.window.pages["word_replace"]
        source = self.directory / "replace.docx"
        simple_docx(source)
        page.source_path.setText(str(source))
        page.add_rule(find="{{NAME}}", replacement="Ada")
        page.filename_pattern.setText("{prefix}-{number:03d}")
        page.request_preview()
        self.wait_idle()
        page.confirm.setChecked(True)
        def hold(action, value):
            if action == "word_replace_create":
                page.auto_run = False
        self.window.controller.completed.connect(hold)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            page.create()
        self.wait_idle()
        self.window.controller.completed.disconnect(hold)
        self.assertEqual(page.run["completed"], 0)
        self.assertEqual(page.run["status"], "Paused")
        page.request_load()
        self.wait_idle()
        self.assertEqual(page.run_history.count(), 1)
        page.load_run()
        self.wait_idle()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            page.resume_run()
        self.wait_for(lambda: page.run["status"] == "Completed")
        self.wait_idle()
        self.assertEqual(page.run_progress.value(), 1)
        self.assertFalse(page.resume_button.isEnabled())
        self.assertTrue(page.run["items"][0]["output_path"].endswith("Dokument-001.docx"))

    def test_builder_panels_compact_tools_and_policy_are_persisted(self):
        page = self.builder()
        graph = deepcopy(page.graph)
        page.toggle_panel("builder_show_inspector")
        self.assertTrue(page.inspector_pane.isHidden())
        page.toggle_panel("builder_show_inspector")
        page.toggle_panel("builder_compact_tools")
        self.assertEqual(page.undo_button.text(), "↶")
        page.daily_budget.setValue(25)
        page.window_start.setTime(QTime(9, 0))
        page.window_end.setTime(QTime(17, 0))
        state = page.work_state()
        self.assertEqual(state["daily_budget"], 25)
        self.assertEqual(state["window_start"], "09:00")
        self.assertEqual(page.graph, graph)
        page.save_panel_sizes()
        loaded, warning = self.window.settings_store.load()
        self.assertIsNone(warning)
        self.assertTrue(loaded.builder_compact_tools)

    def test_motion_disabled_preserves_focus_and_theme_and_error_toast(self):
        self.open_test_project()
        values = {**self.window.preferences.values(), "reduced_motion": True, "toast_seconds": 12}
        self.window.save_preferences(values)
        self.window.navigate("builder")
        self.wait_idle()
        page = self.window.pages["builder"]
        page.name.setFocus()
        self.window.toggle_theme()
        self.assertIs(self.application.focusWidget(), page.name)
        self.assertIsNone(self.window.page_transition.effect)
        self.window.toast.notify("Fehler", "Bitte Eingaben prüfen", category="error")
        self.assertFalse(self.window.toast.timer.isActive())
        self.window.toast.notify("Erfolg", "Neue Meldung")
        self.assertEqual(self.window.toast.message.text(), "Bitte Eingaben prüfen")
        self.window.toast.dismiss()
        self.window.toast.notify("Info", "Hinweis", category="info")
        self.assertEqual(self.window.toast.timer.interval(), 12000)
        self.assertEqual(self.window.toast.effect.opacity(), 1)

    def test_new_preferences_controls_save_and_keep_custom_word_fields(self):
        self.window.navigate("settings")
        page = self.window.pages["settings"]
        page.controls["word_replace_filename_pattern"].setText("{prefix}-{number:03d}-{name}")
        page.controls["word_replace_style"].setCurrentIndex(2)
        page.controls["toast_info"].setChecked(False)
        page.controls["builder_inspector_width"].setValue(480)
        page.save_button.click()
        self.assertEqual(self.window.preferences.word_replace_style, "bold")
        self.assertFalse(self.window.preferences.toast_info)
        self.assertEqual(self.window.pages["word_replace"].replacement_style.currentData(), "bold")
        self.assertEqual(self.window.pages["word_replace"].filename_pattern.text(), "{prefix}-{number:03d}-{name}")

    def test_background_sends_reviewed_group_after_both_dialogs_close(self):
        self.window.bulk_timer.stop()
        bulk, delivery = self.delivery_fixture()
        self.approve_delivery(delivery)
        delivery.background.setChecked(True)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.StandardButton.Yes):
            delivery.start()
        self.wait_idle()
        delivery.reject()
        self.wait_idle()
        bulk.reject()
        self.window.navigate("workspace")
        self.wait_idle()
        for _ in range(4):
            if self.fake_provider.sent:
                break
            self.window.bulk_background_tick()
            self.wait_idle()
        self.assertEqual(len(self.fake_provider.sent),1)
        self.assertIsNone(self.window._bulk_delivery_dialog)
        self.assertTrue(self.window.navigation.isEnabled())
        group = next(g for g in self.window._background_groups if g["status"] == "Running")
        self.window.workspace_action("bulk_pause",group)
        self.wait_idle()
        self.window.bulk_background_tick()
        self.wait_idle()
        self.assertEqual(len(self.fake_provider.sent),1)

    def test_busy_dialog_cancel_is_usable_and_restores_disabled_controls(self):
        from emailcenter.ui.mail_template_dialogs import BusyDialog
        from PySide6.QtWidgets import QVBoxLayout, QPushButton
        dialog = BusyDialog(self.window)
        layout = QVBoxLayout(dialog)
        editable, disabled = QPushButton("Eingabe"), QPushButton("Gesperrt")
        disabled.setEnabled(False)
        layout.addWidget(editable)
        layout.addWidget(disabled)
        requests=[]
        dialog.operation_cancel_requested.connect(lambda: requests.append(True))
        dialog.show()
        self.window.setEnabled(False)
        dialog.set_busy(True)
        self.window.setEnabled(True)
        self.assertTrue(dialog.operation_cancel_button.isEnabled())
        self.assertFalse(editable.isEnabled())
        dialog.operation_cancel_button.click()
        self.assertEqual(requests,[True])
        dialog.set_busy(False)
        self.assertTrue(editable.isEnabled())
        self.assertFalse(disabled.isEnabled())
        dialog.reject()

    def test_builder_condition_and_merge_have_editable_properties_and_row_previews(self):
        from emailcenter.email_builder import node
        page=self.builder()
        self.sources(page)
        data, subject, text, email=page.graph["nodes"]
        condition, merge=node("condition"),node("merge")
        condition["config"]["no"]="Leer"
        merge["config"]["separator"]=" · "
        graph=deepcopy(page.graph)
        graph["nodes"].extend((condition,merge))
        graph["edges"]=[e for e in graph["edges"] if not(e["to"]==email["id"] and e["input"]=="body")]
        def edge(a,port,b,target):
            return {"from":a["id"],"output":port,"to":b["id"],"input":target}
        graph["edges"].extend((edge(data,"values",condition,"values"),edge(text,"text",condition,"yes"),edge(condition,"text",merge,"parts"),edge(merge,"text",email,"body")))
        page.commit(graph,condition["id"])
        from PySide6.QtWidgets import QLineEdit
        self.assertIsNotNone(page.properties.widget().findChild(QLineEdit,"condition_field"))
        page.request_preview()
        self.wait_idle()
        self.assertTrue(page.preview["ready"])
        self.assertEqual(page.preview["rows"][0]["node_previews"][condition["id"]]["branch"],"yes")
        page.scene.clearSelection()
        page.scene.cards[merge["id"]].setSelected(True)
        self.application.processEvents()
        from PySide6.QtWidgets import QPlainTextEdit
        separator=page.properties.widget().findChild(QPlainTextEdit,"merge_separator")
        self.assertIsNotNone(separator)
        separator.setPlainText(" / ")
        self.assertIsNone(page.preview)
        self.assertEqual(next(n for n in page.graph["nodes"] if n["id"]==merge["id"])["config"]["separator"]," / ")

    def test_mail_actions_wrap_at_minimum_main_window_size(self):
        self.open_test_project()
        self.window.resize(820,600)
        self.window.navigate("mail")
        self.wait_idle()
        page=self.window.pages["mail"]
        self.application.processEvents()
        for key in ("new","edit","signature","sync","prepare"):
            widget=page.buttons[key]
            point=widget.mapTo(page,widget.rect().bottomRight())
            self.assertLessEqual(point.x(),page.width())
        self.assertGreater(page.buttons["prepare"].y(),page.buttons["new"].y())

    def test_disabling_persistent_errors_restarts_toast_timer(self):
        self.window.toast.notify("Fehler","Prüfen",category="error")
        preferences=Preferences.validate({**self.window.preferences.values(),"toast_persistent_errors":False})
        self.window.toast.configure(preferences)
        self.assertTrue(self.window.toast.timer.isActive())

    def test_workspace_bulk_and_context_follow_mode_without_page_switch(self):
        self.open_test_project()
        page=self.window.pages["workspace"]
        self.assertEqual(page.context_kind.currentData(),"applications")
        page.buttons["bulk"].click()
        self.wait_idle()
        self.assertIsNotNone(self.window._bulk_dialog)
        self.assertIs(self.window.current_page(),page)
        self.window._bulk_dialog.reject()
        self.submit("set_workspace_mode",{"mode":"mail"})
        self.assertEqual(page.context_kind.currentData(),"contacts")
        self.assertEqual(page.buttons["bulk"].text(),"Bulk-E-Mails vorbereiten")

    def test_preferred_account_and_format_apply_to_new_builder_with_multiple_accounts(self):
        self.open_test_project()
        self.enable_fake_gmail()
        self.fake_provider.email="second@example.test"
        with patch("emailcenter.application.workspace.MailService.connect_gmail",new=lambda service,client_path:service.register_account("second@example.test",{"refresh_token":"fake"})):
            account=self.action_result("mail_connect",{"client_path":"fake-only"})
        settings=self.window.snapshot["project_settings"]
        self.submit("project_setup_save",{"goal":"", "mode":"mail", "defaults":{**settings["defaults"],"account_email":"second@example.test","body_format":"html"},"expected_version":settings["version"]})
        self.window.navigate("builder")
        self.wait_idle()
        page=self.window.pages["builder"]
        self.assertEqual(page.account.currentData(),account["id"])
        self.assertEqual(next(n for n in page.graph["nodes"] if n["kind"]=="email")["config"]["body_format"],"html")


if __name__ == "__main__":
    unittest.main()
