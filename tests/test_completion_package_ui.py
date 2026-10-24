"""Combined UI flows and configurable keyboard-only builder connections."""

from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ui as harness
import test_builder_ui as builder_harness
from test_completion_package import table_docx

if harness.QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox, QTableWidgetItem
    from emailcenter.preferences import Preferences
    from emailcenter.ui.mail_template_dialogs import MailTemplateEditor, MailTemplatePreview
    from emailcenter.ui.document_table_dialog import DocumentTableDialog
    from emailcenter.ui.bulk_source_dialogs import ManualRowsDialog
    from emailcenter.ui.template_page import TemplatePage


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class CompletionDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = builder_harness.BuilderDesktopTests.builder

    def test_logo_and_unified_template_page_filter_actions_and_duplicate(self):
        self.assertFalse(self.window.brand_logo.pixmap().isNull())
        self.assertEqual(self.window.brand_logo.pixmap().width(), 64)
        self.assertFalse(self.window.windowIcon().isNull())
        self.open_test_project()
        path = self.directory / "template.docx"
        harness._make_docx(path)
        self.submit("import_template", {"source_path": str(path), "name": "Beispiel", "mapping": {}, "required_placeholders": []})
        self.submit("mail_template_save", {"name": "Beispiel Mail", "subject": "Betreff", "body": "Text"})
        self.window.navigate("templates")
        self.wait_idle()
        page = self.window.pages["templates"]
        self.assertIsInstance(page, TemplatePage)
        self.assertEqual(page.total, 2)
        index = next(i for i, row in enumerate(page.rows) if row["template_type"] == "document")
        page.table.selectRow(index)
        self.assertTrue(page.action_buttons["generate"][0].isEnabled())
        self.assertFalse(page.action_buttons["edit_mail_template"][0].isEnabled())
        page.action_buttons["duplicate_template"][0].click()
        self.wait_idle()
        self.assertEqual(page.total, 3)
        page.type_filter.setCurrentIndex(page.type_filter.findData("email"))
        self.wait_idle()
        self.assertEqual(page.total, 1)
        page.table.selectRow(0)
        self.assertFalse(page.action_buttons["generate"][0].isEnabled())
        page.action_buttons["edit_mail_template"][0].click()
        self.wait_idle()
        editor = self.window._template_editor
        self.assertIsNotNone(editor)
        editor.subject.setText("Geändert")
        editor.save()
        self.wait_idle()
        self.assertEqual(page.total, 2)

    def test_template_renderer_live_html_resources_blocked_and_preview_gate(self):
        editor = MailTemplateEditor(parent=self.window)
        editor.format.setCurrentIndex(editor.format.findData("html"))
        editor.subject.setText("Hallo")
        editor.body.setPlainText('<h2>Nachricht</h2><p>Persönlicher Text</p><img src="https://example.test/tracker">')
        self.assertIn("Nachricht", editor.rendered.body.text.toPlainText())
        self.assertNotIn("<h2>", editor.rendered.body.text.toPlainText())
        editor.reject()
        value = {"name": "HTML", "version_number": 1, "subject": "Ada", "body": "<b>Hallo Ada</b>", "body_format": "html",
                 "placeholders": ["NAME"], "values": {"NAME": "Ada"}, "missing": []}
        dialog = MailTemplatePreview(value, {}, self.window)
        self.assertEqual(dialog.rendered.body.text.toPlainText(), "Hallo Ada")
        dialog.confirm.setChecked(True)
        self.assertTrue(dialog.apply_button.isEnabled())
        dialog.fields["NAME"].setPlainText("Grace")
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.reject()

    def test_document_table_review_preserves_raw_values_and_source_then_saves_shared_list(self):
        page = self.builder()
        self.window.open_builder_source("manual")
        parent = self.window._bulk_source_dialog
        path = self.directory / "rows.docx"
        table_docx(path)
        self.submit("source_document_tables", {"path": str(path)})
        dialog = parent.table_review
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.mapping[0].setCurrentIndex(dialog.mapping[0].findData("contact.display_name"))
        dialog.mapping[1].setCurrentIndex(dialog.mapping[1].findData("contact.email"))
        dialog.confirm.setChecked(True)
        dialog.apply_button.click()
        entries = parent.capture_rows()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["fields"]["contact.email"], "ada@example.test")
        self.assertEqual(entries[0]["fields"]["document.column_1"], "Ada")
        self.assertEqual(entries[0]["fields"]["source.filename"], "rows.docx")
        parent.list_name.setText("Dokumentdaten")
        parent.save_list()
        self.wait_idle()
        parent.apply()
        self.wait_idle()
        sources = page.graph["nodes"][0]["config"]["sources"]
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["kind"], "list")

    def test_review_custom_field_duplicate_mapping_and_row_capacity(self):
        value = {"filename": "rows.pdf", "sha256": "a" * 64, "tables": [{"title": "PDF Seite 1", "page": 1, "warnings": ["unsicher"], "rows": [["Name", "Adresse"], ["Ada", "a@example.test"], ["Grace", "g@example.test"]]}]}
        dialog = DocumentTableDialog(value, ["contact.email"], self.window, capacity=1)
        dialog.confirm.setChecked(True)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.table.clearSelection()
        dialog.table.selectRow(0)
        dialog.mapping[0].setEditText("custom.person")
        dialog.mapping[1].setCurrentIndex(dialog.mapping[1].findData("contact.email"))
        dialog.confirm.setChecked(True)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(dialog.mapped_rows()[0]["custom.person"], "Ada")
        dialog.mapping[0].setCurrentIndex(dialog.mapping[0].findData("contact.email"))
        with self.assertRaises(ValueError):
            dialog.mapped_rows()
        self.assertFalse(dialog.confirm.isChecked())
        dialog.reject()

    def test_document_bundle_dialog_warning_gate_and_real_zip(self):
        self.open_test_project()
        path = self.directory / "template.docx"
        harness._make_docx(path)
        self.submit("import_template", {"source_path": str(path), "name": "Dokument", "mapping": {}, "required_placeholders": []})
        version = self.window.snapshot["workspace_templates"][0]
        self.submit("generate_document", {"template_version_id": version["id"], "values": {"NAME": "Ada"}, "output_filename": "Dokument.docx"})
        self.window.open_document_bundle()
        self.wait_idle()
        dialog = self.window._export_dialog
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertIn("PDF-Version fehlt", dialog.report.toPlainText())
        dialog.confirm.setChecked(True)
        self.assertTrue(dialog.export_button.isEnabled())
        target = self.directory / "export.zip"
        with patch("emailcenter.ui.document_bundle_dialog.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            dialog.export_button.click()
        self.wait_idle()
        self.assertTrue(target.is_file())
        self.assertIn("Dateien exportiert", dialog.report.toPlainText())
        dialog.reject()
        self.window.open_export()
        self.wait_idle()
        self.window.switch_document_bundle()
        self.wait_idle()
        self.assertEqual(self.window._export_dialog.windowTitle(), "Dokumentensätze exportieren")
        self.window._export_dialog.reject()

    def test_canvas_keyboard_connect_select_delete_undo_and_cancel(self):
        page = self.builder()
        graph = deepcopy(page.graph)
        graph["edges"] = []
        page.commit(graph)
        view = page.view
        view.setFocus()
        QTest.keyClick(view, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(page.selected_id, graph["nodes"][0]["id"])
        QTest.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(view.keyboard_port[1], ("email", True))
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.assertIsNotNone(page.scene.pending)
        for _ in range(3):
            QTest.keyClick(view, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(view.keyboard_port[1], ("recipient", False))
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.application.processEvents()
        self.assertEqual(len(page.graph["edges"]), 1)
        QTest.keyClick(view, Qt.Key.Key_E, Qt.KeyboardModifier.AltModifier)
        self.assertTrue(page.scene.lines[0].isSelected())
        QTest.keyClick(view, Qt.Key.Key_Delete)
        self.assertEqual(page.graph["edges"], [])
        QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(page.graph["edges"]), 1)
        QTest.keyClick(view, Qt.Key.Key_Escape)
        self.assertIsNone(page.scene.pending)
        self.assertIsNone(view.keyboard_port)

    def test_canvas_changed_disabled_shortcuts_and_text_editor_focus(self):
        page = self.builder()
        page.view.setFocus()
        page.view.cycle_node(1)
        page.view.cycle_node(1)
        original = deepcopy(page.graph)
        preferences = Preferences.validate({**self.window.preferences.values(), "canvas_shortcuts": {"duplicate": "Alt+D", "delete": ""}})
        page.apply_settings(preferences)
        QTest.keyClick(page.view, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(page.view, Qt.Key.Key_Delete)
        self.assertEqual(page.graph, original)
        QTest.keyClick(page.view, Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(len(page.graph["nodes"]), len(original["nodes"]) + 1)
        count = len(page.graph["nodes"])
        page.name.setFocus()
        QTest.keyClick(page.name, Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(len(page.graph["nodes"]), count)
        page.busy = True
        QTest.keyClick(page.view, Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(len(page.graph["nodes"]), count)
        page.busy = False

    def test_settings_canvas_controls_conflicts_save_and_help(self):
        page = self.window.pages["settings"]
        page.canvas_controls["connect"].setText("Ctrl+N")
        self.assertIn("bereits", page.state.text())
        page.canvas_controls["connect"].setText("Alt+M")
        page.save_button.click()
        self.assertEqual(self.window.preferences.canvas_shortcuts["connect"], "Alt+M")
        self.assertEqual(self.window.pages["builder"].preferences.canvas_shortcuts["connect"], "Alt+M")
        with patch.object(QMessageBox, "information") as help_message:
            self.window.shortcut_help()
        self.assertIn("Alt+M", help_message.call_args.args[2])

    def test_graph_export_import_cancel_preserves_editor_then_import_resets_delivery(self):
        page = self.builder()
        graph = deepcopy(page.graph)
        graph["nodes"][0]["config"]["sources"] = [{"kind": "manual", "fields": {"contact.email": "private@example.test"}}]
        page.commit(graph)
        page.save()
        self.wait_idle()
        version = page.version_id
        path = self.directory / "graph.json"
        with patch("emailcenter.ui.email_builder_page.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            page.export_graph()
        self.wait_idle()
        self.assertTrue(path.exists())
        self.assertEqual(page.graph, graph)
        self.assertEqual(page.version_id, version)
        page.name.setText("Ungespeicherte Eingaben")
        page.last_batch = "previous-batch"
        with patch("emailcenter.ui.email_builder_page.QFileDialog.getOpenFileName", return_value=(str(path), "")), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            page.import_graph()
            self.wait_idle()
        self.assertEqual(page.name.text(), "Ungespeicherte Eingaben")
        self.assertEqual(page.last_batch, "previous-batch")
        with patch("emailcenter.ui.email_builder_page.QFileDialog.getOpenFileName", return_value=(str(path), "")), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            page.import_graph()
            self.wait_idle()
        self.assertEqual(page.graph["nodes"][0]["config"]["sources"], [])
        self.assertIsNone(page.builder_id)
        self.assertIsNone(page.version_id)
        self.assertIsNone(page.last_batch)
        self.assertEqual(page.delivery_mode.currentData(), "drafts")
        self.assertIsNone(page.preview)
        self.assertFalse(page.create_button.isEnabled())
        page.save()
        self.wait_idle()
        self.assertNotEqual(page.version_id, version)

    def test_graph_import_error_leaves_graph_name_and_selection_untouched(self):
        page = self.builder()
        page.view.cycle_node(1)
        selected = page.selected_id
        graph = deepcopy(page.graph)
        path = self.directory / "invalid.json"
        path.write_text('{"bad":true}')
        with patch("emailcenter.ui.email_builder_page.QFileDialog.getOpenFileName", return_value=(str(path), "")):
            page.import_graph()
        self.wait_idle()
        self.assertEqual(len(self.errors), 1)
        self.errors.clear()
        self.assertEqual(page.graph, graph)
        self.assertEqual(page.selected_id, selected)
