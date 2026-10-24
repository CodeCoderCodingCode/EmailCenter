"""Offscreen UI evidence for the delivered twenty-row workbook; never sends mail."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT / 'tools')]
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from emailcenter.gmail import GmailProvider
from emailcenter.email_builder import node
from test_builder_excel_ui import BuilderExcelDesktopTests
from run_completion_checks import code_hashes


def run(workbook, output, *, existing_word_rules=False, pdf_company_filenames=False):
    output = output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('UI evidence must stay inside the workspace.')
    output.mkdir(parents=True, exist_ok=False)
    before = code_hashes()
    report = {'status': 'Running', 'rows': 20, 'real_gmail_requests': 0, 'native_ui_acceptance': False}
    def forbidden(*args, **kwargs):
        report['real_gmail_requests'] += 1
        raise AssertionError('Real Gmail is disabled.')
    case = BuilderExcelDesktopTests('test_file_import_selects_all_rows_and_exposes_personalization_fields')
    case.setUpClass()
    case.setUp()
    try:
        with patch.object(GmailProvider, '_request', forbidden):
            page = case.builder()
            if existing_word_rules:
                graph = deepcopy(page.graph)
                doc, replace = node('docx'), node('replace')
                doc['config']['path'] = str(ROOT / 'docs/abnahme/A1_Layout/Vorlage.docx')
                replace['config']['rules'] = [{'find': '{{' + token + '}}', 'replacement': '', 'field': field}
                    for token, field in [('NAME', 'Ansprechpartner Name'), ('COMPANY', 'Unternehmen'), ('EMAIL', '{{Email}}')]]
                graph['nodes'].extend([doc, replace])
                convert = node('convert') if pdf_company_filenames else None
                if convert:
                    convert['config']['filename'] = 'Anschreiben{{Unternehmen}}.pdf'
                    graph['nodes'].append(convert)
                for a, out, b, port in [(doc, 'file', replace, 'docx'), (graph['nodes'][0], 'values', replace, 'values'),
                                       *(([(replace, 'file', convert, 'docx'), (convert, 'file', graph['nodes'][3], 'attachments')])
                                         if convert else [(replace, 'file', graph['nodes'][3], 'attachments')])]:
                    graph['edges'].append({'from': a['id'], 'output': out, 'to': b['id'], 'input': port})
                page.commit(graph)
            with patch('emailcenter.ui.main_window.QFileDialog.getOpenFileName', return_value=(str(workbook.resolve()), 'Excel')):
                case.window.open_builder_source('file')
            case.wait_idle()
            dialog = case.window._import_mapping_dialog
            assert dialog.target.currentData() == 'data_rows' and not dialog.target.isEnabled()
            assert dialog.sheet.currentText() == 'Bewerbungsziele'
            dialog.prepare()
            case.wait_idle()
            case.wait_for(lambda: case.window._bulk_source_dialog is not None and case.window._bulk_source_dialog.data is not None)
            dialog = case.window._bulk_source_dialog
            assert dialog.rows.rowCount() == 20
            assert all(dialog.rows.item(row, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable for row in range(20))
            assert dialog.mapping['contact.email'].currentData() == 'Email'
            assert dialog.mapping['contact.display_name'].currentData() == 'Ansprechpartner'
            dialog.select_visible()
            assert len(dialog.selected) == 20 and dialog.apply_button.isEnabled()
            QTest.qWait(300)
            assert dialog.grab().save(str(output / 'Selectable_Excel_Rows.png'))
            dialog.apply_button.click()
            case.wait_idle()
            assert len(page.graph['nodes'][0]['config']['sources']) == 20
            assert {'Bewerber_Name', 'Bewerbungs_ID', 'Anschriftstrasse'} <= set(page.fields())
            if existing_word_rules:
                case.window.open_builder_source('import')
                case.wait_idle()
                dialog = case.window._bulk_source_dialog
                case.wait_for(lambda: dialog.data is not None)
                dialog.select_visible()
                dialog.apply_button.click()
                case.wait_idle()
                assert len(page.graph['nodes'][0]['config']['sources']) == 20
            graph = deepcopy(page.graph)
            graph['nodes'][0]['config']['allow_duplicate_recipients'] = True
            graph['nodes'][1]['config']['text'] = 'EmailCenter TEST {{Bewerbungs_ID}} – {{Stelle}} bei {{Unternehmen}}'
            graph['nodes'][2]['config']['text'] = '{{Anrede_vollstaendig}}\n\n{{Anschreiben}}\n\n{{Bewerber_Name}}'
            page.commit(graph, graph['nodes'][0]['id'])
            QTest.qWait(300)
            assert page.grab().save(str(output / 'Builder_Imported_Data.png'))
            page.request_preview()
            case.wait_idle()
            assert page.preview['ready'] and len(page.preview['rows']) == 20
            if pdf_company_filenames:
                assert existing_word_rules
                for row in page.preview['rows']:
                    assert row['attachments'][0]['filename'] == 'Anschreiben' + row['source_snapshot']['fields']['Unternehmen'] + '.pdf'
                page.scene.clearSelection()
                page.scene.cards[convert['id']].setSelected(True)
                QTest.qWait(300)
                assert page.grab().save(str(output / 'PDF_Filename_Editor.png'))
            assert len({row['email'] for row in page.preview['rows']}) == 5
            page.scene.clearSelection()
            page.scene.cards[graph['nodes'][3]['id']].setSelected(True)
            page.inspector.setCurrentIndex(1)
            QTest.qWait(300)
            assert page.grab().save(str(output / 'Builder_Personal_Mail.png'))
            assert case.errors == []
            report.update(status='Completed', checks={'actual_xlsx_button_dialog': True, 'twenty_enabled_checkboxes': True,
                'automatic_email_name_mapping': True, 'twenty_sources_applied': True, 'all_column_tokens_available': True,
                'twenty_personal_mail_previews_ready': True},
                existing_word_rules_and_reimport_verified=existing_word_rules,
                personal_pdf_names_verified=pdf_company_filenames,
                workbook_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest())
    finally:
        case.tearDown()
    after = code_hashes()
    report['code_changed_during_run'] = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    assert not report['code_changed_during_run']
    report['tested_source_hashes'] = before
    (output / 'UI_Result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'tested_source_hashes'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--existing-word-rules', action='store_true')
    parser.add_argument('--pdf-company-filenames', action='store_true')
    args = parser.parse_args()
    run(args.workbook, args.output, existing_word_rules=args.existing_word_rules, pdf_company_filenames=args.pdf_company_filenames)
