"""Qt integration for the typed canvas and the existing source/delivery dialogs."""

from copy import deepcopy
from pathlib import Path
import os
import unittest
from unittest.mock import patch

import test_ui as harness

if harness.QT_AVAILABLE:
    from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    from emailcenter.email_builder import node, starter_graph
    from emailcenter.ui.email_builder_page import MIME, NodeCard
    from emailcenter.preferences import Preferences


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class BuilderDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    enable_fake_gmail = harness.DesktopTests.enable_fake_gmail

    def builder(self):
        self.open_test_project()
        self.window.navigate("builder")
        self.wait_idle()
        return self.window.pages["builder"]

    def sources(self, page):
        page.add_sources({"contacts": [{"source": {"kind": "manual", "fields": {"contact.display_name": "Ada", "contact.email": "ada@example.test", "company.name": "Ada GmbH", "application.cover_letter": "Mein Anschreiben"}}, "source_values": {}}]})

    def test_project_only_navigation_and_workspace_action(self):
        page = self.window.pages["builder"]
        self.assertFalse(page.isEnabled())
        self.assertTrue(self.window.navigation.item(self.window.page_order.index("builder")).isHidden())
        self.open_test_project()
        self.window.workspace_action("builder", None)
        self.wait_idle()
        self.assertIs(self.window.current_page(), page)
        self.assertEqual(len(page.scene.cards), 4)
        self.assertLessEqual(page.tabs.height(), 320)
        self.assertEqual(page.scroll.verticalScrollBar().maximum(), 0)
        self.submit("close_project", {})
        self.assertFalse(page.isEnabled())
        self.assertEqual(page.graph["nodes"][0]["config"]["sources"], [])

    def test_save_hotkey_load_version_and_theme_preserve_graph(self):
        page = self.builder()
        self.sources(page)
        graph = deepcopy(page.graph)
        self.window.trigger_hotkey("save")
        self.wait_idle()
        self.assertTrue(page.builder_id)
        self.assertTrue(page.version_id)
        self.assertEqual(page.graph, graph)
        first = page.version_id
        page.name.setText("Umbenannt")
        page.save_button.click()
        self.wait_idle()
        self.assertNotEqual(first, page.version_id)
        self.assertEqual(page.versions.count(), 2)
        page.versions.setCurrentIndex(page.versions.findData(first))
        page.load_button.click()
        self.wait_idle()
        self.assertEqual(page.version_id, first)
        self.window.toggle_theme()
        self.assertEqual(page.graph, graph)

    def test_canvas_add_move_duplicate_delete_undo_redo(self):
        page = self.builder()
        page.add_node("file", 112, 116)
        self.assertEqual(len(page.graph["nodes"]), 5)
        card = page.scene.cards[page.graph["nodes"][-1]["id"]]
        card.setPos(167, 191)
        page.capture_positions()
        self.assertEqual(page.graph["nodes"][-1]["x"], 160)
        self.assertEqual(page.graph["nodes"][-1]["y"], 200)
        card.setSelected(True)
        page.view.setFocus()
        QTest.keyClick(page.view, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(page.graph["nodes"]), 6)
        page.undo()
        self.assertEqual(len(page.graph["nodes"]), 5)
        page.redo()
        self.assertEqual(len(page.graph["nodes"]), 6)
        page.scene.cards[page.graph["nodes"][-1]["id"]].setSelected(True)
        QTest.keyClick(page.view, Qt.Key.Key_Delete)
        self.assertEqual(len(page.graph["nodes"]), 5)

    def test_real_port_clicks_connect_and_bad_type_preserves_graph(self):
        page = self.builder()
        graph = deepcopy(page.graph)
        edge = graph["edges"].pop()
        page.commit(graph)
        page.fit()
        source = page.scene.cards[edge["from"]].ports[(edge["output"], True)]
        target = page.scene.cards[edge["to"]].ports[(edge["input"], False)]
        QTest.mouseClick(page.view.viewport(), Qt.MouseButton.LeftButton, pos=page.view.mapFromScene(source.scenePos()))
        QTest.mouseClick(page.view.viewport(), Qt.MouseButton.LeftButton, pos=page.view.mapFromScene(target.scenePos()))
        self.application.processEvents()
        self.assertIn(edge, page.graph["edges"])
        before = deepcopy(page.graph)
        data = page.scene.cards[page.graph["nodes"][0]["id"]].ports[("values", True)]
        email = page.scene.cards[page.graph["nodes"][3]["id"]].ports[("subject", False)]
        page.connect_ports(data, email)
        self.application.processEvents()
        self.assertEqual(page.graph, before)
        self.assertIn("Unpassende", page.status.text())

    def test_palette_drop_and_local_file_drop_confirmation(self):
        page = self.builder()
        mime = QMimeData()
        mime.setData(MIME, b"file")
        point = page.view.viewport().rect().center()
        enter = QDragEnterEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.application.sendEvent(page.view.viewport(), enter)
        drop = QDropEvent(QPointF(point), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.application.sendEvent(page.view.viewport(), drop)
        self.assertEqual(len(page.graph["nodes"]), 5)
        file = self.directory / "attachment.pdf"
        file.write_bytes(b"%PDF-1.4\nexample")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            page.drop_files([str(file)], QPointF(200, 200))
        self.assertEqual(page.graph["nodes"][-1]["kind"], "pdf")
        self.assertEqual(page.graph["nodes"][-1]["config"]["path"], str(file.resolve()))
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            page.drop_files([str(file)], QPointF(200, 200))
        self.assertEqual(len(page.graph["nodes"]), 6)

    def test_source_dialog_routes_to_builder_and_local_group_opens_review(self):
        page = self.builder()
        self.window.open_builder_source("manual")
        dialog = self.window._bulk_source_dialog
        self.assertIsNotNone(dialog)
        self.assertEqual(self.window._source_owner, "builder")
        self.sources(page)
        dialog.reject()
        page.preview_button.click()
        self.wait_idle()
        self.assertTrue(page.preview["ready"])
        self.assertFalse(page.create_button.isEnabled())
        page.confirm.setChecked(True)
        self.assertTrue(page.create_button.isEnabled())
        screenshot = os.environ.get("EMAILCENTER_BUILDER_SCREENSHOT_PATH")
        if screenshot:
            self.window.toast.dismiss()
            page.scene.clearSelection()
            page.inspector.setCurrentIndex(1)
            page.fit()
            self.application.processEvents()
            self.window.grab().save(screenshot)
            self.window.toggle_theme()
            self.application.processEvents()
            target = Path(screenshot)
            self.window.grab().save(str(target.with_name(target.stem + "_dark" + target.suffix)))
            self.window.toggle_theme()
        page.create_button.click()
        self.wait_idle()
        self.assertTrue(page.last_batch)
        self.assertTrue(page.delivery_button.isEnabled())
        page.delivery_button.click()
        self.wait_idle()
        review = self.window._bulk_delivery_dialog
        self.assertEqual(review.data["batch"]["id"], page.last_batch)
        self.assertIsNone(review.dispatch)
        review.reject()
        self.assertEqual(self.errors, [])

    def test_word_rule_typing_and_preview_invalidation(self):
        page = self.builder()
        page.add_node("replace")
        table = page.rule_table
        table.insertRow(0)
        from PySide6.QtWidgets import QTableWidgetItem
        table.setItem(0, 0, QTableWidgetItem("{{NAME}}"))
        table.setItem(0, 2, QTableWidgetItem("contact.display_name"))
        self.assertEqual(page.graph["nodes"][-1]["config"]["rules"][0]["field"], "contact.display_name")
        self.assertEqual(table.item(0, 0).text(), "{{NAME}}")
        page.delete_selected()
        self.sources(page)
        page.request_preview()
        self.wait_idle()
        page.confirm.setChecked(True)
        self.assertTrue(page.create_button.isEnabled())
        page.account.addItem("Test", "unconnected")
        page.account.setCurrentIndex(1)
        self.assertIsNone(page.preview)
        self.assertFalse(page.confirm.isChecked())

    def test_settings_apply_zoom_and_busy_cancel_footer_reachable(self):
        page = self.builder()
        preferences = Preferences.validate({**self.window.preferences.values(), "builder_zoom": 150, "builder_grid": False, "builder_snap": False})
        self.window.save_preferences(preferences.values())
        self.assertEqual(page.view.transform().m11(), 1.5)
        self.assertFalse(page.preferences.builder_grid)
        self.window.resize(820, 600)
        self.application.processEvents()
        self.assertEqual(self.window.height(), 600)
        self.assertEqual(self.window.width(), 820)
        self.assertFalse(page.palette.isVisible())
        self.assertTrue(page.footer.isVisible())
        bottom = page.create_button.mapTo(page, page.create_button.rect().bottomRight())
        self.assertLessEqual(bottom.y(), page.height())
        self.window.controller.current_action = "builder_preview"
        self.window.set_busy(True)
        self.assertTrue(page.cancel_button.isEnabled())
        self.assertTrue(page.cancel_button.isVisible())
        self.assertFalse(page.tabs.isEnabled())
        self.window.controller.current_action = None
        self.window.set_busy(False)

    def test_palette_search_new_blocks_and_live_text_preview(self):
        page = self.builder()
        self.assertGreaterEqual(page.palette.count(), 19)
        page.palette_search.setText("Betreff")
        visible = [page.palette.item(i).data(Qt.ItemDataRole.UserRole) for i in range(page.palette.count()) if not page.palette.item(i).isHidden()]
        self.assertEqual(visible, ["subject"])
        page.add_node("description")
        from PySide6.QtWidgets import QPlainTextEdit
        editor = page.properties.findChild(QPlainTextEdit)
        editor.setPlainText("Neuer Text {{company.name}}")
        self.assertEqual(page.inline_preview.text.toPlainText(), "Neuer Text {{company.name}}")
        self.assertIn("Platzhalter", page.inline_preview.caption.text())
        page.undo()
        self.assertEqual(page.graph["nodes"][-1]["config"]["text"], "")

    def test_middle_mouse_pan_keeps_graph_history_selection(self):
        page = self.builder()
        card = page.scene.cards[page.graph["nodes"][1]["id"]]
        card.setSelected(True)
        graph, history = deepcopy(page.graph), deepcopy(page.history)
        start = page.view.viewport().rect().center()
        before = page.view.horizontalScrollBar().value()
        QTest.mousePress(page.view.viewport(), Qt.MouseButton.MiddleButton, pos=start)
        QTest.mouseMove(page.view.viewport(), start + QPoint(80, 30))
        QTest.mouseRelease(page.view.viewport(), Qt.MouseButton.MiddleButton, pos=start)
        self.assertNotEqual(page.view.horizontalScrollBar().value(), before)
        self.assertEqual(page.graph, graph)
        self.assertEqual(page.history, history)
        self.assertTrue(card.isSelected())
        self.assertIsNone(page.view.pan_position)

    def test_moving_nodes_reuses_edges_and_connection_preview_clears(self):
        page = self.builder()
        lines = list(page.scene.lines)
        card = page.scene.cards[page.graph["nodes"][1]["id"]]
        card.setPos(500, 120)
        self.assertEqual(page.scene.lines, lines)
        page.scene.pending = card.ports[("text", True)]
        page.scene.draw_connection(QPointF(700, 140))
        self.assertIsNotNone(page.scene.connection)
        QTest.keyClick(page.view, Qt.Key.Key_Escape)
        self.assertIsNone(page.scene.connection)
        page.scene.draw_connection(QPointF(800, 160))
        page.scene.rebuild(page.graph)
        self.assertIsNone(page.scene.connection)

    def test_image_docx_and_pdf_preview_in_editor(self):
        page = self.builder()
        from PySide6.QtGui import QImage, QPdfWriter, QPainter
        from PySide6.QtPdf import QPdfDocument
        from test_documents import _make_docx
        image = self.directory / "bild.png"
        bitmap = QImage(64, 32, QImage.Format.Format_RGB32)
        bitmap.fill(Qt.GlobalColor.green)
        self.assertTrue(bitmap.save(str(image)))
        page.add_node("image")
        page.property_changed("path", str(image))
        page.request_asset_preview()
        self.wait_idle()
        self.assertIsNotNone(page.node_preview.pixmap)
        self.assertEqual(page.inspector.currentIndex(), 2)
        screenshot = os.environ.get("EMAILCENTER_BUILDER_MEDIA_SCREENSHOT_PATH")
        if screenshot:
            self.window.toast.dismiss()
            page.fit()
            self.application.processEvents()
            self.window.grab().save(screenshot)
        docx = self.directory / "vorlage.docx"
        _make_docx(docx)
        page.add_node("docx")
        page.property_changed("path", str(docx))
        page.request_asset_preview()
        self.wait_idle()
        self.assertIn("{{COMPANY}}", page.node_preview.text.toPlainText())
        pdf = self.directory / "vorschau.pdf"
        writer = QPdfWriter(str(pdf))
        painter = QPainter(writer)
        painter.drawText(100, 200, "Lokale PDF-Vorschau")
        painter.end()
        del writer
        page.add_node("pdf")
        page.property_changed("path", str(pdf))
        page.request_asset_preview()
        self.wait_idle()
        self.assertEqual(page.node_preview.pdf.document.status(), QPdfDocument.Status.Ready)
        document = page.node_preview.pdf.document
        page.node_preview.clear()
        self.assertEqual(document.status(), QPdfDocument.Status.Null)
        self.assertEqual(self.errors, [])

    def test_rendered_html_preview_blocks_external_resources_and_links(self):
        page = self.builder()
        self.sources(page)
        graph = deepcopy(page.graph)
        graph["nodes"][2]["kind"] = "html"
        graph["nodes"][2]["config"]["text"] = '<h2>{{contact.display_name}}</h2><p>Hallo!</p><img src="https://example.test/tracker.png">'
        graph["nodes"][3]["config"]["body_format"] = "html"
        page.commit(graph)
        page.request_preview()
        self.wait_idle()
        page.rendered.setChecked(True)
        self.assertTrue(page.mail_preview.isVisible())
        self.assertFalse(page.result.isVisible())
        self.assertIn("Ada", page.mail_preview.text.toPlainText())
        self.assertNotIn("<h2>", page.mail_preview.text.toPlainText())
        self.assertFalse(page.mail_preview.text.openExternalLinks())
        self.assertFalse(page.mail_preview.text.openLinks())
        self.assertTrue(page.mail_preview.text.loadResource(2, QUrl("https://example.test/image.png")).isEmpty())

    def test_video_preview_explicit_playback_and_decoder_error(self):
        page = self.builder()
        video = self.directory / "defekt.mp4"
        # A recognized container header, deliberately without playable frames.
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        page.add_node("video")
        page.property_changed("path", str(video))
        page.request_asset_preview()
        self.wait_idle()
        from PySide6.QtMultimedia import QMediaPlayer
        self.assertEqual(page.node_preview.player.source(), QUrl.fromLocalFile(str(video)))
        self.assertEqual(page.node_preview.player.playbackState(), QMediaPlayer.PlaybackState.StoppedState)
        self.wait_for(lambda: page.node_preview.player.error() != QMediaPlayer.Error.NoError)
        self.assertIn("nicht lesbar", page.node_preview.video_notice.text())
        page.node_preview.clear()
        self.assertTrue(page.node_preview.player.source().isEmpty())
        self.assertEqual(self.errors, [])

    def test_builder_plan_prepares_and_opens_review_with_pending_jobs(self):
        page = self.builder()
        self.enable_fake_gmail()
        page.request_load()
        self.wait_idle()
        self.sources(page)
        page.account.setCurrentIndex(1)
        page.delivery_mode.setCurrentIndex(page.delivery_mode.findData("scheduled"))
        page.timezone.setCurrentText("UTC")
        page.interval.setValue(8)
        page.request_preview()
        self.wait_idle()
        page.confirm.setChecked(True)
        self.assertTrue(page.create_button.isEnabled())
        self.assertIn("Planung", page.create_button.text())
        page.create_button.click()
        self.wait_idle()
        review = self.window._bulk_delivery_dialog
        self.assertIsNotNone(review)
        self.assertEqual(review.dispatch["status"], "Ready")
        self.assertEqual(review.dispatch["interval_seconds"], 8)
        self.assertEqual(review.dispatch["timezone_id"], "UTC")
        self.assertIsNotNone(review.dispatch["items"][0]["job"]["scheduled_at_utc"])
        self.assertEqual(review.dispatch["items"][0]["job"]["approval_status"], "pending")
        self.assertEqual(self.fake_provider.sent, [])
        review.reject()
        self.wait_idle()

    def test_plan_changes_reset_confirmation_and_require_account(self):
        page = self.builder()
        self.sources(page)
        page.request_preview()
        self.wait_idle()
        page.confirm.setChecked(True)
        self.assertTrue(page.create_button.isEnabled())
        page.delivery_mode.setCurrentIndex(1)
        self.assertFalse(page.confirm.isChecked())
        page.confirm.setChecked(True)
        self.assertFalse(page.create_button.isEnabled())
        self.assertIn("Gmail", page.status.text())
        page.delivery_mode.setCurrentIndex(0)
        page.confirm.setChecked(True)
        self.assertTrue(page.create_button.isEnabled())

    def test_all_themes_keep_graph_and_preview_and_toolbar_pair(self):
        page = self.builder()
        self.sources(page)
        page.request_preview()
        self.wait_idle()
        graph, preview = deepcopy(page.graph), deepcopy(page.preview)
        from emailcenter.appearance import THEMES, paired_theme
        from PySide6.QtGui import QPalette
        backgrounds = set()
        for theme in THEMES:
            self.window.save_preferences({**self.window.preferences.values(), "theme": theme})
            backgrounds.add(self.application.palette().color(QPalette.ColorRole.Window).name())
            self.assertEqual(page.graph, graph)
            self.assertEqual(page.preview, preview)
            self.window.toggle_theme()
            self.assertEqual(self.window.preferences.theme, paired_theme(theme))
        self.assertEqual(len(backgrounds), len(THEMES))
        self.assertEqual(self.window.pages["settings"].theme.count(), len(THEMES))


if __name__ == "__main__":
    unittest.main()
