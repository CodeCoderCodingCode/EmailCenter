"""Hidden builder controls belong to their page before any resize/show event."""
import unittest
from copy import deepcopy
from emailcenter.language import render, set_language
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from emailcenter.preferences import PreferencesStore
from emailcenter.ui.main_window import MainWindow
import test_ui as harness


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class WidgetLifetimeTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project

    def test_hidden_builder_menus_switch_language_without_triggering_actions(self):
        page = self.window.pages['builder']
        menus = (page.add_button.menu(), page.transfer_button.menu())
        actions = [action for menu in menus for action in menu.actions() if not action.isSeparator()]
        original_graph = deepcopy(page.graph)
        original_name = page.name.text()
        triggered = []
        for action in actions:
            self.assertIsNotNone(action.property('languageSource'))
            action.triggered.connect(lambda *args: triggered.append(True))
        try:
            for language in ('en', 'de'):
                self.window.save_preferences({**self.window.preferences.values(), 'language': language}, preserve_edits=True)
                self.application.processEvents()
                self.assertEqual(actions, [action for menu in menus for action in menu.actions() if not action.isSeparator()])
                for action in actions:
                    self.assertEqual(action.text(), render(action.property('languageSource'), language))
                self.assertEqual(triggered, [])
                self.assertEqual(page.graph, original_graph)
                self.assertEqual(page.name.text(), original_name)
                self.assertFalse(page.isVisible())
            self.assertEqual(self.errors, [])
        finally:
            set_language('de')

    def test_hidden_builder_controls_and_menus_belong_to_page(self):
        page = self.window.pages['builder']
        self.assertFalse(page.isVisible())
        for control in (*page.tool_buttons, *page.footer_buttons):
            self.assertIsNotNone(control.parentWidget())
            self.assertTrue(page.isAncestorOf(control))
        for control in (page.add_button, page.transfer_button):
            self.assertIs(control.menu().parentWidget(), control)

    def test_unvisited_builder_buttons_and_menus_are_destroyed_with_window(self):
        baseline = set(QApplication.topLevelWidgets())
        for iteration in range(4):
            window = MainWindow(settings_store=PreferencesStore(self.directory / f'lifetime-{iteration}.json'))
            page = window.pages['builder']
            controls = [*page.tool_buttons, *page.footer_buttons, page.add_button.menu(), page.transfer_button.menu()]
            deleted = set()
            for index, control in enumerate(controls):
                control.destroyed.connect(lambda *args, index=index: deleted.add(index))
            window.show()
            self.application.processEvents()
            self.assertFalse(page.isVisible())
            window.close()
            self.wait_for(lambda: not window.controller.thread.isRunning())
            window.deleteLater()
            self.application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.application.processEvents()
            self.assertEqual(deleted, set(range(16)))
            self.assertEqual(set(QApplication.topLevelWidgets()), baseline)

    def test_resize_and_navigation_keep_builder_controls_owned(self):
        self.open_test_project()
        page = self.window.pages['builder']
        self.window.navigate('builder')
        self.wait_idle()
        for width in (820, 1250, 950, 820):
            self.window.resize(width, 720)
            self.application.processEvents()
            for control in (*page.tool_buttons, *page.footer_buttons):
                self.assertTrue(page.isAncestorOf(control))
                self.assertIsNotNone(control.parentWidget().layout())
        self.window.navigate('workspace')
        self.wait_idle()
        self.assertTrue(page.isAncestorOf(page.add_button))


if __name__ == '__main__':
    unittest.main()
