"""Actionable rule errors and the preview → draft group → review sequence."""
from copy import deepcopy
import unittest

import test_email_builder as service_harness
import test_builder_ui as ui_harness
import test_ui as harness
from emailcenter.email_builder import node, starter_graph, validate_graph
from emailcenter.word_replace import WordRuleError, validate_rules


class RuleFeedbackTests(unittest.TestCase):
    def rule(self, find='{{NAME}}'):
        return {'find': find, 'replacement': '', 'field': 'contact.display_name'}

    def test_empty_rule_identifies_editor_row_without_changing_input(self):
        rules = [self.rule(), self.rule('')]
        before = deepcopy(rules)
        with self.assertRaises(WordRuleError) as caught:
            validate_rules(rules, True)
        self.assertEqual(caught.exception.rule_rows, (1,))
        self.assertIn('Regel 2 hat keinen Suchtext', str(caught.exception))
        self.assertEqual(rules, before)

    def test_duplicate_identifies_both_rows_and_respects_case_choice(self):
        rules = [self.rule('NAME'), self.rule('name')]
        self.assertEqual(validate_rules(rules, True), rules)
        with self.assertRaises(WordRuleError) as caught:
            validate_rules(rules, False)
        self.assertEqual(caught.exception.rule_rows, (0, 1))
        self.assertIn('Regel 1 und 2', str(caught.exception))
        self.assertIn('alle Treffer', str(caught.exception))

    def test_invalid_rule_details_and_limits_remain_enforced(self):
        for rule in (self.rule('x' * 201), self.rule('bad\ttext'),
                     {**self.rule(), 'field': 'x' * 201},
                     {**self.rule(), 'replacement': 'x' * 32769},
                     self.rule('bad\x00text'), {**self.rule(), 'field': None}):
            with self.subTest(rule_type=type(rule.get('field')).__name__):
                with self.assertRaises(WordRuleError) as caught:
                    validate_rules([rule], True)
                self.assertEqual(caught.exception.rule_rows, (0,))
        for rules in ([], [self.rule(str(i)) for i in range(101)]):
            with self.assertRaises(WordRuleError):
                validate_rules(rules, True)

    def test_graph_error_carries_block_identifier_and_position(self):
        graph = starter_graph()
        replacement = node('replace')
        replacement['config']['rules'] = [self.rule(), self.rule()]
        graph['nodes'].append(replacement)
        with self.assertRaises(WordRuleError) as caught:
            validate_graph(graph, complete=True)
        self.assertEqual(caught.exception.builder_node_id, replacement['id'])
        self.assertIn('Baustein 5', str(caught.exception))


class BlockPreviewFeedbackTests(unittest.TestCase):
    setUp = service_harness.BuilderTests.setUp
    tearDown = service_harness.BuilderTests.tearDown
    document_chain = service_harness.BuilderTests.document_chain

    def test_personal_asset_preview_exposes_the_actual_missing_data_field(self):
        self.document_chain()
        replacement = next(n for n in self.graph['nodes'] if n['kind'] == 'replace')
        replacement['config']['rules'][0]['field'] = 'Missing_Excel_Column'
        with self.assertRaisesRegex(ValueError, 'Zeile 1.*Fehlende Datenfelder: Missing_Excel_Column'):
            self.service.asset_preview(self.graph, replacement['id'])

    def test_literal_search_inside_braces_exposes_remaining_docx_placeholder(self):
        self.document_chain()
        replacement = next(n for n in self.graph['nodes'] if n['kind'] == 'replace')
        replacement['config']['rules'][0]['find'] = 'NAME'
        data = self.graph['nodes'][0]['config']
        data['sources'] = data['sources'][:1]
        for name in ('Ada', 'Max Mustermann', 'Éva Müller'):
            with self.subTest(name=name):
                data['sources'][0]['fields']['contact.display_name'] = name
                with self.assertRaisesRegex(ValueError, 'Offene Dokumentplatzhalter: ' + name):
                    self.service.asset_preview(self.graph, replacement['id'])
                self.assertFalse(self.service.preview(self.graph)['ready'])
        replacement['config']['rules'][0]['find'] = '{{NAME}}'
        self.assertIn('Hello Éva Müller', self.service.asset_preview(self.graph, replacement['id'])['text'])


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class BuilderFeedbackDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = ui_harness.BuilderDesktopTests.builder
    sources = ui_harness.BuilderDesktopTests.sources

    def test_workflow_explains_disabled_buttons_and_requires_a_real_preview(self):
        page = self.builder()
        self.sources(page)
        self.assertIn('Schritt 1', page.workflow_hint.text())
        self.assertFalse(page.confirm.isEnabled())
        self.assertFalse(page.delivery_button.isEnabled())
        self.assertIn('Entwurfsgruppe erstellen', page.delivery_button.toolTip())
        page.preview_button.click()
        self.wait_idle()
        self.assertIn('Schritt 2', page.workflow_hint.text())
        self.assertTrue(page.confirm.isEnabled())
        page.confirm.setChecked(True)
        self.assertIn('Schritt 3', page.workflow_hint.text())
        page.create_button.click()
        self.wait_idle()
        self.assertTrue(page.delivery_button.isEnabled())
        self.assertIn('Gruppe gespeichert', page.workflow_hint.text())
        self.assertEqual(self.errors, [])

    def test_bad_rule_selects_block_and_row_without_starting_background_work(self):
        page = self.builder()
        page.add_node('replace')
        from PySide6.QtWidgets import QTableWidgetItem
        table = page.rule_table
        table.insertRow(0)
        table.setItem(0, 0, QTableWidgetItem('{{NAME}}'))
        table.setItem(0, 2, QTableWidgetItem('contact.display_name'))
        table.insertRow(1)
        table.setItem(1, 0, QTableWidgetItem(''))
        replacement = page.selected_id
        self.assertIn('Regel 2', page.rule_feedback.text())
        self.assertGreater(table.item(1, 0).background().color().alpha(), 0)
        page.scene.clearSelection()
        requests = []
        page.operation_requested.connect(lambda action, payload: requests.append(action))
        page.preview_button.click()
        self.assertEqual(requests, [])
        self.assertEqual(page.selected_id, replacement)
        self.assertEqual(page.rule_table.currentRow(), 1)
        self.assertIn('Regel 2 hat keinen Suchtext', page.status.text())
        self.assertIn('Vorschau blockiert', page.workflow_hint.text())
        self.assertFalse(page.create_button.isEnabled())
        page.delete_selected()
        self.assertIn('Schritt 1', page.workflow_hint.text())
        self.assertIsNone(page._preview_error)

    def test_rule_feedback_updates_when_case_choice_changes(self):
        page = self.builder()
        page.add_node('replace')
        from PySide6.QtWidgets import QCheckBox, QTableWidgetItem
        table = page.rule_table
        for index, text in enumerate(('NAME', 'name')):
            table.insertRow(index)
            table.setItem(index, 0, QTableWidgetItem(text))
        self.assertIn('Regelstruktur gültig', page.rule_feedback.text())
        control = next(w for w in page.properties.findChildren(QCheckBox) if w.text() == 'Groß-/Kleinschreibung')
        control.setChecked(False)
        self.assertIn('Regel 1 und 2', page.rule_feedback.text())
        control.setChecked(True)
        self.assertIn('Regelstruktur gültig', page.rule_feedback.text())
        self.assertEqual(table.item(0, 0).background().color().alpha(), 0)

    def test_footer_stays_reachable_with_step_hint_in_small_window(self):
        page = self.builder()
        self.window.resize(820, 600)
        self.application.processEvents()
        self.assertTrue(page.workflow_hint.isVisible())
        bottom = page.delivery_button.mapTo(page, page.delivery_button.rect().bottomRight())
        self.assertLessEqual(bottom.y(), page.height())


if __name__ == '__main__':
    unittest.main()
