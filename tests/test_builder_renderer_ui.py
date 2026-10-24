"""Finished mail renderer and background media autoload through the editor."""

from copy import deepcopy
import os
from threading import Event
import unittest
from unittest.mock import patch

import test_ui as harness
import test_builder_ui as builder_harness

if harness.QT_AVAILABLE:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QImage, QPainter, QPdfWriter
    from PySide6.QtPdf import QPdfDocument
    from emailcenter.email_builder import EmailBuilderService, node
    from emailcenter.ui.builder_preview import LocalTextDocument
    from test_documents import _make_docx


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class BuilderRendererDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = builder_harness.BuilderDesktopTests.builder
    sources = builder_harness.BuilderDesktopTests.sources

    def rows(self, page):
        self.sources(page)
        graph = deepcopy(page.graph)
        graph["nodes"][0]["config"]["sources"].append({"kind": "manual", "fields": {"contact.display_name": "Grace", "contact.email": "grace@example.test", "company.name": "Grace GmbH", "application.cover_letter": "Grace-Anschreiben"}})
        graph["nodes"][2]["kind"] = "html"
        graph["nodes"][2]["config"]["text"] = '<h2>Hallo {{contact.display_name}}</h2><p>{{application.cover_letter}}</p><a href="https://example.test">Webseite</a><img src="https://example.test/tracker">'
        graph["nodes"][3]["config"]["body_format"] = "html"
        page.commit(graph)

    def select(self, page, identifier):
        page.node_jump.setCurrentIndex(page.node_jump.findData(identifier))
        self.assertEqual(page.selected_id, identifier)

    def preview(self, page):
        page.request_preview()
        self.wait_idle()
        self.assertTrue(page.preview["ready"], page.status.text())

    def wait_assets(self, page):
        self.wait_for(lambda: page._auto_asset_inflight is None and not page._asset_queue)
        self.assertEqual(page._asset_errors, {})

    def image(self, name, color):
        path = self.directory / name
        bitmap = QImage(80, 40, QImage.Format.Format_RGB32)
        bitmap.fill(color)
        self.assertTrue(bitmap.save(str(path)))
        return path

    def attach(self, page, kind, path):
        graph = deepcopy(page.graph)
        item = node(kind, 350, 450 + (len(graph["nodes"]) - 4) * 180)
        item["config"]["path"] = str(path)
        graph["nodes"].append(item)
        graph["edges"].append({"from": item["id"], "output": "file", "to": graph["nodes"][3]["id"], "input": "attachments"})
        if "{{" in str(path):
            graph["edges"].append({"from": graph["nodes"][0]["id"], "output": "values", "to": item["id"], "input": "values"})
        page.commit(graph, item["id"])
        return item["id"]

    def test_finished_mail_autoloads_at_email_node_and_changes_with_recipient(self):
        page = self.builder()
        self.submit("mail_save_signature", {"name": "Persönlich", "content_text": "Gruß von Tim", "content_html": "<b>Gruß von Tim</b>"})
        page.request_load()
        self.wait_idle()
        page.signature.setCurrentIndex(1)
        self.rows(page)
        self.select(page, page.graph["nodes"][3]["id"])
        self.assertTrue(page.inline_mail.value["live"])
        self.preview(page)
        self.assertEqual(page.inspector.currentIndex(), 0)
        self.assertTrue(page.rendered.isChecked())
        self.assertIn("ada@example.test", page.inline_mail.headers.text())
        self.assertIn("Bewerbung bei Ada GmbH", page.inline_mail.headers.text())
        self.assertIn("Hallo Ada", page.inline_mail.text.toPlainText())
        self.assertIn("Gruß von Tim", page.inline_mail.text.toPlainText())
        card = page.scene.cards[page.selected_id]
        self.assertIsNotNone(card.preview_document)
        self.assertIn("Hallo Ada", card.preview_document.toPlainText())
        page.recipient.setCurrentIndex(1)
        self.assertIn("grace@example.test", page.inline_mail.headers.text())
        self.assertIn("Hallo Grace", page.mail_preview.text.toPlainText())
        self.assertIn("Hallo Grace", card.preview_document.toPlainText())
        self.assertFalse(page.inline_mail.text.openLinks())
        self.assertFalse(page.inline_mail.text.openExternalLinks())
        self.assertTrue(card.preview_document.loadResource(2, QUrl("https://example.test/tracker")).isEmpty())
        screenshot = os.environ.get("EMAILCENTER_BUILDER_RENDERER_SCREENSHOT_PATH")
        if screenshot:
            self.window.resize(1400, 900)
            page.zoom(1.2)
            self.application.processEvents()
            self.window.toast.dismiss()
            self.window.grab().save(screenshot)

    def test_live_mail_without_preview_is_marked_unverified_and_typing_clears_ready_cards(self):
        page = self.builder()
        self.rows(page)
        self.select(page, page.graph["nodes"][3]["id"])
        self.assertTrue(page.inline_mail.value["live"])
        self.assertIn("{{contact.display_name}}", page.inline_mail.text.toPlainText())
        self.preview(page)
        page.confirm.setChecked(True)
        self.select(page, page.graph["nodes"][2]["id"])
        page.property_changed("text", "Unfertig {{contact.")
        self.assertIsNone(page.preview)
        self.assertFalse(page.confirm.isChecked())
        self.assertTrue(all(card.preview_value is None for card in page.scene.cards.values()))
        self.select(page, page.graph["nodes"][3]["id"])
        self.assertTrue(page.inline_mail.value["live"])
        self.assertIn("Ungeprüfter Entwurf", page.inline_mail.notice.text())
        self.assertFalse(page.create_button.isEnabled())

    def test_images_preload_on_canvas_and_show_inline_without_media_button(self):
        page = self.builder()
        self.rows(page)
        image = self.image("bild.png", Qt.GlobalColor.green)
        identifier = self.attach(page, "image", image)
        self.select(page, page.graph["nodes"][3]["id"])
        self.preview(page)
        self.wait_assets(page)
        self.assertIsNotNone(page.scene.cards[identifier].preview_pixmap)
        self.assertIn("bild.png", page.inline_mail.attachments.text())
        self.select(page, identifier)
        self.assertEqual(page.inspector.currentIndex(), 0)
        self.assertIsNotNone(page.inline_preview.pixmap)
        self.assertIsNotNone(page.node_preview.pixmap)
        self.assertEqual(self.errors, [])

    def test_selected_pdf_autoload_and_video_without_autoplay(self):
        page = self.builder()
        self.rows(page)
        pdf = self.directory / "ansicht.pdf"
        writer = QPdfWriter(str(pdf))
        painter = QPainter(writer)
        painter.drawText(100, 200, "Editor-PDF")
        painter.end()
        del writer
        identifier = self.attach(page, "pdf", pdf)
        self.preview(page)
        self.wait_assets(page)
        self.assertEqual(page.inline_preview.pdf.document.status(), QPdfDocument.Status.Ready)
        video = self.directory / "video.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        identifier = self.attach(page, "video", video)
        self.preview(page)
        self.wait_assets(page)
        from PySide6.QtMultimedia import QMediaPlayer
        self.assertEqual(page.inline_preview.player.source(), QUrl.fromLocalFile(str(video)))
        self.assertEqual(page.inline_preview.player.playbackState(), QMediaPlayer.PlaybackState.StoppedState)

    def test_word_replace_personal_document_preview_loads_inline_on_row_switch(self):
        page = self.builder()
        self.rows(page)
        source = self.directory / "original.docx"
        _make_docx(source)
        graph = deepcopy(page.graph)
        document, replacement = node("docx", 300, 450), node("replace", 620, 450)
        document["config"]["path"] = str(source)
        replacement["config"]["rules"] = [{"find": "{{NAME}}", "replacement": "", "field": "contact.display_name"}, {"find": "{{COMPANY}}", "replacement": "", "field": "company.name"}]
        replacement["config"]["rules"].extend({"find": "{{" + key + "}}", "replacement": "Beispiel", "field": ""} for key in ("ROLE", "DATE", "UNKNOWN"))
        graph["nodes"].extend([document, replacement])
        graph["edges"].extend([
            {"from": document["id"], "output": "file", "to": replacement["id"], "input": "docx"},
            {"from": graph["nodes"][0]["id"], "output": "values", "to": replacement["id"], "input": "values"},
            {"from": replacement["id"], "output": "file", "to": graph["nodes"][3]["id"], "input": "attachments"}])
        page.commit(graph, replacement["id"])
        self.preview(page)
        self.assertIn("Ada", page.inline_preview.text.toPlainText())
        page.recipient.setCurrentIndex(1)
        self.assertIn("Grace", page.inline_preview.text.toPlainText())
        self.assertNotIn("Ada", page.inline_preview.text.toPlainText())
        self.assertIsNone(page._auto_asset_inflight)

    def test_row_switch_during_background_load_keeps_editor_enabled_and_discards_old_display(self):
        page = self.builder()
        self.rows(page)
        first = self.image("ada.png", Qt.GlobalColor.red)
        second = self.image("grace.png", Qt.GlobalColor.blue)
        graph = deepcopy(page.graph)
        for source, path in zip(graph["nodes"][0]["config"]["sources"], (first, second)):
            source["fields"]["attachment.path"] = str(path)
        page.commit(graph)
        identifier = self.attach(page, "image", "{{attachment.path}}")
        started, release = Event(), Event()
        original = EmailBuilderService.asset_preview

        def held(service, *args, **kwargs):
            if kwargs["row_number"] == 1:
                started.set()
                release.wait(7)
            return original(service, *args, **kwargs)

        with patch.object(EmailBuilderService, "asset_preview", held):
            try:
                self.preview(page)
                self.wait_for(started.is_set)
                self.assertFalse(self.window.controller.busy)
                self.assertTrue(page.recipient.isEnabled())
                page.recipient.setCurrentIndex(1)
            finally:
                release.set()
            self.wait_assets(page)
        self.assertEqual(page.inline_preview.value["filename"], "grace.png")
        self.assertEqual(page.scene.cards[identifier].preview_value["filename"], "grace.png")
        self.assertEqual(page.inline_preview.pixmap.toImage().pixelColor(0, 0), Qt.GlobalColor.blue)

    def test_changed_file_during_autoload_retains_mail_and_requires_new_preview(self):
        page = self.builder()
        self.rows(page)
        image = self.image("bild.png", Qt.GlobalColor.green)
        self.attach(page, "image", image)
        started, release = Event(), Event()
        original = EmailBuilderService.asset_preview

        def held(service, *args, **kwargs):
            started.set()
            release.wait(7)
            return original(service, *args, **kwargs)

        with patch.object(EmailBuilderService, "asset_preview", held):
            try:
                self.preview(page)
                self.wait_for(started.is_set)
                self.image("bild.png", Qt.GlobalColor.red)
            finally:
                release.set()
            self.wait_for(lambda: page._auto_asset_inflight is None)
        self.assertTrue(page._asset_errors)
        self.assertIsNotNone(page.preview)
        page.confirm.setChecked(True)
        self.assertFalse(page.create_button.isEnabled())
        self.assertIn("geändert", page.inline_preview.text.toPlainText())
        self.assertIn("geändert", page.mail_preview.notice.text())
        self.preview(page)
        self.wait_assets(page)
        self.assertEqual(page._asset_errors, {})
        self.assertEqual(self.errors, [])

    def test_repreview_during_inflight_media_load_clears_old_generation(self):
        page = self.builder()
        self.rows(page)
        self.attach(page, "image", self.image("alt.png", Qt.GlobalColor.red))
        started, release = Event(), Event()
        original = EmailBuilderService.asset_preview

        def held(service, *args, **kwargs):
            started.set()
            release.wait(7)
            return original(service, *args, **kwargs)

        with patch.object(EmailBuilderService, "asset_preview", held):
            try:
                self.preview(page)
                self.wait_for(started.is_set)
                page.property_changed("path", str(self.image("neu.png", Qt.GlobalColor.blue)))
                page.request_preview()
            finally:
                release.set()
            self.wait_idle()
            self.wait_assets(page)
        self.assertEqual(page.inline_preview.value["filename"], "neu.png")
        self.assertEqual(page.inline_preview.pixmap.toImage().pixelColor(0, 0), Qt.GlobalColor.blue)

    def test_many_image_thumbnails_keep_cache_bounded_and_small_footer_reachable(self):
        page = self.builder()
        self.rows(page)
        identifiers = [self.attach(page, "image", self.image(str(index) + ".png", Qt.GlobalColor.green)) for index in range(7)]
        self.preview(page)
        self.wait_assets(page)
        self.assertLessEqual(len(page._asset_cache), 6)
        self.assertTrue(all(page.scene.cards[key].preview_pixmap for key in identifiers))
        self.assertLessEqual(sum(len(value.get("content", b"")) for value in page._asset_cache.values()), 40 * 1024 * 1024)
        self.window.resize(820, 600)
        self.application.processEvents()
        bottom = page.create_button.mapTo(page, page.create_button.rect().bottomRight())
        self.assertLessEqual(bottom.y(), page.height())
        self.assertTrue(page.recipient.isVisible())


if __name__ == "__main__":
    unittest.main()
