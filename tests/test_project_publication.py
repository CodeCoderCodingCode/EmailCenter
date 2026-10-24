"""Bounded Windows rename retries preserve unrelated projects and errors."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from emailcenter.project import ProjectError, create_project

ROOT = Path(__file__).resolve().parents[1]


def windows_lock(code=5):
    error = PermissionError('temporary Windows lock')
    error.winerror = code
    return error


class ProjectPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'project'

    def tearDown(self):
        self.temporary.cleanup()

    def test_transient_windows_errors_retry_then_open_valid_project(self):
        original = Path.rename
        for code in (5, 32):
            with self.subTest(winerror=code):
                target = self.root / f'project-{code}'
                attempts = []
                def transient(source, destination):
                    attempts.append(source)
                    if len(attempts) < 4:
                        raise windows_lock(code)
                    return original(source, destination)
                with patch.object(Path, 'rename', transient), patch('emailcenter.project.time.sleep') as sleep:
                    project = create_project(target)
                try:
                    self.assertEqual(len(attempts), 4)
                    self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.05, 0.1, 0.2])
                    self.assertEqual(project.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                    self.assertEqual(project.connection.execute("SELECT value FROM project_metadata WHERE key='schema_version'").fetchone()[0], '14')
                finally:
                    project.close()

    def test_permanent_windows_error_stops_after_five_attempts(self):
        error = windows_lock()
        with patch.object(Path, 'rename', side_effect=error) as rename, patch('emailcenter.project.time.sleep') as sleep:
            with self.assertRaises(ProjectError) as raised:
                create_project(self.target)
        self.assertIs(raised.exception.__cause__, error)
        self.assertEqual(rename.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.project.creating-*')))

    def test_other_permission_errors_are_not_retried(self):
        error = PermissionError('persistent non-Windows error')
        with patch.object(Path, 'rename', side_effect=error) as rename, patch('emailcenter.project.time.sleep') as sleep:
            with self.assertRaises(ProjectError) as raised:
                create_project(self.target)
        self.assertIs(raised.exception.__cause__, error)
        self.assertEqual(rename.call_count, 1)
        sleep.assert_not_called()
        self.assertFalse(list(self.root.glob('.project.creating-*')))

    def test_destination_created_during_retry_is_preserved(self):
        def another_project(source, destination):
            destination.mkdir()
            (destination / 'keep.txt').write_text('Existing project', encoding='utf-8')
            raise windows_lock()
        with patch.object(Path, 'rename', autospec=True, side_effect=another_project) as rename, patch('emailcenter.project.time.sleep') as sleep:
            with self.assertRaises(ProjectError):
                create_project(self.target)
        self.assertEqual(rename.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual((self.target / 'keep.txt').read_text(encoding='utf-8'), 'Existing project')
        self.assertFalse(list(self.root.glob('.project.creating-*')))
