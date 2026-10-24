"""Bounded filename interpolation without Python attribute/index evaluation."""

from .language import translate as _ui_tr, format_text as _ui_format

import re
from string import Formatter
from .bulk_sources import FIELD_NAME


def validate_pattern(pattern):
    if not isinstance(pattern, str) or len(pattern) > 200 or any(c in pattern for c in '<>:"/\\|?*\r\n\x00'):
        # A colon inside the numeric format specifier is explicitly allowed below.
        cleaned = re.sub(r"\{number:0[1-6]d\}", "{number}", pattern) if isinstance(pattern, str) else ""
        if not isinstance(pattern, str) or len(pattern) > 200 or any(c in cleaned for c in '<>:"/\\|?*\r\n\x00'):
            raise ValueError(_ui_tr('Dateinamensmuster ist ungültig (maximal 200 Zeichen).'))
    try:
        for _, field, spec, conversion in Formatter().parse(pattern):
            if field is not None and (not FIELD_NAME.fullmatch(field) or conversion or (spec and not (field == "number" and re.fullmatch(r"0[1-6]d", spec)))):
                raise ValueError(_ui_tr('Platzhalter verwenden: {prefix}, {number:03d}, {name} oder {Datenfeld}.'))
    except ValueError as error:
        raise ValueError(_ui_format('Dateinamensmuster prüfen: {0}', str(error))) from error
    return pattern


def output_name(prefix, number, name, fields, file_format, pattern="", *, multiple=True):
    validate_pattern(pattern)
    def safe(value):
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip().rstrip(". ")[:80]
    if pattern:
        values = {**fields, "prefix": prefix, "number": number, "name": name or "Einzeldatei"}
        parts = []
        for literal, field, spec, _ in Formatter().parse(pattern):
            parts.append(literal)
            if field:
                if field not in values or (field not in ("name", "prefix", "number") and not str(values[field]).strip()):
                    raise ValueError(_ui_format('Datenfeld für Dateiname fehlt: {0}', field))
                parts.append(format(number, spec) if spec else safe(values[field]))
        stem = "".join(parts).strip().rstrip(". ")
    else:
        suffix = f"-{number:03d}" + ("-" + re.sub(r"[^\w -]", "", name)[:70].strip() if name else "") if multiple else ""
        stem = prefix.strip().rstrip(". ") + suffix
    if not stem or len(stem) > 200 or stem in (".", "..") or any(c in stem for c in '<>:"/\\|?*\r\n\x00') or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", stem, re.I):
        raise ValueError(_ui_tr('Muster ergibt keinen gültigen Dateinamen.'))
    return stem + "." + file_format
