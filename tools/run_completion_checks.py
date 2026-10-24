"""Run local regression checks and record which code was actually checked."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def code_hashes():
    paths = [ROOT / 'requirements.txt']
    for folder, pattern in (('src', '*.py'), ('tests', '*.py'), ('migrations', '*.sql')):
        paths.extend((ROOT / folder).rglob(pattern))
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if '__pycache__' not in path.parts}


def run(output=None, evidence=None):
    output = Path(output or ROOT / 'docs/38_Localization_Full_Test_Output.txt').resolve()
    evidence = Path(evidence or ROOT / 'docs/abnahme/A5_Localization/Full_Test_Result.json').resolve()
    if not output.is_relative_to(ROOT) or not evidence.is_relative_to(ROOT):
        raise ValueError('Completion reports must stay within the workspace.')
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    before = code_hashes()
    environment = {**os.environ, 'PYTHONPATH': os.pathsep.join((str(ROOT / 'src'), str(ROOT / 'tests'))),
                   'PYTHONIOENCODING': 'utf-8', 'QT_QPA_PLATFORM': 'offscreen', 'TEMP': str(ROOT), 'TMP': str(ROOT)}
    started = time.monotonic()
    with output.open('w', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, '-X', 'faulthandler', '-m', 'unittest',
                                 'discover', '-s', 'tests', '-v'], cwd=ROOT, env=environment,
                                stdout=stream, stderr=subprocess.STDOUT)
    content = output.read_text(encoding='utf-8', errors='replace')
    summary = re.search(r'Ran (\d+) tests in ([\d.]+)s', content)
    skipped = re.search(r'^(?:OK|FAILED)\s*\([^\n]*\bskipped=(\d+)', content, re.MULTILINE)
    after = code_hashes()
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    report = {'exit_code': result.returncode, 'tests': int(summary[1]) if summary else None,
              'skipped': int(skipped[1]) if skipped else 0, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'code_changed_during_run': changed, 'tested_source_hashes': before,
              'ok': result.returncode == 0 and summary is not None and not changed,
              'native_windows_acceptance': False}
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'tested_source_hashes'}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    sys.exit(run(args.output, args.evidence))
