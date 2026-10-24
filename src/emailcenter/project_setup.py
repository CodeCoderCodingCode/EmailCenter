"""Validate optional initial project records before creating any files."""

from .language import translate as _ui_tr, format_text as _ui_format

from .mail_models import address, header
import json


def initial_records(profile=None, signature=None):
    result = []
    for fields, allowed, required in (
        (profile, {"display_name": 200, "email": 254, "phone": 80, "address_json": 65536, "custom_fields_json": 65536}, "display_name"),
        (signature, {"name": 200, "content_text": 100000}, "name"),
    ):
        if fields is None:
            result.append(None)
            continue
        if not isinstance(fields, dict) or set(fields) - set(allowed):
            raise ValueError(_ui_tr('Ungültige Angaben für Profil oder Signatur.'))
        values = {}
        for key, maximum in allowed.items():
            if key.endswith("_json") and key not in fields:
                continue
            value = fields.get(key, "")
            if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
                raise ValueError(_ui_format('Ungültige Angabe: {0} (maximal {1} Zeichen).', f'{key}', f'{maximum}'))
            values[key] = value.strip()
            if key.endswith("_json"):
                try:
                    parsed = json.loads(value)
                    if not isinstance(parsed, dict):
                        raise ValueError()
                    values[key] = json.dumps(parsed, ensure_ascii=False, allow_nan=False)
                except (ValueError, TypeError, RecursionError):
                    raise ValueError(_ui_tr('Profiladresse und eigene Profilfelder müssen gültige Objekte sein.')) from None
        if not values[required]:
            raise ValueError(_ui_tr('Bitte einen Namen für Profil oder Signatur eingeben.'))
        header(values[required], _ui_tr('Name'))
        if required == "display_name" and values["email"]:
            values["email"] = address(values["email"])
        if required == "name" and not values["content_text"]:
            raise ValueError(_ui_tr('Bitte einen Signaturtext eingeben.'))
        result.append(values)
    return tuple(result)
