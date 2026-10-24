"""The actual Builder file button leads to selectable source rows."""
import unittest
from unittest.mock import patch
from copy import deepcopy

import test_ui as harness
import test_builder_ui as builder_harness
if harness.QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton, QCheckBox


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class BuilderExcelDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = builder_harness.BuilderDesktopTests.builder

    def test_existing_word_rule_with_excel_header_does_not_break_import(self):
        from emailcenter.email_builder import node
        page = self.builder()
        graph = deepcopy(page.graph)
        replace = node('replace')
        replace['config']['rules'] = [{'find': '{{BEWERBER}}', 'replacement': '', 'field': 'Bewerber Name'}]
        graph['nodes'].append(replace)
        page.commit(graph)
        source = self.directory / 'targets.csv'
        source.write_text('Bewerber Name;Ansprechpartner;Unternehmen;Email;Anschreiben\nTimon Huwer;Ada;Firma A;test@example.test;Text A\n', encoding='utf-8-sig')
        with patch('emailcenter.ui.main_window.QFileDialog.getOpenFileName', return_value=(str(source), 'CSV')):
            self.window.open_builder_source('file')
        self.wait_idle()
        self.window._import_mapping_dialog.prepare()
        self.wait_idle()
        self.wait_for(lambda: self.window._bulk_source_dialog is not None and self.window._bulk_source_dialog.data is not None)
        dialog = self.window._bulk_source_dialog
        self.assertEqual(dialog.mapping['contact.display_name'].currentData(), 'Ansprechpartner')
        self.assertEqual(dialog.mapping['contact.email'].currentData(), 'Email')
        from emailcenter.ui.bulk_source_dialogs import ImportRowsDialog
        raw_dialog = ImportRowsDialog([], ['Bewerber Name', '{{unfinished}}'], self.window)
        raw_dialog.display(dialog.data)
        self.assertEqual(raw_dialog.mapping['Bewerber_Name'].currentData(), 'Bewerber Name')
        self.assertNotIn('Bewerber Name', raw_dialog.mapping)
        self.assertNotIn('{{unfinished}}', raw_dialog.mapping)
        raw_dialog.deleteLater()
        dialog.select_visible()
        dialog.apply_button.click()
        self.wait_idle()
        self.assertEqual(self.errors, [])
        self.assertEqual(len(page.graph['nodes'][0]['config']['sources']), 1)
        self.assertIn('Bewerber_Name', page.fields())
        self.assertNotIn('Bewerber Name', page.fields())

    def test_file_import_selects_all_rows_and_exposes_personalization_fields(self):
        page = self.builder()
        source = self.directory / 'targets.csv'
        source.write_text('Bewerber Name;Ansprechpartner;Unternehmen;Email;Status;Anschreiben\nTimon Huwer;Ada;Firma A;test@example.test;offen;Text A\nTimon Huwer;Grace;Firma B;test@example.test;offen;Text B\n', encoding='utf-8-sig')
        card = page.scene.cards[page.graph['nodes'][0]['id']]
        card.setSelected(True)
        self.application.processEvents()
        load = next(b for b in page.properties.findChildren(QPushButton) if b.text() == 'Excel / CSV laden')
        with patch('emailcenter.ui.main_window.QFileDialog.getOpenFileName', return_value=(str(source), 'CSV')):
            load.click()
        self.wait_idle()
        dialog = self.window._import_mapping_dialog
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.target.currentData(), 'data_rows')
        self.assertFalse(dialog.target.isEnabled())
        dialog.prepare()
        self.wait_idle()
        self.wait_for(lambda: self.window._bulk_source_dialog is not None and self.window._bulk_source_dialog.data is not None)
        dialog = self.window._bulk_source_dialog
        self.assertEqual(dialog.rows.rowCount(), 2)
        for row in range(2):
            self.assertTrue(dialog.rows.item(row, 0).flags() & Qt.ItemFlag.ItemIsEnabled)
            self.assertTrue(dialog.rows.item(row, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertEqual(dialog.mapping['contact.display_name'].currentData(), 'Ansprechpartner')
        self.assertEqual(dialog.mapping['contact.email'].currentData(), 'Email')
        dialog.select_visible()
        self.assertTrue(dialog.apply_button.isEnabled())
        dialog.apply_button.click()
        self.wait_idle()
        self.assertIsNone(self.window._bulk_source_dialog)
        self.assertEqual(len(page.graph['nodes'][0]['config']['sources']), 2)
        self.assertIn('Bewerber_Name', page.fields())
        repeated = next(c for c in page.properties.findChildren(QCheckBox) if c.text().startswith('Mehrere Bewerbungsziele'))
        self.assertFalse(repeated.isChecked())
        repeated.click()
        self.application.processEvents()
        self.assertTrue(page.graph['nodes'][0]['config']['allow_duplicate_recipients'])
        graph = deepcopy(page.graph)
        graph['nodes'][1]['config']['text'] = '{{Unternehmen}} / {{Bewerber_Name}}'
        graph['nodes'][2]['config']['text'] = '{{Anschreiben}}'
        page.commit(graph)
        page.request_preview()
        self.wait_idle()
        self.assertTrue(page.preview['ready'], page.preview['rows'])
        self.assertEqual([r['subject'] for r in page.preview['rows']], ['Firma A / Timon Huwer', 'Firma B / Timon Huwer'])
        self.assertEqual(self.errors, [])
