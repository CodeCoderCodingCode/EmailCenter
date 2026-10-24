"""Small, validated application preferences with atomic file replacement."""

from .language import translate as _ui_tr, format_text as _ui_format

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .shortcuts import default_shortcuts, validate_shortcuts, default_canvas_shortcuts, validate_canvas_shortcuts
from .appearance import THEMES


@dataclass(frozen=True)
class Preferences:
    theme: str = "light"
    accent: str = "#2862c4"
    timezone_id: str = "Europe/Berlin"
    export_format: str = "csv"
    export_directory: str = ""
    csv_delimiter: str = ";"
    csv_encoding: str = "utf-8-sig"
    word_replace_case_sensitive: bool = True
    word_replace_whole_words: bool = False
    word_replace_missing: str = "error"
    word_replace_format: str = "docx"
    word_replace_directory: str = ""
    word_replace_style: str = "first"
    word_replace_filename_pattern: str = ""
    libreoffice_path: str = ""
    conversion_timeout: int = 120
    shortcuts: dict = field(default_factory=default_shortcuts)
    canvas_shortcuts: dict = field(default_factory=default_canvas_shortcuts)
    builder_grid: bool = True
    builder_snap: bool = True
    builder_zoom: int = 100
    builder_autosave: bool = True
    builder_autosave_seconds: int = 3
    builder_palette_width: int = 180
    builder_inspector_width: int = 320
    builder_show_palette: bool = True
    builder_show_inspector: bool = True
    builder_compact_tools: bool = False
    reduced_motion: bool = False
    transition_style: str = 'theme'
    animation_ms: int = 180
    hover_feedback: bool = True
    builder_preview_delay_ms: int = 180
    guided_workspace: bool = True
    tooltips_enabled: bool = True
    toast_seconds: int = 6
    toast_info: bool = True
    toast_success: bool = True
    toast_persistent_errors: bool = True
    language: str = "de"
    workspace_mode: str = "applications"
    start_page: str = "workspace"
    mail_account_email: str = ""
    mail_signature_name: str = ""
    mail_body_format: str = "plain"
    mail_timezone_id: str = "Europe/Berlin"
    mail_delivery_mode: str = "drafts"
    mail_interval_seconds: int = 1
    mail_daily_budget: int = 100
    mail_window_start: str = "00:00"
    mail_window_end: str = "00:00"
    list_page_size: int = 50
    list_alternating_rows: bool = True
    list_word_wrap: bool = True
    list_compact_rows: bool = False
    backup_directory: str = ""
    backup_retention: int = 0
    builder_default_blocks: list = field(default_factory=lambda: ["text"])

    @classmethod
    def validate(cls, values):
        if not isinstance(values, dict) or not {"theme", "accent", "timezone_id"} <= set(values) or set(values) - set(cls().values()):
            raise ValueError(_ui_tr('Ungültige Einstellungsfelder.'))
        values = {**cls().values(), **values}
        if not isinstance(values["theme"], str) or values["theme"] not in THEMES:
            raise ValueError(_ui_tr('Bitte ein verfügbares Design auswählen.'))
        if not isinstance(values["accent"], str) or re.fullmatch(r"#[0-9a-fA-F]{6}", values["accent"]) is None:
            raise ValueError(_ui_tr('Ungültige Akzentfarbe. Erwartet wird beispielsweise #2862c4.'))
        try:
            ZoneInfo(values["timezone_id"])
        except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
            raise ValueError(_ui_tr('Unbekannte Zeitzone. Beispielsweise Europe/Berlin oder UTC eingeben.')) from error
        choices = {"export_format": ("csv", "xlsx"), "csv_delimiter": (";", ",", "\t"),
                   "csv_encoding": ("utf-8-sig", "utf-8", "cp1252", "utf-16"),
                   "word_replace_missing": ("error", "keep"), "word_replace_format": ("docx", "pdf"),
                   "word_replace_style": ("first", "plain", "bold", "italic")}
        choices.update(language=("de", "en"), workspace_mode=("applications", "mail"),
                       start_page=("workspace", "overview", "builder", "word_replace"),
                       mail_body_format=("plain", "html"), mail_delivery_mode=("drafts", "now", "scheduled"), transition_style=('theme', 'fade', 'slide', 'zoom', 'none'))
        for key, allowed in choices.items():
            if values[key] not in allowed:
                raise ValueError(_ui_format('Ungültige Einstellung: {0}', key))
        for key in ("word_replace_case_sensitive", "word_replace_whole_words", "builder_grid", "builder_snap", "builder_autosave", "builder_show_palette", "builder_show_inspector", "builder_compact_tools", "reduced_motion", "toast_info", "toast_success", "toast_persistent_errors"):
            if type(values[key]) is not bool:
                raise ValueError(_ui_format('Ungültiger Schalter: {0}', key))
        for key in ("list_alternating_rows", "list_word_wrap", "list_compact_rows", 'hover_feedback', 'guided_workspace', 'tooltips_enabled'):
            if type(values[key]) is not bool:
                raise ValueError(_ui_format('Ungültiger Schalter: {0}', key))
        for key in ("export_directory", "word_replace_directory", "libreoffice_path", "backup_directory"):
            path = values[key]
            if not isinstance(path, str) or len(path) > 2048 or any(c in path for c in "\x00\r\n") or (path and not Path(path).is_absolute()):
                raise ValueError(_ui_format('Für {0} einen absoluten Pfad eingeben oder das Feld leer lassen.', key))
        for key in ("mail_account_email", "mail_signature_name"):
            if not isinstance(values[key], str) or len(values[key]) > 254 or any(c in values[key] for c in "\x00\r\n"):
                raise ValueError(_ui_format('Ungültige E-Mail-Vorgabe: {0}', key))
        if values["mail_account_email"]:
            from .mail_models import address
            address(values["mail_account_email"])
        try:
            ZoneInfo(values["mail_timezone_id"])
        except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
            raise ValueError(_ui_tr('Unbekannte Versandzeitzone.')) from error
        from .delivery_policy import validate_policy
        validate_policy(values["mail_daily_budget"], values["mail_window_start"], values["mail_window_end"])
        for key, minimum, maximum in (("mail_interval_seconds", 1, 3600), ("list_page_size", 10, 200), ("backup_retention", 0, 1000), ('animation_ms', 60, 1000), ('builder_preview_delay_ms', 0, 2000)):
            if type(values[key]) is not int or not minimum <= values[key] <= maximum:
                raise ValueError(_ui_format('{0}: Wert zwischen {1} und {2} wählen.', f'{key}', f'{minimum}', f'{maximum}'))
        blocks = values["builder_default_blocks"]
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 10 or any(not isinstance(k, str) or k not in ("text", "description", "paragraph", "heading", "html", "greeting", "closing", "separator", "list") for k in blocks) or len(set(blocks)) != len(blocks):
            raise ValueError(_ui_tr('Mindestens einen eindeutigen Standard-Textbaustein wählen.'))
        if type(values["conversion_timeout"]) is not int or not 10 <= values["conversion_timeout"] <= 600:
            raise ValueError(_ui_tr('PDF-Zeitlimit muss zwischen 10 und 600 Sekunden liegen.'))
        if type(values["builder_zoom"]) is not int or not 25 <= values["builder_zoom"] <= 250:
            raise ValueError(_ui_tr('Builder-Zoom muss zwischen 25 und 250 Prozent liegen.'))
        if type(values["builder_autosave_seconds"]) is not int or not 1 <= values["builder_autosave_seconds"] <= 60:
            raise ValueError(_ui_tr('Autosicherungsabstand muss zwischen 1 und 60 Sekunden liegen.'))
        from .filename_patterns import validate_pattern
        validate_pattern(values["word_replace_filename_pattern"])
        for key, minimum, maximum in (("builder_palette_width", 150, 320), ("builder_inspector_width", 220, 700), ("toast_seconds", 2, 30)):
            if type(values[key]) is not int or not minimum <= values[key] <= maximum:
                raise ValueError(_ui_format('{0}: Wert zwischen {1} und {2} wählen.', f'{key}', f'{minimum}', f'{maximum}'))
        shortcuts = validate_shortcuts(values["shortcuts"])
        canvas = validate_canvas_shortcuts(values["canvas_shortcuts"], shortcuts)
        return cls(**{**values, "accent": values["accent"].lower(), "shortcuts": shortcuts, "canvas_shortcuts": canvas})

    def values(self):
        return asdict(self)


class PreferencesStore:
    def __init__(self, path):
        self.path = Path(path)
        self._revision = None
        self._unsupported = False

    def _read(self):
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 65536:
            raise ValueError(_ui_tr('Einstellungsdatei ist zu groß.'))
        return self.path.read_bytes()

    def load(self):
        defaults = Preferences()
        self._unsupported = False
        try:
            content = self._read()
            self._revision = hashlib.sha256(content).hexdigest() if content is not None else None
            if content is None:
                return defaults, None
            values = json.loads(content.decode("utf-8"))
            if not isinstance(values, dict):
                raise ValueError(_ui_tr('Einstellungsdatei enthält kein Objekt.'))
            if type(values.get("version")) is not int or values["version"] != 1:
                self._unsupported = True
                raise ValueError(_ui_tr('Einstellungsformat wird nicht unterstützt. Die Datei bleibt unverändert.'))
            result, invalid = defaults.values(), []
            for key in result:
                if key in ("shortcuts", "canvas_shortcuts"):
                    continue
                try:
                    candidate = Preferences.validate({**defaults.values(), key: values.get(key, result[key])})
                    result[key] = candidate.values()[key]
                except ValueError:
                    invalid.append(key)
            try:
                result["shortcuts"] = validate_shortcuts(values.get("shortcuts", result["shortcuts"]))
            except ValueError:
                invalid.append("shortcuts")
            try:
                result["canvas_shortcuts"] = validate_canvas_shortcuts(values.get("canvas_shortcuts", result["canvas_shortcuts"]), {})
            except ValueError:
                invalid.append("canvas_shortcuts")
            # Preserve old app bindings; newly introduced conflicting canvas defaults are disabled.
            for action, key in result["canvas_shortcuts"].items():
                if key and key in result["shortcuts"].values():
                    result["canvas_shortcuts"][action] = ""
                    if "canvas_shortcuts" not in invalid:
                        invalid.append("canvas_shortcuts")
            warning = _ui_format('Ungültige Einstellungen verwenden Standardwerte: {0}', ', '.join(invalid)) if invalid else None
            return Preferences.validate(result), warning
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            return defaults, _ui_format('Einstellungen konnten nicht vollständig geladen werden: {0}', str(error))

    def save(self, preferences):
        preferences = Preferences.validate(preferences.values())
        if self._unsupported:
            raise ValueError(_ui_tr('Dieses Einstellungsformat kann nicht überschrieben werden. Bitte eine passende Programmversion verwenden.'))
        current = self._read()
        revision = hashlib.sha256(current).hexdigest() if current is not None else None
        if revision != self._revision:
            raise ValueError(_ui_tr('Einstellungen wurden zwischenzeitlich geändert. Bitte Neu laden und erneut bearbeiten.'))
        content = (json.dumps({"version": 1, **preferences.values()}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.path.parent, prefix=".preferences-", suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            self._revision = hashlib.sha256(content).hexdigest()
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return preferences
