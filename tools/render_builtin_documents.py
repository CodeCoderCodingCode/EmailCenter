"""Run the skill renderer with the release's portable converter, never desktop LO."""
import os
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
runtime = Path('C:/Users/timon/.cache/codex-runtimes/codex-primary-runtime/dependencies')
os.environ['PATH'] = str(ROOT / '.tools/libreoffice/program') + os.pathsep + str(runtime / 'native/poppler/Library/bin') + os.pathsep + os.environ['PATH']
os.environ['TEMP'] = os.environ['TMP'] = str(ROOT / 'docs/abnahme/B_Release/Templates')
# Some LO extension workers retain profile files briefly on Windows. Keep those
# task-local intermediates when cleanup races; still require render success.
original = tempfile.TemporaryDirectory
class Temporary(original):
    def __init__(self, *args, **kwargs):
        kwargs['ignore_cleanup_errors'] = True
        super().__init__(*args, **kwargs)
tempfile.TemporaryDirectory = Temporary
renderer = Path('C:/Users/timon/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/render_docx.py')
for path in sorted((ROOT / 'assets/templates').glob('*.docx')):
    sys.argv = [str(renderer), str(path), '--output_dir', str(ROOT / 'docs/abnahme/B_Release/Templates' / path.stem), '--emit_pdf']
    runpy.run_path(str(renderer), run_name='__main__')
