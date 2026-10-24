"""Repeat existing local Qt workflows in one process, with resource evidence."""
import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['TEMP'] = os.environ['TMP'] = str(ROOT)
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from emailcenter.gmail import GmailProvider
from run_completion_checks import code_hashes

MODULES = ['test_localization', 'test_endspurt_ui', 'test_builder_workspace_ui',
           'test_completion_package_ui', 'test_ui_lifetime', 'test_restore_long_paths']
MAIL_CASES = [
    'test_bulk_source_excel_mapping_personal_preview_and_snapshot_history',
    'test_bulk_manual_table_paste_and_personal_file_selection',
    'test_bulk_excel_document_template_generates_matching_application_attachments',
    'test_bulk_delivery_common_review_approval_and_personalized_send',
    'test_bulk_delivery_pause_stays_clickable_during_send_and_resume_skips_sent',
    'test_bulk_delivery_cancel_after_inflight_send_preserves_its_receipt',
    'test_bulk_delivery_planned_close_pauses_and_reopen_keeps_jobs',
    'test_bulk_delivery_uncertain_result_stops_and_exposes_reconciliation',
    'test_bulk_delivery_long_ui_gap_pauses_planned_group',
    'test_bulk_delivery_preparation_error_retains_completed_jobs_and_resumes',
    'test_bulk_delivery_gap_during_inflight_send_requires_new_approval_before_next',
    'test_bulk_delivery_single_job_dialog_does_not_offer_group_bypass',
    'test_workflow_ui_word_uses_excel_source_without_bulk_dialog',
    'test_workflow_ui_export_selection_columns_and_settings_defaults',
    'test_hotkeys_actual_navigation_and_search_key_events',
    'test_hotkeys_actual_record_save_key_event',
    'test_hotkeys_help_and_save_do_not_approve_or_send_jobs',
]


def resources():
    result = {}
    if os.name == 'nt':
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in (
                            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                            'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        data = Counters()
        data.cb = ctypes.sizeof(data)
        if psapi.GetProcessMemoryInfo(process, ctypes.byref(data), data.cb):
            result.update(working_set_bytes=data.WorkingSetSize, private_bytes=data.PrivateUsage,
                          peak_working_set_bytes=data.PeakWorkingSetSize)
        handles = wintypes.DWORD()
        kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        if kernel.GetProcessHandleCount(process, ctypes.byref(handles)):
            result['process_handles'] = handles.value
    app = QApplication.instance()
    if app:
        result['qt_widgets'] = len(app.allWidgets())
        result['qt_top_level_widgets'] = len(app.topLevelWidgets())
        result['qt_top_level_classes'] = dict(Counter(widget.metaObject().className() for widget in app.topLevelWidgets()))
    return result


def cleanup():
    gc.collect()
    app = QApplication.instance()
    if app:
        for _ in range(2):
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    gc.collect()


def run(rounds, output):
    if not output.resolve().is_relative_to(ROOT):
        raise ValueError('UI output must stay within the workspace.')
    output.mkdir(parents=True, exist_ok=False)
    before = code_hashes()
    started = time.monotonic()
    blocked = []
    def no_real_gmail(*args, **kwargs):
        blocked.append('unexpected_real_gmail_request')
        raise RuntimeError('Real Gmail requests are disabled in this local UI run.')
    report = {'rounds': [], 'requested_rounds': rounds, 'tests': 0,
              'native_keyboard_or_dpi_acceptance': False, 'qt_platform': os.environ['QT_QPA_PLATFORM'],
              'real_gmail_requests': 0, 'tested_source_hashes': before,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (output / 'UI_Soak_Output.txt').open('w', encoding='utf-8') as stream, \
            patch.object(GmailProvider, '_request', no_real_gmail):
        for number in range(1, rounds + 1):
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromNames(MODULES + ['test_ui.DesktopTests.' + name for name in MAIL_CASES])
            round_start = time.monotonic()
            result = unittest.TextTestRunner(stream=stream, verbosity=2, failfast=True).run(suite)
            stream.flush()
            cleanup()
            entry = {'round': number, 'tests': result.testsRun, 'failures': len(result.failures),
                     'errors': len(result.errors), 'skipped': len(result.skipped),
                     'elapsed_seconds': round(time.monotonic() - round_start, 3),
                     'ok': result.wasSuccessful(), 'resources': resources()}
            report['rounds'].append(entry)
            report['tests'] += result.testsRun
            (output / 'UI_Soak_Result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(entry), flush=True)
            if not result.wasSuccessful():
                break
    after = code_hashes()
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    counts = [item['resources'].get('qt_top_level_widgets', 0) for item in report['rounds']]
    widget_growth = bool(counts and any(count > counts[0] for count in counts[1:]))
    report.update(elapsed_seconds=round(time.monotonic() - started, 3),
                  code_changed_during_run=changed, unexpected_real_gmail_requests=blocked,
                  retained_top_level_widget_counts=counts, top_level_widget_growth=widget_growth,
                  ok=len(report['rounds']) == rounds and all(item['ok'] for item in report['rounds'])
                     and not changed and not blocked and not widget_growth)
    (output / 'UI_Soak_Result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('rounds', 'tested_source_hashes')}), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/abnahme/A7_Workflow/UI_Soak')
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:
        parser.error('rounds must be 1..100')
    sys.exit(run(args.rounds, args.output.resolve()))
