"""Portable bindings and persisted conflicts without a running GUI."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.shortcuts import SHORTCUTS, default_shortcuts, normalize_shortcut, validate_shortcuts


class ShortcutTests(unittest.TestCase):
    def test_defaults_are_unique_and_have_no_send_action(self):
        defaults = default_shortcuts()
        self.assertEqual(validate_shortcuts(defaults), defaults)
        self.assertEqual(len(set(defaults.values())), len(defaults))
        self.assertFalse({"send", "approve", "retry"} & set(SHORTCUTS))

    def test_aliases_case_and_modifier_order_are_normalized(self):
        self.assertEqual(normalize_shortcut(" shift + STRG + e "), "Ctrl+Shift+E")
        self.assertEqual(normalize_shortcut("alt+control+s"), "Ctrl+Alt+S")
        self.assertEqual(normalize_shortcut("f12"), "F12")
        self.assertEqual(normalize_shortcut("  "), "")

    def test_typing_editing_system_and_multiple_key_sequences_rejected(self):
        for value in ("A", "F", "Shift+F", "Shift+A", "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+K", "Ctrl+U", "Ctrl+H", "Ctrl+Shift+Z", "Alt+F4", "Meta+N",
                      "Ctrl+Ctrl+A", "Ctrl+K, Ctrl+C", "Ctrl+", "F13", "Ctrl+Space", "Ctrl+Ä", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_shortcut(value)

    def test_conflicts_include_canonical_aliases_and_implicit_defaults(self):
        for values in ({"new": "strg+o"}, {"save": "Shift+Ctrl+E"}, {"help": "F5"}):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "doppelt"):
                validate_shortcuts(values)

    def test_disabled_actions_and_partial_legacy_mapping(self):
        values = validate_shortcuts({"new": "", "help": "Ctrl+N"})
        self.assertEqual(values["new"], "")
        self.assertEqual(values["help"], "Ctrl+N")
        self.assertEqual(values["open"], "Ctrl+O")
        first, second = Preferences(), Preferences()
        first.shortcuts["new"] = ""
        self.assertEqual(second.shortcuts["new"], "Ctrl+N")

    def test_unknown_actions_and_invalid_mapping_rejected(self):
        for values in ({"send": "Ctrl+Enter"}, [], None, {"save": 1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_shortcuts(values)

    def test_bindings_roundtrip_and_old_preferences_keep_defaults(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "preferences.json"
            path.write_text('{"version":1,"theme":"dark","accent":"#2862c4","timezone_id":"UTC"}', encoding="utf-8")
            store = PreferencesStore(path)
            original, warning = store.load()
            self.assertIsNone(warning)
            self.assertEqual(original.shortcuts, default_shortcuts())
            configured = Preferences.validate({**original.values(), "shortcuts": {"refresh": "strg+r", "export": ""}})
            store.save(configured)
            self.assertEqual(PreferencesStore(path).load(), (configured, None))

    def test_invalid_stored_bindings_warn_without_losing_other_preferences(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "preferences.json"
            content = json.dumps({"version": 1, **Preferences(theme="dark").values(), "shortcuts": {"new": "Ctrl+O"}})
            path.write_text(content, encoding="utf-8")
            preferences, warning = PreferencesStore(path).load()
            self.assertEqual(preferences.theme, "dark")
            self.assertEqual(preferences.shortcuts, default_shortcuts())
            self.assertIn("shortcuts", warning)
            self.assertEqual(path.read_text(encoding="utf-8"), content)
