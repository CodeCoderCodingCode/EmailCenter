"""Keep Qt/Shiboken DLL search handles alive in a Windows frozen application."""
import os
import sys
from pathlib import Path

_qt_dll_handles = []
if sys.platform == 'win32' and hasattr(os, 'add_dll_directory'):
    for _name in ('PySide6', 'shiboken6'):
        _directory = Path(sys._MEIPASS) / _name
        if _directory.is_dir():
            _qt_dll_handles.append(os.add_dll_directory(str(_directory)))

if os.environ.get('EMAILCENTER_DEBUG_IMPORTS') == '1':
    import builtins
    import traceback
    _original_import = builtins.__import__
    def _diagnostic_import(name, *args, **kwargs):
        try:
            return _original_import(name, *args, **kwargs)
        except ImportError:
            if name.startswith(('PySide6', 'shiboken6')):
                traceback.print_exc(file=sys.stderr)
            raise
    builtins.__import__ = _diagnostic_import
