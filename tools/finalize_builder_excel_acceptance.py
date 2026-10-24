"""Bind the workbook, full suite, real conversions and UI evidence to the archive."""
import argparse
import json
from pathlib import Path
import zipfile

from run_completion_checks import code_hashes
from create_code_snapshot import create_snapshot

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/abnahme/A8_Builder_Excel'


def main(evidence=EVIDENCE, workflow_folder='Run2', ui_folder='UI4', workbook_result=None, feedback_result=None, user_core_workflow_confirmed=False):
    evidence = Path(evidence).resolve()
    if not evidence.is_relative_to(ROOT):
        raise ValueError('Evidence must stay within the workspace.')
    suite = json.loads((evidence / 'Full_Test_Result.json').read_text(encoding='utf-8'))
    workflow = json.loads((evidence / workflow_folder / 'Workflow_Result.json').read_text(encoding='utf-8'))
    ui = json.loads((evidence / ui_folder / 'UI_Result.json').read_text(encoding='utf-8'))
    workbook = json.loads(Path(workbook_result or evidence / 'Workbook_Result.json').read_text(encoding='utf-8'))
    assert suite['ok'] and suite['exit_code'] == 0
    assert all(r['status'] == 'Completed' for r in (workflow, ui, workbook))
    hashes = code_hashes()
    assert suite['tested_source_hashes'] == workflow['tested_source_hashes'] == ui['tested_source_hashes'] == hashes
    assert all(not r['code_changed_during_run'] for r in (suite, workflow, ui))
    assert workflow['real_gmail_requests'] == ui['real_gmail_requests'] == 0
    assert workflow['workbook_sha256'] == ui['workbook_sha256'] == workbook['sha256']
    assert workflow['checks']['test_project_database_closed_before_windows_cleanup']
    if feedback_result:
        feedback = json.loads(Path(feedback_result).read_text(encoding='utf-8'))
        assert feedback['status'] == 'Completed' and feedback['real_gmail_requests'] == 0
        assert not feedback['code_changed_during_run'] and feedback['tested_source_hashes'] == hashes
        assert all(feedback['checks'].values())
    archive = create_snapshot()
    assert archive['schema_version'] == 14
    with zipfile.ZipFile(ROOT / 'docs/abnahme' / archive['archive']) as saved:
        manifest = json.loads(saved.read('CODE_MANIFEST.json'))
        assert all(manifest['files'][name]['sha256'] == digest for name, digest in hashes.items())
    result = {'status': 'Completed', 'schema_version': 14, 'rows': 20, 'allowed_recipient_addresses': 5,
        'real_gmail_requests': 0, 'native_ui_acceptance': False,
        'user_core_workflow_confirmed': user_core_workflow_confirmed,
        'own_docx_acceptance_pending': not user_core_workflow_confirmed,
        'tests': suite['tests'], 'passed': suite['tests'] - suite['skipped'], 'skipped': suite['skipped'],
        'same_code_verified_by_suite_workflow_ui_archive': True, 'verified_source_file_count': len(hashes),
        'workbook_sha256': workbook['sha256'], 'archive': archive,
        'evidence': {'full_suite': 'Full_Test_Result.json', 'workflow': workflow_folder + '/Workflow_Result.json',
                     'ui': ui_folder + '/UI_Result.json', 'workbook': str(workbook_result or evidence / 'Workbook_Result.json')}}
    if feedback_result:
        result['evidence']['feedback_ui'] = str(feedback_result)
    (evidence / 'Completion_Result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--workflow-folder', default='Run2')
    parser.add_argument('--ui-folder', default='UI4')
    parser.add_argument('--workbook-result', type=Path)
    parser.add_argument('--feedback-result', type=Path)
    parser.add_argument('--user-core-workflow-confirmed', action='store_true')
    args = parser.parse_args()
    main(args.evidence, args.workflow_folder, args.ui_folder, args.workbook_result, args.feedback_result, args.user_core_workflow_confirmed)
