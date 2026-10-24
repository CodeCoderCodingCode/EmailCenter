"""Responsive autosave, recovery and graph navigation through real Qt controls."""

from copy import deepcopy
import json
import os
from threading import Event
import unittest
from unittest.mock import patch

import test_builder_ui as builder_harness
import test_ui as harness

if harness.QT_AVAILABLE:
    from PySide6.QtCore import QDateTime
    from PySide6.QtWidgets import QMessageBox, QPlainTextEdit, QLineEdit, QCheckBox
    from emailcenter.builder_workspace import BuilderWorkspaceService
    from emailcenter.database import connect
    from emailcenter.mail_bulk import digest
    from emailcenter.ui.main_window import MainWindow
    from emailcenter.preferences import PreferencesStore


@unittest.skipUnless(harness.QT_AVAILABLE, "PySide6 not installed")
class BuilderWorkspaceDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = builder_harness.BuilderDesktopTests.builder
    sources = builder_harness.BuilderDesktopTests.sources

    def tearDown(self):
        page = self.window.pages["builder"]
        if page._autosave_blocked:
            self.window.save_preferences({**self.window.preferences.values(), "builder_autosave": False})
        harness.DesktopTests.tearDown(self)

    def checkpoint(self, page):
        page.request_checkpoint(force=True)
        self.wait_for(lambda: self.window.controller._background is None)
        self.assertFalse(page._autosave_blocked, page.checkpoint_label.text())

    def stored(self):
        db = connect(self.directory / "project" / "emailcenter.sqlite3")
        try:
            record = db.execute("SELECT * FROM email_builder_workspace WHERE id=1").fetchone()
            return dict(record) if record else None
        finally:
            db.close()

    def external_change(self, **changes):
        record = self.stored()
        state = {**json.loads(record["state_json"]), **changes}
        db = connect(self.directory / "project" / "emailcenter.sqlite3")
        try:
            db.execute("UPDATE email_builder_workspace SET revision=revision+1,state_json=?,content_hash=?", (json.dumps(state), digest(state)))
            db.commit()
        finally:
            db.close()

    def test_debounced_autosave_keeps_editor_enabled_and_flushes_edits_before_close(self):
        page = self.builder()
        started, release = Event(), Event()
        original = BuilderWorkspaceService.save
        calls = []

        def held(service, **kwargs):
            calls.append(deepcopy(kwargs["state"]))
            if len(calls) == 1:
                started.set()
                release.wait(8)
            return original(service, **kwargs)

        self.window.save_preferences({**self.window.preferences.values(), "builder_autosave_seconds": 1})
        with patch.object(BuilderWorkspaceService, "save", held):
            try:
                page.name.setText("Erster Stand")
                self.assertTrue(page.autosave_timer.isActive())
                self.assertEqual(page.autosave_timer.interval(), 1000)
                self.wait_for(started.is_set)
                self.assertFalse(self.window.controller.busy)
                self.assertTrue(page.name.isEnabled())
                page.name.setText("Während Sicherung weitergeschrieben")
                self.assertTrue(self.window.controller.submit("close_project", {}))
            finally:
                release.set()
            self.wait_idle()
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(json.loads(self.stored()["state_json"])["name"], "Während Sicherung weitergeschrieben")
        self.assertEqual(self.errors, [])

    def test_close_project_restores_unfinished_rules_plan_and_view_without_approval(self):
        page = self.builder()
        page.name.setText("Unfertiger Auftrag")
        page.add_node("replace")
        page.property_changed("rules", [{"find": "", "replacement": "", "field": ""}], draft=True)
        page.delivery_mode.setCurrentIndex(page.delivery_mode.findData("scheduled"))
        page.schedule.setDateTime(QDateTime.fromString("2030-03-04T12:30:00", "yyyy-MM-ddTHH:mm:ss"))
        page.interval.setValue(13)
        page.zoom(1.2)
        state = page.work_state()
        self.submit("close_project", {})
        self.submit("open_project", {"path": str(self.directory / "project")})
        self.window.navigate("builder")
        self.wait_idle()
        self.assertEqual(page.graph, state["graph"])
        self.assertEqual(page.name.text(), state["name"])
        self.assertEqual(page.work_state()["scheduled_local"], state["scheduled_local"])
        self.assertEqual(page.interval.value(), 13)
        self.assertAlmostEqual(page.view.transform().m11(), state["view"]["zoom"])
        self.assertIsNone(page.preview)
        self.assertFalse(page.confirm.isChecked())
        self.assertIn("wiederhergestellt", page.checkpoint_label.text())

    def test_window_shutdown_flushes_checkpoint_and_next_window_restores(self):
        page = self.builder()
        page.name.setText("Letzte Eingabe vor Schließen")
        old = self.window
        old.close()
        self.wait_for(lambda: not old.controller.thread.isRunning())
        self.assertEqual(json.loads(self.stored()["state_json"])["name"], "Letzte Eingabe vor Schließen")
        old.deleteLater()
        self.application.processEvents()
        self.window = MainWindow(settings_store=PreferencesStore(self.directory / "preferences.json"))
        self.window.show()
        self.submit("open_project", {"path": str(self.directory / "project")})
        self.window.navigate("builder")
        self.wait_idle()
        self.assertEqual(self.window.pages["builder"].name.text(), "Letzte Eingabe vor Schließen")

    def test_autosave_off_manual_checkpoint_and_explicit_recovery(self):
        page = self.builder()
        self.window.save_preferences({**self.window.preferences.values(), "builder_autosave": False})
        page.name.setText("Manuell gesichert")
        page.autosave_timer.stop()
        page.request_checkpoint()
        self.assertIsNone(self.window.controller._background)
        self.assertIsNone(self.stored())
        self.checkpoint(page)
        self.submit("close_project", {})
        self.submit("open_project", {"path": str(self.directory / "project")})
        self.window.navigate("builder")
        self.wait_idle()
        self.assertEqual(page.name.text(), "Mein E-Mail-Ablauf")
        page.reload_workspace()
        self.wait_idle()
        self.assertEqual(page.name.text(), "Manuell gesichert")

    def test_conflict_retains_editor_blocks_close_and_reload_recovers_other_revision(self):
        page = self.builder()
        self.checkpoint(page)
        self.external_change(name="Zweites Fenster")
        page.name.setText("Meine neuen Eingaben")
        page.request_checkpoint(force=True)
        self.wait_for(lambda: self.window.controller._background is None)
        self.assertTrue(page._autosave_blocked)
        self.assertEqual(page.name.text(), "Meine neuen Eingaben")
        self.assertTrue(self.window.controller.submit("close_project", {}))
        self.wait_idle()
        self.assertTrue(page.isEnabled())
        self.assertIn("Autosicherung pausiert", self.errors[-1])
        self.errors.clear()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            page.reload_workspace()
        self.wait_idle()
        self.assertEqual(page.name.text(), "Zweites Fenster")
        self.assertFalse(page._autosave_blocked)

    def test_corrupt_checkpoint_blocks_shutdown_without_overwriting_then_explicit_replace(self):
        page = self.builder()
        self.checkpoint(page)
        db = connect(self.directory / "project" / "emailcenter.sqlite3")
        try:
            db.execute("UPDATE email_builder_workspace SET state_json='{broken'")
            db.commit()
        finally:
            db.close()
        page._workspace_loaded = False
        page.request_load()
        self.wait_idle()
        self.assertTrue(page._autosave_blocked)
        self.window.close()
        self.application.processEvents()
        self.assertTrue(self.window.controller.thread.isRunning())
        self.assertFalse(self.window.controller.stopping)
        self.assertTrue(self.window.isEnabled())
        self.assertEqual(self.stored()["state_json"], "{broken")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.checkpoint(page)
        self.assertIsInstance(json.loads(self.stored()["state_json"]), dict)

    def test_new_blocks_live_preview_personalized_links_and_node_navigation_layout(self):
        page = self.builder()
        self.sources(page)
        page.add_node("button")
        editor = page.properties.findChild(QPlainTextEdit)
        editor.setPlainText("Profil {{contact.display_name}}")
        url = next(edit for edit in page.properties.findChildren(QLineEdit) if edit.text() == "https://")
        url.setText("https://example.test/profil")
        self.assertIn("Profil {{contact.display_name}}", page.inline_preview.text.toPlainText())
        self.assertIn("href=", page.inline_preview.text.toHtml())
        identifier = page.selected_id
        graph = deepcopy(page.graph)
        graph["edges"].extend([
            {"from": graph["nodes"][0]["id"], "output": "values", "to": identifier, "input": "values"},
            {"from": identifier, "output": "text", "to": graph["nodes"][3]["id"], "input": "body"}])
        graph["nodes"][3]["config"]["body_format"] = "html"
        page.commit(graph)
        page.request_preview()
        self.wait_idle()
        self.assertTrue(page.preview["ready"])
        self.assertIn("Profil Ada", page.preview["rows"][0]["body"])
        for kind in ("link", "list", "file"):
            page.add_node(kind)
        for a in page.scene.cards.values():
            for b in page.scene.cards.values():
                if a is not b:
                    self.assertFalse(a.sceneBoundingRect().intersects(b.sceneBoundingRect()))
        before = deepcopy(page.graph)
        page.arrange()
        self.assertEqual(page.graph["edges"], before["edges"])
        page.undo()
        self.assertEqual(page.graph, before)
        page.node_jump.setCurrentIndex(page.node_jump.findData(identifier))
        self.assertEqual(page.selected_id, identifier)
        self.assertTrue(page.scene.cards[identifier].isSelected())
        screenshot = os.environ.get("EMAILCENTER_BUILDER_WORKSPACE_SCREENSHOT_PATH")
        if screenshot:
            page.arrange()
            self.window.resize(1280, 850)
            self.application.processEvents()
            self.window.toast.dismiss()
            self.window.grab().save(screenshot)

    def test_named_version_remains_base_of_recovered_unsaved_graph(self):
        page = self.builder()
        self.sources(page)
        page.save_button.click()
        self.wait_idle()
        base = page.version_id
        saved = deepcopy(page.saved_graph)
        page.name.setText("Ungespeicherter Name")
        self.submit("close_project", {})
        self.submit("open_project", {"path": str(self.directory / "project")})
        self.window.navigate("builder")
        self.wait_idle()
        self.assertEqual(page.version_id, base)
        self.assertEqual(page.saved_graph, saved)
        self.assertEqual(page.versions.count(), 1)
        self.assertEqual(page.name.text(), "Ungespeicherter Name")

    def test_manual_checkpoint_queued_during_background_save_when_autosave_off(self):
        page = self.builder()
        self.window.save_preferences({**self.window.preferences.values(), "builder_autosave": False})
        started, release = Event(), Event()
        original = BuilderWorkspaceService.save

        def held(service, **kwargs):
            started.set()
            release.wait(5)
            return original(service, **kwargs)

        with patch.object(BuilderWorkspaceService, "save", held):
            try:
                page.name.setText("Erster manueller Stand")
                page.request_checkpoint(force=True)
                self.wait_for(started.is_set)
                page.name.setText("Zweiter manueller Stand")
                page.request_checkpoint(force=True)
                self.assertTrue(page._checkpoint_force)
            finally:
                release.set()
            self.wait_for(lambda: self.window.controller._background is None)
        self.wait_for(lambda: json.loads(self.stored()["state_json"])["name"] == "Zweiter manueller Stand")
        self.assertFalse(page._checkpoint_force)
        started.clear()
        release.clear()
        with patch.object(BuilderWorkspaceService, "save", held):
            try:
                page.name.setText("Dritter manueller Stand")
                page.request_checkpoint(force=True)
                self.wait_for(started.is_set)
                page.name.setText("Letzter manueller Stand vor Projektwechsel")
                page.request_checkpoint(force=True)
                self.assertTrue(self.window.controller.submit("close_project", {}))
            finally:
                release.set()
            self.wait_idle()
        self.assertEqual(json.loads(self.stored()["state_json"])["name"], "Letzter manueller Stand vor Projektwechsel")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
