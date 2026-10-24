"""Compare static imports with bundled DLL exports; no DLL execution."""
from pathlib import Path
import pefile
import hashlib

ROOT=Path(__file__).resolve().parents[1]
internal=ROOT/'dist/runtime/EmailCenter/_internal'
folders=[internal,internal/'PySide6',internal/'shiboken6',Path('C:/Windows/System32')]
done=set()
def check(path):
    if path.name.lower() in done:return
    done.add(path.name.lower())
    pe=pefile.PE(str(path),fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
        name=entry.dll.decode()
        if name.lower().startswith(('api-','ext-')):continue
        target=next((folder/name for folder in folders if (folder/name).is_file()),None)
        if target is None:
            print('UNRESOLVED',path.name,name);continue
        if target.parent==Path('C:/Windows/System32'):continue
        lib=pefile.PE(str(target),fast_load=True)
        lib.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
        exports={e.name for e in getattr(getattr(lib,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[])}
        for imp in entry.imports:
            if imp.name and imp.name not in exports:print('MISSING PROCEDURE',path.name,name,imp.name.decode(errors='replace'))
        check(target)
for file in (internal/'PySide6').glob('*.pyd'):check(file)
for name in ('Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','pyside6.abi3.dll'):
    a=internal/'PySide6'/name;b=ROOT/'.venv/Lib/site-packages/PySide6'/name
    print('IDENTICAL',name,hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest(),a.stat().st_size,b.stat().st_size)
