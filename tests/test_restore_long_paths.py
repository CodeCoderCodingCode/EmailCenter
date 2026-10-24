"""Real Windows staging paths can exceed MAX_PATH while final paths fit."""
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from emailcenter.project import create_project, open_project, ProjectError
from emailcenter.backups import inspect_backup, restore_backup, _filesystem_path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows extended filesystem paths')
class LongRestorePaths(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name)
        self.project = create_project(self.root / 'original')
        prefix = Path('exports/mail/drafts') / str(uuid4()) / str(uuid4()) / '00'
        length = 247 - len(str(self.project.path / prefix)) - len('\\.pdf')
        self.assertGreater(length, 0)
        self.relative = prefix / ('a' * length + '.pdf')
        self.source = self.project.file_path(self.relative, create_parent=True)
        self.source.write_bytes(b'%PDF synthetic long path content')
        self.assertEqual(len(str(self.source)), 247)
        self.archive = self.project.create_backup()
        self.review = inspect_backup(self.archive)

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_long_staging_path_restores_content_and_leaves_no_temporary_tree(self):
        destination = self.root / 'r'
        anticipated = self.root / '.emailcenter-restore-12345678' / self.relative
        self.assertGreaterEqual(len(str(anticipated)), 260)
        restore_backup(self.archive, destination, self.review['hash'])
        with open_project(destination) as restored:
            self.assertEqual(restored.file_path(self.relative).read_bytes(), self.source.read_bytes())
        self.assertFalse(list(self.root.glob('.emailcenter-restore-*')))
        self.assertTrue(self.source.is_file())

    def test_cancel_after_opening_long_file_removes_staging_and_preserves_original(self):
        observed = []
        def cancelled():
            for staging in self.root.glob('.emailcenter-restore-*'):
                target = staging / self.relative
                if _filesystem_path(target).is_file():
                    observed.append(len(str(target)))
                    return True
            return False
        destination = self.root / 'r'
        with self.assertRaisesRegex(ProjectError, 'abgebrochen'):
            restore_backup(self.archive, destination, self.review['hash'], cancelled=cancelled)
        self.assertTrue(observed)
        self.assertGreaterEqual(min(observed), 260)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob('.emailcenter-restore-*')))
        self.assertEqual(self.source.read_bytes(), b'%PDF synthetic long path content')


if __name__ == '__main__':
    unittest.main()
