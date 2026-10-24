"""Release settings, durable undo and safe backup restoration; no live provider."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import test_builder_workspace as builder_fixture
import test_bulk_delivery as bulk_fixture
from emailcenter.application.workspace import WorkspaceService
from emailcenter.backups import inspect_backup, restore_backup, prune_backups, INDEX
from emailcenter.builder_workspace import BuilderWorkspaceService, validate_state
from emailcenter.email_builder import starter_graph, validate_graph
from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.project import create_project, open_project, ProjectError


class EndspurtPreferencesTests(unittest.TestCase):
    def test_all_defaults_roundtrip_and_legacy_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"version": 1, "theme": "dark", "accent": "#2862c4", "timezone_id": "UTC"}), encoding="utf-8")
            store = PreferencesStore(path)
            defaults, warning = store.load()
            self.assertIsNone(warning)
            values = {**defaults.values(), "language": "en", "workspace_mode": "mail", "start_page": "builder",
                      "mail_account_email": "test@example.test", "mail_signature_name": "Privat", "mail_body_format": "html",
                      "mail_timezone_id": "UTC", "mail_delivery_mode": "scheduled", "mail_interval_seconds": 7,
                      "mail_daily_budget": 2, "mail_window_start": "22:00", "mail_window_end": "07:00",
                      "list_page_size": 100, "list_word_wrap": False, "list_compact_rows": True,
                      "backup_directory": temporary, "backup_retention": 3, "builder_default_blocks": ["greeting", "description", "closing"]}
            expected = Preferences.validate(values)
            store.save(expected)
            self.assertEqual(PreferencesStore(path).load(), (expected, None))

    def test_invalid_new_fields_are_rejected(self):
        for changes in ({"language": "fr"}, {"start_page": "mail_send"}, {"workspace_mode": "other"},
                        {"mail_account_email": "not an address"}, {"mail_signature_name": "a\nb"},
                        {"mail_timezone_id": "Mars/Test"}, {"mail_daily_budget": True}, {"mail_interval_seconds": 0},
                        {"mail_window_start": "9:00"}, {"list_page_size": 201}, {"list_word_wrap": 1},
                        {"backup_retention": -1}, {"backup_directory": "relative"}, {"builder_default_blocks": []},
                        {"builder_default_blocks": ["email"]}, {"builder_default_blocks": ["text", "text"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Preferences.validate({**Preferences().values(), **changes})

    def test_invalid_loaded_fields_fall_back_without_discarding_other_preferences(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temporary:
            path = Path(temporary) / "preferences.json"
            path.write_text(json.dumps({"version": 1, **Preferences().values(), "language": "en", "backup_retention": -1}), encoding="utf-8")
            preferences, warning = PreferencesStore(path).load()
            self.assertEqual(preferences.language, "en")
            self.assertEqual(preferences.backup_retention, 0)
            self.assertIn("backup_retention", warning)

    def test_default_blocks_form_a_connected_editable_graph(self):
        for blocks in (["text"], ["greeting", "description", "closing"], ["heading", "html", "separator", "list"]):
            graph = starter_graph(blocks)
            validate_graph(graph, editable=True)
            self.assertEqual([n["kind"] for n in graph["nodes"]], ["data", "subject", *blocks, "email"])
            self.assertEqual(len(graph["edges"]), 3 + 2 * len(blocks))


class DurableUndoTests(unittest.TestCase):
    setUp = builder_fixture.WorkspaceCheckpointTests.setUp
    tearDown = builder_fixture.WorkspaceCheckpointTests.tearDown
    state = builder_fixture.WorkspaceCheckpointTests.state

    def test_undo_and_redo_survive_reopen(self):
        state = {**self.state(), "history": [deepcopy(self.graph)], "future": [deepcopy(self.graph)]}
        state["history"][0]["nodes"][1]["config"]["text"] = "Vorher"
        service = BuilderWorkspaceService(self.project)
        service.save(self.project.project_id, state, 0)
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        self.assertEqual(BuilderWorkspaceService(self.workspace.project).load()["state"], state)

    def test_bad_history_rejected_before_replacing_checkpoint(self):
        service = BuilderWorkspaceService(self.project)
        service.save(self.project.project_id, self.state(), 0)
        for history in (None, [self.graph] * 101, [{"nodes": [], "edges": []}], ["invalid"]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                service.save(self.project.project_id, {**self.state(), "history": history}, 1)
        self.assertEqual(service.load()["revision"], 1)


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temporary.name)
        self.project = create_project(self.root / "original", name="Backup-Test")
        self.project.file_path("documents/example.txt", create_parent=True).write_text("Unverändertes Dokument", encoding="utf-8")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def archive_with(self, members):
        path = self.root / "malicious.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for key, content in members.items():
                archive.writestr(key, content)
        return path

    def restore(self, path, **options):
        return restore_backup(path, self.root / "restored", inspect_backup(path)["hash"], **options)

    def test_index_hashes_and_atomic_roundtrip(self):
        archive = self.project.create_backup()
        review = inspect_backup(archive)
        self.assertTrue(review["verified_index"])
        result = self.restore(archive)
        with open_project(result) as restored:
            self.assertEqual(restored.project_id, self.project.project_id)
            self.assertEqual(restored.file_path("documents/example.txt").read_text(encoding="utf-8"), "Unverändertes Dokument")
            self.assertEqual(restored.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertTrue(self.project.file_path("documents/example.txt").is_file())
        self.assertFalse(list(self.root.glob(".emailcenter-restore-*")))

    def test_legacy_archive_remains_supported_with_warning_flag(self):
        archive = self.project.create_backup()
        with zipfile.ZipFile(archive) as source:
            legacy = self.archive_with({name: source.read(name) for name in source.namelist() if name != INDEX})
        self.assertFalse(inspect_backup(legacy)["verified_index"])
        self.assertTrue(Path(self.restore(legacy)).is_dir())

    def test_changed_archive_after_review_is_rejected(self):
        archive = self.project.create_backup()
        review = inspect_backup(archive)
        with zipfile.ZipFile(archive, "a") as stream:
            stream.comment = b"Changed"
        with self.assertRaisesRegex(ProjectError, "Vorschau"):
            restore_backup(archive, self.root / "restored", review["hash"])
        self.assertFalse((self.root / "restored").exists())

    def test_hash_mismatch_preserves_original_and_publishes_nothing(self):
        archive = self.project.create_backup()
        with zipfile.ZipFile(archive) as source:
            values = {name: source.read(name) for name in source.namelist()}
        values["documents/example.txt"] = b"Tampered"
        index = json.loads(values[INDEX])
        index["files"]["documents/example.txt"]["size"] = len(values["documents/example.txt"])
        values[INDEX] = json.dumps(index).encode()
        bad = self.archive_with(values)
        with self.assertRaisesRegex(ProjectError, "Hash"):
            self.restore(bad)
        self.assertFalse((self.root / "restored").exists())
        self.assertFalse(list(self.root.glob(".emailcenter-restore-*")))

    def test_path_traversal_windows_names_links_duplicates_and_unknown_content_blocked(self):
        for name in ("../outside", "/absolute", "documents/../../outside", "documents\\evil", "documents/C:evil", "documents/CON.txt", "documents/trailing. ", "credentials.json"):
            with self.subTest(name=name), self.assertRaises(ProjectError):
                inspect_backup(self.archive_with({name: b"bad"}))
        path = self.root / "link.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("documents/link")
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, b"../../outside")
        with self.assertRaises(ProjectError):
            inspect_backup(path)
        with self.assertRaises(ProjectError):
            inspect_backup(self.archive_with({"documents/Test": b"1", "documents/test": b"2"}))

    def test_existing_destination_and_cancellation_are_safe(self):
        archive = self.project.create_backup()
        destination = self.root / "restored"
        destination.mkdir()
        (destination / "keep.txt").write_text("Keep", encoding="utf-8")
        with self.assertRaises(ProjectError):
            self.restore(archive)
        self.assertEqual((destination / "keep.txt").read_text(encoding="utf-8"), "Keep")
        with self.assertRaisesRegex(ProjectError, "abgebrochen"):
            restore_backup(archive, self.root / "cancelled", inspect_backup(archive)["hash"], cancelled=lambda: True)
        self.assertFalse((self.root / "cancelled").exists())

    def test_external_target_is_separate_and_content_directory_is_rejected(self):
        path = self.project.create_backup(self.root / "external")
        self.assertTrue(path.is_relative_to(self.root / "external"))
        row = self.project.connection.execute("SELECT file_path FROM backup_metadata ORDER BY rowid DESC").fetchone()
        self.assertEqual(row["file_path"], str(path))
        with self.assertRaises(ProjectError):
            self.project.create_backup(self.project.path / "documents")

    def test_retention_keeps_changed_unmanaged_and_other_project_archives(self):
        paths = [self.project.create_backup() for _ in range(3)]
        changed = paths[0]
        with zipfile.ZipFile(changed, "a") as archive:
            archive.comment = b"Keep changed archive"
        unknown = paths[0].parent / "unmanaged.zip"
        unknown.write_bytes(paths[1].read_bytes())
        prune_backups(self.project, paths[-1].parent, 1)
        self.assertTrue(changed.exists())
        self.assertFalse(paths[1].exists())
        self.assertTrue(paths[2].exists())
        self.assertTrue(unknown.exists())
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM backup_metadata WHERE status='Deleted'").fetchone()[0], 1)

    def test_incomplete_word_runs_cannot_write_to_the_old_project(self):
        db = self.project.connection
        db.execute("INSERT INTO word_replace_runs(id,name,source_path,source_hash,configuration_json,status,created_at,updated_at) VALUES('run','Old','exports/input.docx','hash','{}','Running','2026','2026')")
        restored_path = self.restore(self.project.create_backup())
        from emailcenter.word_replace_runs import WordReplaceRuns
        with open_project(restored_path) as restored:
            run = WordReplaceRuns(restored).snapshot("run")
            self.assertEqual(run["status"], "Paused")
            with self.assertRaisesRegex(ValueError, "Sicherung"):
                WordReplaceRuns(restored)._claim("run")


class RestoreDeliveryTests(unittest.TestCase):
    setUp = bulk_fixture.BulkDeliveryTests.setUp
    tearDown = bulk_fixture.BulkDeliveryTests.tearDown
    make_service = bulk_fixture.BulkDeliveryTests.make_service
    begin = bulk_fixture.BulkDeliveryTests.begin
    ready = bulk_fixture.BulkDeliveryTests.ready
    approved = bulk_fixture.BulkDeliveryTests.approved
    running = bulk_fixture.BulkDeliveryTests.running

    def test_diagnostics_contains_only_allowlisted_statuses_and_versions(self):
        from emailcenter.diagnostics import diagnostic_report
        report = diagnostic_report(self.workspace.project)
        serialized = json.dumps(report)
        self.assertTrue(report["project"]["database_integrity_ok"])
        for private in (self.account["account_email"], str(self.root), "refresh_token", "Feste Datei", "Anhang.txt", "Ada", "Grace"):
            self.assertNotIn(private, serialized)
        self.assertEqual(report["project"]["enabled_gmail_accounts"], 1)

    def test_local_diagnostic_export_and_report_without_project(self):
        path = self.workspace.diagnostic_export(str(self.root))
        self.assertTrue(Path(path).is_file())
        self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["format_version"], 1)
        self.workspace.close()
        path = self.workspace.diagnostic_export(str(self.root))
        self.assertIsNone(json.loads(Path(path).read_text(encoding="utf-8"))["project"])
        with self.assertRaises(ValueError):
            self.workspace.diagnostic_export("relative")

    def test_restore_deactivates_accounts_revokes_approvals_and_pauses_background(self):
        value = self.running()
        self.db.execute("UPDATE email_bulk_dispatches SET background=1 WHERE id=?", (value["id"],))
        archive = self.workspace.project.create_backup()
        destination = restore_backup(archive, self.root / "restored", inspect_backup(archive)["hash"])
        with open_project(destination) as restored:
            self.assertEqual(restored.connection.execute("SELECT is_enabled FROM email_provider_accounts").fetchone()[0], 0)
            group = restored.connection.execute("SELECT status,background FROM email_bulk_dispatches").fetchone()
            self.assertEqual(tuple(group), ("Paused", 0))
            for row in restored.connection.execute("SELECT approval_status,requires_overdue_confirmation FROM email_jobs"):
                self.assertEqual(tuple(row), ("pending", 1))
        self.assertEqual(self.service.snapshot(value["id"])["status"], "Running")
        self.assertEqual(self.provider.sent, [])

    def test_interrupted_send_becomes_uncertain_not_queued(self):
        value = self.running()
        self.db.execute("UPDATE email_jobs SET status='Sending' WHERE id=?", (value["items"][0]["job"]["id"],))
        archive = self.workspace.project.create_backup()
        destination = restore_backup(archive, self.root / "restored", inspect_backup(archive)["hash"])
        with open_project(destination) as restored:
            self.assertIn("Uncertain", [row[0] for row in restored.connection.execute("SELECT status FROM email_jobs")])

    def test_incomplete_preparation_remains_resumable_without_background_permission(self):
        value = self.begin()
        archive = self.workspace.project.create_backup()
        destination = restore_backup(archive, self.root / "restored", inspect_backup(archive)["hash"])
        with open_project(destination) as restored:
            row = restored.connection.execute("SELECT status,background FROM email_bulk_dispatches").fetchone()
            self.assertEqual(tuple(row), ("Preparing", 0))


if __name__ == "__main__":
    unittest.main()
