"""Validated, durable preferences without touching real user settings."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.preferences import Preferences, PreferencesStore


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.temporary.name) / "config" / "preferences.json"
        self.store = PreferencesStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, content):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(content)

    def test_missing_file_uses_defaults_without_writing(self):
        self.assertEqual(self.store.load(), (Preferences(), None))
        self.assertFalse(self.path.parent.exists())

    def test_valid_preferences_roundtrip_and_color_normalization(self):
        self.store.load()
        values = Preferences.validate({"theme": "dark", "accent": "#ABCDEF", "timezone_id": "America/New_York"})
        self.store.save(values)
        self.assertEqual(values.accent, "#abcdef")
        self.assertEqual(PreferencesStore(self.path).load(), (values, None))
        self.assertEqual(set(json.loads(self.path.read_text(encoding="utf-8"))), {"version", *Preferences().values()})

    def test_invalid_fields_fall_back_individually_and_keep_file(self):
        content = b'{"version":1,"theme":"dark","accent":"invalid","timezone_id":"UTC"}'
        self.write(content)
        values, warning = self.store.load()
        self.assertEqual(values, Preferences("dark", "#2862c4", "UTC"))
        self.assertIn("accent", warning)
        self.assertEqual(self.path.read_bytes(), content)

    def test_malformed_json_can_be_explicitly_repaired(self):
        content = b'{"theme": '
        self.write(content)
        values, warning = self.store.load()
        self.assertEqual(values, Preferences())
        self.assertIsNotNone(warning)
        self.assertEqual(self.path.read_bytes(), content)
        self.store.save(Preferences())
        self.assertEqual(PreferencesStore(self.path).load(), (Preferences(), None))
        for content in (b"[" * 2000 + b"0" + b"]" * 2000, b"\xff"):
            self.write(content)
            self.assertIsNotNone(self.store.load()[1])
            self.assertEqual(self.path.read_bytes(), content)

    def test_unknown_format_cannot_be_overwritten(self):
        for version in (2, True, None):
            content = json.dumps({"version": version, "theme": "dark"}).encode()
            self.write(content)
            self.assertIsNotNone(self.store.load()[1])
            with self.assertRaises(ValueError):
                self.store.save(Preferences())
            self.assertEqual(self.path.read_bytes(), content)

    def test_invalid_values_and_css_injection_are_rejected(self):
        for changes in ({"theme": "system"}, {"accent": "red; color:white"}, {"accent": "#abcd"}, {"accent": None},
                        {"timezone_id": "Unknown/Place"}, {"timezone_id": 42}, {"language": "fr"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Preferences.validate({**Preferences().values(), **changes})

    def test_builder_autosave_settings_roundtrip_and_legacy_defaults(self):
        self.write(b'{"version":1,"theme":"dark"}')
        defaults, warning = self.store.load()
        self.assertIsNone(warning)
        self.assertTrue(defaults.builder_autosave)
        self.assertEqual(defaults.builder_autosave_seconds, 3)
        changed = Preferences.validate({**defaults.values(), "builder_autosave": False, "builder_autosave_seconds": 60})
        self.store.save(changed)
        self.assertEqual(PreferencesStore(self.path).load(), (changed, None))
        for changes in ({"builder_autosave": 1}, {"builder_autosave_seconds": True}, {"builder_autosave_seconds": 0}, {"builder_autosave_seconds": 61}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Preferences.validate({**defaults.values(), **changes})

    def test_failed_replace_preserves_existing_file_and_cleans_temporary_file(self):
        self.store.load()
        self.store.save(Preferences())
        original = self.path.read_bytes()
        with patch("emailcenter.preferences.os.replace", side_effect=PermissionError("Write denied")):
            with self.assertRaises(PermissionError):
                self.store.save(Preferences(theme="dark"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".preferences-*.tmp")), [])
        self.store.save(Preferences(theme="dark"))
        self.assertEqual(PreferencesStore(self.path).load()[0].theme, "dark")

    def test_changed_file_requires_reload_before_save(self):
        self.store.load()
        other = PreferencesStore(self.path)
        other.load()
        other.save(Preferences(theme="dark"))
        with self.assertRaisesRegex(ValueError, "zwischenzeitlich"):
            self.store.save(Preferences(timezone_id="UTC"))
        self.assertEqual(self.store.load()[0].theme, "dark")
        self.store.save(Preferences("dark", "#2862c4", "UTC"))

    def test_oversized_file_is_not_loaded_or_overwritten(self):
        content = b"x" * 65537
        self.write(content)
        self.assertIsNotNone(self.store.load()[1])
        with self.assertRaises(ValueError):
            self.store.save(Preferences())
        self.assertEqual(self.path.read_bytes(), content)

    def test_legacy_version_one_adds_workflow_defaults(self):
        self.write(b'{"version":1,"theme":"dark","accent":"#2862c4","timezone_id":"UTC"}')
        values, warning = self.store.load()
        self.assertIsNone(warning)
        self.assertEqual(values.export_format, "csv")
        self.assertEqual(values.word_replace_format, "docx")
        self.assertEqual(values.conversion_timeout, 120)
        self.store.save(values)
        self.assertEqual(PreferencesStore(self.path).load(), (values, None))

    def test_workflow_preferences_roundtrip(self):
        self.store.load()
        values = Preferences.validate({**Preferences().values(), "export_format": "xlsx", "csv_encoding": "utf-16", "csv_delimiter": "\t",
            "export_directory": str(self.path.parent), "word_replace_whole_words": True, "word_replace_case_sensitive": False,
            "word_replace_missing": "keep", "word_replace_directory": str(self.path.parent), "libreoffice_path": str(self.path.parent / "soffice.exe"), "conversion_timeout": 60})
        self.store.save(values)
        self.assertEqual(PreferencesStore(self.path).load(), (values, None))

    def test_invalid_workflow_values_are_rejected(self):
        for changes in ({"export_format": "html"}, {"csv_encoding": "ascii"}, {"csv_delimiter": "xx"}, {"export_directory": "relative"},
                        {"word_replace_directory": "\x00"}, {"libreoffice_path": "relative.exe"}, {"word_replace_case_sensitive": 1},
                        {"word_replace_whole_words": "yes"}, {"word_replace_missing": "ignore"}, {"word_replace_format": "txt"},
                        {"conversion_timeout": True}, {"conversion_timeout": 601}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Preferences.validate({**Preferences().values(), **changes})

    def test_invalid_workflow_field_falls_back_without_losing_valid_fields(self):
        self.write(json.dumps({"version": 1, **Preferences().values(), "export_format": "xlsx", "word_replace_missing": "wrong"}).encode())
        values, warning = self.store.load()
        self.assertEqual(values.export_format, "xlsx")
        self.assertEqual(values.word_replace_missing, "error")
        self.assertIn("word_replace_missing", warning)
