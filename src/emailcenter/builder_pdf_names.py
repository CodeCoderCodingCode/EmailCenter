"""Literal, source-aware PDF filenames; placeholder values cannot become paths."""
import re
from pathlib import Path

from .bulk_sources import column_fields
from .language import translate as _ui_tr, format_text as _ui_format
from .mail_models import MailError

TOKEN = re.compile(r'\{\{([^{}\r\n\x00]*)\}\}')


def filename_fields(pattern):
    if not isinstance(pattern, str) or len(pattern) > 250 or any(c in pattern for c in '\x00\r\n'):
        raise MailError(_ui_tr('PDF-Dateinamensmuster ist ungültig (maximal 250 Zeichen, keine Zeilenumbrüche).'))
    names = [name.strip() for name in TOKEN.findall(pattern)]
    rest = TOKEN.sub('', pattern)
    if '{{' in rest or '}}' in rest or any(not name or len(name) > 200 for name in names):
        raise MailError(_ui_tr('PDF-Dateiname: Platzhalter vollständig als {{Spaltenname}} angeben.'))
    return sorted(set(names))


def pdf_filename(pattern, fields, original_filename, *, source_headers=()):
    filename_fields(pattern)
    if pattern.strip():
        aliases = {header: alias for alias, header in column_fields(list(source_headers)).items()}
        def substitute(match):
            name = match.group(1).strip()
            value = fields.get(aliases.get(name, name), '')
            if not value.strip():
                raise MailError(_ui_format('Datenfeld für PDF-Dateiname fehlt: {0}', name))
            return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', value).strip().rstrip(' .')
        filename = TOKEN.sub(substitute, pattern).strip()
    else:
        filename = Path(original_filename).stem + '.pdf'
    if not filename.lower().endswith('.pdf'):
        raise MailError(_ui_tr('PDF-Dateiname muss mit .pdf enden, z. B. Anschreiben{{Unternehmen}}.pdf.'))
    if (len(filename) > 250 or not filename[:-4].strip(' .') or re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
            or filename.rstrip(' .') != filename
            or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', filename.split('.')[0])):
        raise MailError(_ui_tr('PDF-Dateiname ist ungültig; nur einen Dateinamen mit höchstens 250 Zeichen verwenden.'))
    return filename
