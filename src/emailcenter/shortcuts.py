"""Portable single-key bindings; editing keys and send actions stay separate."""

from .language import translate as _ui_tr, format_text as _ui_format

import re


SHORTCUTS = {
    "new": ("Neues Projekt", "Ctrl+N"), "open": ("Projekt öffnen", "Ctrl+O"),
    "refresh": ("Aktualisieren", "F5"), "workspace": ("Arbeitsbereich", "Ctrl+1"),
    "word_replace": ("Word Replace", "Ctrl+2"), "settings": ("Einstellungen", "Ctrl+Alt+S"),
    "export": ("Datenexport", "Ctrl+Shift+E"), "search": ("Suchfeld fokussieren", "Ctrl+F"),
    "save": ("Aktuelles Formular speichern", "Ctrl+S"), "help": ("Hilfe / Guide", "F1"),
}
EDITING_KEYS = {"Ctrl+" + key for key in "ABCDEHIJKLTUVWXYZ"} | {"Ctrl+Shift+Z", "Ctrl+Shift+Y"}
CANVAS_SHORTCUTS = {
    "next_node": ("Nächster Baustein", "Alt+Right"), "previous_node": ("Voriger Baustein", "Alt+Left"),
    "next_port": ("Nächster Stecker", "Alt+Down"), "previous_port": ("Voriger Stecker", "Alt+Up"),
    "connect": ("Stecker aktivieren / verbinden", "Return"), "cancel": ("Verbindung / Auswahl abbrechen", "Escape"),
    "next_edge": ("Nächste Verbindung auswählen", "Alt+E"), "delete": ("Auswahl löschen", "Delete"),
    "duplicate": ("Baustein duplizieren", "Ctrl+D"), "undo": ("Rückgängig", "Ctrl+Z"), "redo": ("Wiederholen", "Ctrl+Y"),
    "zoom_in": ("Vergrößern", "Ctrl+Up"), "zoom_out": ("Verkleinern", "Ctrl+Down"), "fit": ("Graph einpassen", "Ctrl+0"),
}


def default_canvas_shortcuts():
    return {key: value[1] for key, value in CANVAS_SHORTCUTS.items()}


def normalize_canvas_shortcut(value):
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError(_ui_tr('Canvas-Kürzel müssen Text sein.'))
    if not value.strip():
        return ""
    parts = [part.strip().upper() for part in value.split("+")]
    aliases = {"CTRL": "Ctrl", "CONTROL": "Ctrl", "STRG": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "UMSCHALT": "Shift"}
    keys = {key.upper(): key for key in ("Delete", "Backspace", "Left", "Right", "Up", "Down", "Return", "Space", "Escape", "Home", "End", "PageUp", "PageDown")}
    keys.update({"ENTF": "Delete", "DEL": "Delete", "ENTER": "Return", "ESC": "Escape", "LEERTASTE": "Space", "PGUP": "PageUp", "PGDOWN": "PageDown"})
    key, modifiers = parts[-1], parts[:-1]
    if any(part not in aliases for part in modifiers) or len(set(aliases.get(part) for part in modifiers)) != len(modifiers):
        raise ValueError(_ui_tr('Ungültige Canvas-Modifikatoren.'))
    if key not in keys and not re.fullmatch(r"[A-Z0-9]|F(?:[1-9]|1[0-2])", key):
        raise ValueError(_ui_tr('Canvas: Ctrl/Alt/Shift mit Taste, Pfeiltaste, Return, Escape oder Delete verwenden.'))
    result = "+".join([*(m for m in ("Ctrl", "Alt", "Shift") if m in [aliases[p] for p in modifiers]), keys.get(key, key)])
    if result in ("Alt+F4", "Alt+Space", "Ctrl+Escape", "Ctrl+Alt+Delete"):
        raise ValueError(_ui_format('Dieses Kürzel bleibt für Windows reserviert: {0}', result))
    return result


def validate_canvas_shortcuts(values, app_shortcuts=None):
    if not isinstance(values, dict) or set(values) - set(CANVAS_SHORTCUTS):
        raise ValueError(_ui_tr('Unbekannte Canvas-Aktion.'))
    result, used = {}, {}
    global_keys = set((default_shortcuts() if app_shortcuts is None else app_shortcuts).values()) - {""}
    for action, value in {**default_canvas_shortcuts(), **values}.items():
        key = normalize_canvas_shortcut(value)
        if key and (key in used or key in global_keys):
            raise ValueError(_ui_format('Canvas-Tastenkürzel doppelt oder bereits als App-Hotkey belegt: {0}', key))
        result[action] = key
        if key:
            used[key] = action
    return result


def default_shortcuts():
    return {key: value[1] for key, value in SHORTCUTS.items()}


def normalize_shortcut(value):
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError(_ui_tr('Tastenkürzel müssen Text sein.'))
    if not value.strip():
        return ""
    parts = [part.strip().upper() for part in value.split("+")]
    key, modifiers = parts[-1], parts[:-1]
    aliases = {"CTRL": "Ctrl", "CONTROL": "Ctrl", "STRG": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "UMSCHALT": "Shift"}
    if re.fullmatch(r"[A-Z0-9]|F(?:[1-9]|1[0-2])", key) is None or any(part not in aliases for part in modifiers):
        raise ValueError(_ui_tr('Ein Kürzel wie Ctrl+Shift+E, Alt+W oder F5 eingeben; leer deaktiviert die Aktion.'))
    normalized = [aliases[part] for part in modifiers]
    function_key = len(key) > 1 and key.startswith("F")
    if len(set(normalized)) != len(normalized) or (not function_key and not {"Ctrl", "Alt"}.intersection(normalized)):
        raise ValueError(_ui_tr('Buchstaben/Ziffern benötigen Ctrl oder Alt; doppelte Modifikatoren sind ungültig.'))
    result = "+".join([*(part for part in ("Ctrl", "Alt", "Shift") if part in normalized), key])
    if result in EDITING_KEYS or result == "Alt+F4":
        raise ValueError(_ui_format('Dieses Kürzel bleibt für Texteingaben oder Windows reserviert: {0}', result))
    return result


def validate_shortcuts(values):
    if not isinstance(values, dict) or set(values) - set(SHORTCUTS):
        raise ValueError(_ui_tr('Unbekannte Tastaturaktion.'))
    result, used = {}, {}
    for action, value in {**default_shortcuts(), **values}.items():
        key = normalize_shortcut(value)
        if key and key in used:
            raise ValueError(_ui_format('Tastenkürzel doppelt: {0} · {1} / {2}', key, _ui_tr(SHORTCUTS[used[key]][0]), _ui_tr(SHORTCUTS[action][0])))
        result[action] = key
        if key:
            used[key] = action
    return result
