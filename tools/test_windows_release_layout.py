"""Packaging regression checks; no GUI, credentials or network."""
from pathlib import Path
import tempfile
import unittest
from windows_release_layout import REQUIRED, validate_bundle, retire_intermediate_executable


class ReleaseLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'dist/runtime/EmailCenter'
        for name in REQUIRED:
            file = self.bundle / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'release-file')

    def test_complete_bundle(self):
        self.assertEqual(validate_bundle(self.bundle), self.bundle.resolve())

    def test_missing_or_empty_dependency_rejected(self):
        for name in REQUIRED:
            with self.subTest(name=name):
                file = self.bundle / name
                file.unlink()
                with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                    validate_bundle(self.bundle)
                file.touch()
                with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                    validate_bundle(self.bundle)
                file.write_bytes(b'release-file')

    def test_incompatible_icu_rejected(self):
        (self.bundle / '_internal/icuuc.dll').write_bytes(b'incompatible')
        with self.assertRaisesRegex(RuntimeError, 'ICU'):
            validate_bundle(self.bundle)

    def test_only_matching_intermediate_removed(self):
        build = self.root / 'build/pyinstaller/EmailCenter'
        build.mkdir(parents=True)
        intermediate = build / 'EmailCenter.exe'
        intermediate.write_bytes(b'other-build')
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            retire_intermediate_executable(self.root)
        self.assertTrue(intermediate.exists())
        intermediate.write_bytes((self.bundle / 'EmailCenter.exe').read_bytes())
        retire_intermediate_executable(self.root)
        self.assertFalse(intermediate.exists())
        self.assertTrue((self.bundle / 'EmailCenter.exe').is_file())
        self.assertTrue((build / 'NICHT_HIER_STARTEN.txt').is_file())
        retire_intermediate_executable(self.root)

    def test_incomplete_bundle_preserves_intermediate(self):
        build = self.root / 'build/pyinstaller/EmailCenter'
        build.mkdir(parents=True)
        intermediate = build / 'EmailCenter.exe'
        intermediate.write_bytes(b'release-file')
        (self.bundle / '_internal/python313.dll').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            retire_intermediate_executable(self.root)
        self.assertTrue(intermediate.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
