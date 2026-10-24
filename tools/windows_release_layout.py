"""Reject incomplete onedir bundles before making an installer."""
from pathlib import Path


REQUIRED = (
    'EmailCenter.exe',
    '_internal/python313.dll',
    '_internal/python3.dll',
    '_internal/base_library.zip',
    '_internal/vcruntime140.dll',
    '_internal/PySide6/Qt6Core.dll',
    '_internal/PySide6/Qt6Gui.dll',
    '_internal/PySide6/Qt6Widgets.dll',
    '_internal/PySide6/plugins/platforms/qwindows.dll',
    '_internal/LibreOffice/program/soffice.com',
    '_internal/guide/EmailCenter_Guide.html',
    '_internal/assets/oauth/desktop_client.json',
)


def validate_bundle(directory):
    root = Path(directory).resolve()
    missing = [name for name in REQUIRED
               if not (root / name).is_file() or (root / name).stat().st_size == 0]
    if missing:
        raise RuntimeError('Incomplete EmailCenter runtime: ' + ', '.join(missing))
    if (root / '_internal/icuuc.dll').exists():
        raise RuntimeError('Incompatible ICU at the runtime root; use the Windows ICU for Qt.')
    return root


def retire_intermediate_executable(workspace):
    """The build EXE alone cannot run. COLLECT has already copied the real app."""
    workspace = Path(workspace).resolve()
    runtime = validate_bundle(workspace / 'dist/runtime/EmailCenter')
    build = (workspace / 'build/pyinstaller/EmailCenter').resolve()
    if not build.is_relative_to(workspace / 'build') or build == runtime:
        raise RuntimeError('Unexpected intermediate directory.')
    executable = build / 'EmailCenter.exe'
    if executable.exists():
        if executable.read_bytes() != (runtime / 'EmailCenter.exe').read_bytes():
            raise RuntimeError('Intermediate executable differs from the collected application.')
        executable.unlink()
    build.mkdir(parents=True, exist_ok=True)
    (build / 'NICHT_HIER_STARTEN.txt').write_text(
        'Dieser Ordner enthaelt nur Build-Zwischendateien.\n'
        'Installation: dist/release/EmailCenter-Setup-1.0.1-Windows-x64.exe\n'
        'Oder im Projektordner: Install_EmailCenter.cmd bzw. Start_EmailCenter.cmd.\n'
        'Die vollstaendige portable App liegt unter dist/runtime/EmailCenter.\n'
        'EmailCenter.exe und der komplette Ordner _internal gehoeren zusammen.\n',
        encoding='utf-8')
