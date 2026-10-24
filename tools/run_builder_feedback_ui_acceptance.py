"""Capture rule errors and the local draft/review sequence without Gmail calls."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT / 'tools')]
from PySide6.QtWidgets import QTableWidgetItem
from emailcenter.gmail import GmailProvider
from test_builder_feedback import BuilderFeedbackDesktopTests
from run_completion_checks import code_hashes


def run(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('UI evidence must stay inside the workspace.')
    output.mkdir(parents=True, exist_ok=False)
    before = code_hashes()
    report = {'status': 'Running', 'native_ui_acceptance': False, 'real_gmail_requests': 0, 'checks': {}}
    def forbidden(*args, **kwargs):
        report['real_gmail_requests'] += 1
        raise AssertionError('Real Gmail is disabled.')
    case = BuilderFeedbackDesktopTests('test_workflow_explains_disabled_buttons_and_requires_a_real_preview')
    case.setUpClass()
    case.setUp()
    try:
        with patch.object(GmailProvider, '_request', forbidden):
            page = case.builder()
            case.sources(page)
            assert not page.confirm.isEnabled() and not page.delivery_button.isEnabled()
            report['checks']['confirmation_unavailable_before_successful_preview'] = True
            page.add_node('replace')
            table = page.rule_table
            for index in range(2):
                table.insertRow(index)
                table.setItem(index, 0, QTableWidgetItem('{{NAME}}'))
                table.setItem(index, 2, QTableWidgetItem('contact.display_name'))
            page.preview_button.click()
            assert page.rule_table.currentRow() == 1 and 'Regel 1 und 2' in page.status.text()
            assert page.rule_table.item(0, 0).background().color().alpha() > 0
            assert not page.create_button.isEnabled() and not case.window.controller.busy
            report['checks']['duplicate_rows_marked_and_focused_before_background_work'] = True
            case.window.toast.dismiss()
            page.tabs.setSizes([150, 350, 510])
            case.application.processEvents()
            page.grab().save(str(output / 'Duplicate_Rule_Feedback.png'))
            page.delete_selected()
            page.preview_button.click()
            case.wait_idle()
            assert page.preview['ready'] and page.confirm.isEnabled()
            assert 'Schritt 2' in page.workflow_hint.text()
            page.confirm.setChecked(True)
            assert page.create_button.isEnabled() and 'Schritt 3' in page.workflow_hint.text()
            report['checks']['successful_preview_then_confirmation_enables_creation'] = True
            page.create_button.click()
            case.wait_idle()
            assert page.last_batch and page.delivery_button.isEnabled()
            assert 'Gruppe gespeichert' in page.workflow_hint.text()
            case.window.toast.dismiss()
            case.application.processEvents()
            page.grab().save(str(output / 'Group_Ready_For_Review.png'))
            page.delivery_button.click()
            case.wait_idle()
            review = case.window._bulk_delivery_dialog
            assert review.data['batch']['id'] == page.last_batch and review.dispatch is None
            review.grab().save(str(output / 'Local_Group_Review.png'))
            report['checks']['saved_group_opens_existing_review_without_dispatch_or_send'] = True
            review.reject()
            assert case.errors == []
        report['status'] = 'Completed'
    finally:
        case.tearDown()
    after = code_hashes()
    report['code_changed_during_run'] = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    assert not report['code_changed_during_run']
    report['tested_source_hashes'] = before
    (output / 'Feedback_UI_Result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'tested_source_hashes'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
