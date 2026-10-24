"""Tests for local EmailCenter project lifecycle and file safety."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.database import CompanyRepository, connect  # noqa: E402
from emailcenter.project import ProjectError, create_project, open_project  # noqa: E402


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.project_path = Path(self.temporary_directory.name) / "Applicant Project"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_create_close_and_reopen_project(self):
        project = create_project(self.project_path, name="Bewerbungen 2026")
        project_id = project.project_id
        self.assertEqual(project.name, "Bewerbungen 2026")
        self.assertTrue(project.database_path.is_file())
        self.assertTrue((self.project_path / "documents").is_dir())
        CompanyRepository(project.connection).create("Persisted GmbH")
        project.close()
        self.assertTrue(project.is_closed)

        reopened = open_project(self.project_path)
        try:
            self.assertEqual(reopened.project_id, project_id)
            self.assertEqual(
                CompanyRepository(reopened.connection).list()[0]["name"], "Persisted GmbH"
            )
        finally:
            reopened.close()

    def test_project_context_manager_closes_connection(self):
        with create_project(self.project_path) as project:
            self.assertFalse(project.is_closed)
        self.assertTrue(project.is_closed)

    def test_initial_profile_and_signature_persist_on_reopen(self):
        project = create_project(self.project_path, initial_profile={
            "display_name": " Ada ", "email": "ada@example.test", "phone": " 030 123 "},
            initial_signature={"name": " Privat ", "content_text": "Viele Grüße\nAda"})
        project.close()
        with open_project(self.project_path) as reopened:
            profile = reopened.connection.execute("SELECT * FROM applicant_profiles").fetchone()
            signature = reopened.connection.execute("SELECT * FROM email_signatures").fetchone()
            self.assertEqual((profile["display_name"], profile["email"], profile["phone"]),
                             ("Ada", "ada@example.test", "030 123"))
            self.assertEqual((signature["name"], signature["content_text"], signature["is_default"]),
                             ("Privat", "Viele Grüße\nAda", 1))

    def test_invalid_initial_records_create_no_files(self):
        for values in (
            {"initial_profile": {"display_name": "Ada", "email": "invalid"}},
            {"initial_profile": {"display_name": ""}},
            {"initial_profile": {"display_name": "Ada", "phone": 123}},
            {"initial_profile": {"display_name": "Ada", "unknown": "value"}},
            {"initial_signature": {"name": "Privat", "content_text": ""}},
            {"initial_signature": {"name": "Injected\r\nHeader", "content_text": "Text"}},
            {"initial_signature": {"name": "Privat", "content_text": "x" * 100001}},
        ):
            with self.subTest(values=list(values)):
                with self.assertRaises(ProjectError):
                    create_project(self.project_path, **values)
                self.assertEqual(list(self.project_path.parent.iterdir()), [])

    def test_initial_record_failure_cleans_staging_without_publishing_project(self):
        from emailcenter.database import apply_migrations
        def reject_signature(connection, migrations):
            apply_migrations(connection, migrations)
            connection.execute("CREATE TRIGGER reject_setup BEFORE INSERT ON email_signatures "
                               "BEGIN SELECT RAISE(ABORT, 'setup failed'); END")
        with patch("emailcenter.project.apply_migrations", side_effect=reject_signature):
            with self.assertRaisesRegex(ProjectError, "setup failed"):
                create_project(self.project_path, initial_profile={"display_name": "Ada"},
                               initial_signature={"name": "Privat", "content_text": "Grüße"})
        self.assertEqual(list(self.project_path.parent.iterdir()), [])

    def test_project_paths_cannot_escape_project_root(self):
        project = create_project(self.project_path)
        try:
            with self.assertRaises(ProjectError):
                project.file_path("../outside.txt")
            with self.assertRaises(ProjectError):
                project.file_path(self.project_path / "absolute.txt")
            nested_path = project.file_path("documents/generated/result.docx", create_parent=True)
            self.assertTrue(nested_path.parent.is_dir())
            self.assertTrue(nested_path.is_relative_to(self.project_path))
        finally:
            project.close()

    def test_existing_project_is_not_overwritten(self):
        project = create_project(self.project_path)
        project.close()
        with self.assertRaisesRegex(ProjectError, "already exists"):
            create_project(self.project_path)

    def test_open_detects_missing_project_parts_and_corrupt_database(self):
        project = create_project(self.project_path)
        project.close()
        (self.project_path / "templates").rmdir()
        with self.assertRaisesRegex(ProjectError, "missing folders"):
            open_project(self.project_path)

        (self.project_path / "templates").mkdir()
        self.project_path.joinpath("emailcenter.sqlite3").write_bytes(b"not a sqlite database")
        with self.assertRaises(ProjectError):
            open_project(self.project_path)

    def test_project_backup_is_verified_and_recorded(self):
        project = create_project(self.project_path)
        try:
            CompanyRepository(project.connection).create("Backup GmbH")
            project.file_path("documents/cover-letter.docx", create_parent=True).write_bytes(
                b"sample document bytes"
            )
            backup_path = project.create_backup()
            self.assertTrue(backup_path.is_file())
            row = project.connection.execute(
                "SELECT file_path, file_size_bytes, file_hash, status, verified_at "
                "FROM backup_metadata"
            ).fetchone()
            self.assertEqual(row[0], str(backup_path.relative_to(self.project_path)))
            self.assertGreater(row[1], 0)
            self.assertEqual(len(row[2]), 64)
            self.assertEqual(row[3], "Verified")
            self.assertTrue(row[4].endswith("Z"))

            with zipfile.ZipFile(backup_path, "r") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(
                    archive.read("documents/cover-letter.docx"), b"sample document bytes"
                )
                staged_database = Path(self.temporary_directory.name) / "backup-check.sqlite3"
                staged_database.write_bytes(archive.read("emailcenter.sqlite3"))
            backup = connect(staged_database)
            try:
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(
                    backup.execute("SELECT name FROM companies").fetchone()[0], "Backup GmbH"
                )
            finally:
                backup.close()
        finally:
            project.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
