"""Create a verified local code archive, separate from user project backups."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def selected_files():
    files = set()
    patterns = {
        'src': {'*.py'}, 'tests': {'*.py'}, 'migrations': {'*.sql'},
        'tools': {'*.py'}, 'assets': {'Logo256.png'}, 'doc': {'*.txt'},
    }
    for directory, globs in patterns.items():
        for pattern in globs:
            files.update((ROOT / directory).rglob(pattern))
    for name in ('README_START_HERE.txt', 'requirements.txt', 'start_emailcenter.py',
                 'Start_EmailCenter.cmd', '04_Migration_v1.sql'):
        files.add(ROOT / name)
    for pattern in ('*.md', '*.txt'):
        files.update((ROOT / 'docs').glob(pattern))
    files.add(ROOT / 'docs/Runtime_Inventory.json')
    for name in ('Catalog_Audit.json', 'Catalog_Review.json'):
        files.add(ROOT / 'docs/localization' / name)
    files.update(p for p in (ROOT / 'docs/third_party').rglob('*') if p.is_file())
    for path in sorted(files):
        if '__pycache__' in path.parts:
            continue
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f'Unsupported snapshot source: {path}')
        yield path


def create_snapshot():
    directory = ROOT / 'docs/abnahme'
    directory.mkdir(exist_ok=True)
    created = datetime.now(timezone.utc)
    archive_path = directory / f'Code_Completion_{created:%Y%m%dT%H%M%S%fZ}.zip'
    schema_version = max(int(path.name.split('_', 1)[0]) for path in (ROOT / 'migrations').glob('*.sql'))
    manifest = {'format_version': 1, 'schema_version': schema_version,
                'created_at_utc': created.isoformat(), 'files': {}}
    with tempfile.TemporaryDirectory(prefix='code-snapshot-', dir=directory) as temporary:
        staged = Path(temporary) / 'code.zip'
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in selected_files():
                name = path.relative_to(ROOT).as_posix()
                data = path.read_bytes()
                manifest['files'][name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                archive.writestr(name, data)
            archive.writestr('CODE_MANIFEST.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive CRC check failed.')
            for name, expected in manifest['files'].items():
                data = archive.read(name)
                if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                    raise ValueError(f'Archive content check failed: {name}')
        staged.rename(archive_path)
    result = {'status': 'Completed', 'archive': archive_path.name,
              'sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
              'created_at_utc': created.isoformat(), 'schema_version': schema_version,
              'file_count': len(manifest['files']), 'crc_and_content_hashes_verified': True,
              'contains_user_projects_or_credentials': False,
              'contains_bundled_runtimes': False, 'installer': False}
    report = directory / 'Code_Snapshot.json'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        staged_report = Path(stream.name)
    try:
        staged_report.replace(report)
    finally:
        staged_report.unlink(missing_ok=True)
    return result


if __name__ == '__main__':
    print(json.dumps(create_snapshot(), indent=2))
