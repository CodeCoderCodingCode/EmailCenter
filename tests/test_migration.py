"""Tests for EmailCenter's SQLite connection factory and migration runner."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.database import (  # noqa: E402
    CompanyRepository,
    ContactRepository,
    MigrationError,
    apply_migrations,
    connect,
    discover_migrations,
)

MIGRATIONS = ROOT / "migrations"


class ConnectionTests(unittest.TestCase):
    def test_foreign_keys_are_enabled_for_every_connection(self):
        first = connect(":memory:")
        second = connect(":memory:")
        try:
            self.assertEqual(first.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(second.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        finally:
            first.close()
            second.close()

    def test_parent_directory_is_created_for_file_database(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            database_path = Path(temporary_directory) / "new" / "project.sqlite"
            connection = connect(database_path)
            try:
                self.assertTrue(database_path.parent.is_dir())
                self.assertTrue(database_path.is_file())
            finally:
                connection.close()

    def test_invalid_timeout_is_rejected(self):
        with self.assertRaises(ValueError):
            connect(":memory:", timeout=-1)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.applied = apply_migrations(self.db, MIGRATIONS)

    def tearDown(self):
        self.db.close()

    def test_builder_reuse_migration_preserves_populated_schema_thirteen(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            for migration in discover_migrations(MIGRATIONS):
                if migration.version <= 13:
                    shutil.copyfile(migration.path, directory / migration.path.name)
            connection = connect(':memory:')
            try:
                apply_migrations(connection, directory)
                connection.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at) VALUES('t','Old','email','now','now')")
                connection.execute("INSERT INTO template_versions(id,template_id,version_number,created_at) VALUES('v','t',1,'now')")
                connection.execute("INSERT INTO email_drafts(id,subject,created_at,updated_at) VALUES('d','Keep me','now','now')")
                connection.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES('b','Old','v','now')")
                connection.execute("INSERT INTO email_draft_batch_items(batch_id,item_key,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json) VALUES('b','old:key','d','old@example.test','Old','{\"preserved\":true}')")
                old = dict(connection.execute('SELECT * FROM email_draft_batch_items').fetchone())
                connection.commit()
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [14])
                current = dict(connection.execute('SELECT * FROM email_draft_batch_items').fetchone())
                self.assertEqual(current.pop('recipient_reuse_allowed'), 0)
                self.assertEqual(current, old)
                self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(connection.execute("SELECT subject FROM email_drafts WHERE id='d'").fetchone()[0], 'Keep me')
            finally:
                connection.close()

    def test_initial_migration_is_applied_and_recorded(self):
        self.assertEqual(self.applied, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
        row = self.db.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 1"
        ).fetchone()
        self.assertEqual(tuple(row), (1, "initial_project_schema"))
        row = self.db.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 2"
        ).fetchone()
        self.assertEqual(tuple(row), (2, "seed_application_statuses"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=3").fetchone()
        self.assertEqual(tuple(row), (3, "import_run_snapshots"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=4").fetchone()
        self.assertEqual(tuple(row), (4, "email_delivery_snapshots"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=5").fetchone()
        self.assertEqual(tuple(row), (5, "email_draft_batches"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=6").fetchone()
        self.assertEqual(tuple(row), (6, "bulk_data_sources"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=7").fetchone()
        self.assertEqual(tuple(row), (7, "bulk_delivery"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=8").fetchone()
        self.assertEqual(tuple(row), (8, "source_library"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=9").fetchone()
        self.assertEqual(tuple(row), (9, "email_builder"))
        row = self.db.execute("SELECT version,name FROM schema_migrations WHERE version=10").fetchone()
        self.assertEqual(tuple(row), (10, "builder_workspace"))

    def test_source_library_migration_preserves_existing_project_data(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            for migration in sorted(MIGRATIONS.glob("00[1-7]_*.sql")):
                shutil.copyfile(migration, Path(folder) / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, folder)
                contact = ContactRepository(connection).create("Ada", email="ada@example.test")
                connection.commit()
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [8, 9, 10, 11, 12, 13, 14])
                self.assertEqual(connection.execute("SELECT email FROM contacts WHERE id=?", (contact["id"],)).fetchone()[0], "ada@example.test")
                for table in ("data_source_profiles", "data_source_lists", "data_source_list_rows"):
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_completion_upgrade_from_eleven_preserves_records(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            for migration in MIGRATIONS.glob('*.sql'):
                if int(migration.name.split('_')[0])<=11:
                    shutil.copyfile(migration,Path(folder)/migration.name)
            db=connect(':memory:')
            try:
                apply_migrations(db,folder);contact=ContactRepository(db).create('Legacy',email='legacy@example.test')
                db.execute('UPDATE contacts SET custom_fields_json=? WHERE id=?',('{"keep":true}',contact['id']))
                self.assertEqual(apply_migrations(db,MIGRATIONS),[12,13,14])
                row=db.execute('SELECT * FROM contacts WHERE id=?',(contact['id'],)).fetchone()
                self.assertEqual(row['email'],'legacy@example.test');self.assertEqual(row['custom_fields_json'],'{"keep":true}');self.assertEqual(row['address_json'],'{}')
                for table in ('record_archive','export_history','builder_groups','file_cleanup'):
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:db.close()

    def test_builder_upgrade_from_eight_preserves_lists_and_drafts(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            for migration in sorted(MIGRATIONS.glob("00[1-8]_*.sql")):
                shutil.copyfile(migration, Path(folder) / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, folder)
                connection.execute("INSERT INTO data_source_lists(id,name,created_at,updated_at) VALUES('list','Daten','now','now')")
                connection.execute("INSERT INTO email_drafts(id,subject,body,body_format,recipients_json,configuration_json,created_at,updated_at) VALUES('draft','Betreff','Text','plain','{}','{}','now','now')")
                connection.commit()
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [9, 10, 11, 12, 13, 14])
                self.assertEqual(connection.execute("SELECT name FROM data_source_lists WHERE id='list'").fetchone()[0], "Daten")
                self.assertEqual(connection.execute("SELECT subject FROM email_drafts WHERE id='draft'").fetchone()[0], "Betreff")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM email_builders").fetchone()[0], 0)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_workspace_upgrade_from_nine_preserves_builder_versions_and_drafts(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            for migration in sorted(MIGRATIONS.glob("00[1-9]_*.sql")):
                shutil.copyfile(migration, Path(folder) / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, folder)
                connection.execute("INSERT INTO email_builders VALUES('builder','Mein Ablauf','now','now')")
                connection.execute("INSERT INTO email_builder_versions VALUES('version','builder',1,'{}','hash','now')")
                connection.execute("INSERT INTO email_drafts(id,subject,body,body_format,recipients_json,configuration_json,created_at,updated_at) VALUES('draft','Betreff','Text','plain','{}','{}','now','now')")
                connection.commit()
                before = tuple(connection.execute("SELECT * FROM email_builder_versions").fetchone())
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [10, 11, 12, 13, 14])
                self.assertEqual(tuple(connection.execute("SELECT * FROM email_builder_versions").fetchone()), before)
                self.assertEqual(connection.execute("SELECT subject FROM email_drafts").fetchone()[0], "Betreff")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM email_builder_workspace").fetchone()[0], 0)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_import_snapshot_migration_preserves_existing_runs(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            for name in ("001_initial_project_schema.sql", "002_seed_application_statuses.sql"):
                shutil.copyfile(MIGRATIONS / name, directory / name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, directory)
                connection.execute("INSERT INTO import_runs(id,source_filename,status,created_at) VALUES('legacy','old.csv','Pending','now')")
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
                row = connection.execute("SELECT * FROM import_runs WHERE id='legacy'").fetchone()
                self.assertEqual(row["source_filename"], "old.csv")
                self.assertEqual(row["configuration_json"], "{}")
                self.assertIsNone(row["source_file_hash"])
            finally:
                connection.close()

    def test_schema_version_tracks_latest_migration(self):
        row = self.db.execute(
            "SELECT value FROM project_metadata WHERE key = 'schema_version'"
        ).fetchone()
        self.assertEqual(row[0], "14")

    def test_email_migration_preserves_legacy_drafts_and_jobs(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            for migration in sorted(MIGRATIONS.glob("00[1-3]_*.sql")):
                shutil.copyfile(migration, directory / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, directory)
                connection.execute("INSERT INTO email_drafts(id,subject,created_at,updated_at) VALUES('draft','Existing','now','now')")
                connection.execute("INSERT INTO email_jobs(id,draft_id,recipients_snapshot_json,subject_snapshot,body_snapshot,body_format,timezone_id,status,idempotency_key,created_at,updated_at) VALUES('job','draft','{}','Existing','body','plain','UTC','Draft','old-key','now','now')")
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
                row = connection.execute("SELECT * FROM email_jobs WHERE id='job'").fetchone()
                self.assertEqual(row["subject_snapshot"], "Existing")
                self.assertIsNone(row["payload_file_path"])
                self.assertEqual(connection.execute("SELECT subject FROM email_drafts WHERE id='draft'").fetchone()[0], "Existing")
            finally:
                connection.close()

    def test_bulk_source_migration_preserves_existing_contact_groups(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            for migration in sorted(MIGRATIONS.glob("00[1-5]_*.sql")):
                shutil.copyfile(migration, directory / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, directory)
                connection.execute("INSERT INTO contacts(id,display_name,created_at,updated_at) VALUES('contact','Old','now','now')")
                connection.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at) VALUES('template','Old','email','now','now')")
                connection.execute("INSERT INTO template_versions(id,template_id,version_number,created_at) VALUES('version','template',1,'now')")
                connection.execute("INSERT INTO email_drafts(id,subject,created_at,updated_at) VALUES('draft','Existing','now','now')")
                connection.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES('batch','Old','version','now')")
                connection.execute("INSERT INTO email_draft_batch_items(batch_id,contact_id,draft_id,recipient_snapshot,name_snapshot) VALUES('batch','contact','draft','old@example.test','Old')")
                connection.commit()
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [6, 7, 8, 9, 10, 11, 12, 13, 14])
                row = connection.execute("SELECT * FROM email_draft_batch_items").fetchone()
                self.assertEqual((row["item_key"], row["contact_id"], row["draft_id"], row["source_snapshot_json"]), ("contact", "contact", "draft", "{}"))
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_bulk_delivery_migration_preserves_existing_source_groups_without_automatic_jobs(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            for migration in sorted(MIGRATIONS.glob("00[1-6]_*.sql")):
                shutil.copyfile(migration, directory / migration.name)
            connection = connect(":memory:")
            try:
                apply_migrations(connection, directory)
                connection.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at) VALUES('template','Old','email','now','now')")
                connection.execute("INSERT INTO template_versions(id,template_id,version_number,created_at) VALUES('version','template',1,'now')")
                connection.execute("INSERT INTO email_drafts(id,subject,created_at,updated_at) VALUES('draft','Existing','now','now')")
                connection.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES('batch','Old','version','now')")
                connection.execute("INSERT INTO email_draft_batch_items(batch_id,item_key,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json) VALUES('batch','manual:key','draft','old@example.test','Old','{\"kind\":\"manual\"}')")
                self.assertEqual(apply_migrations(connection, MIGRATIONS), [7, 8, 9, 10, 11, 12, 13, 14])
                row = connection.execute("SELECT * FROM email_draft_batch_items").fetchone()
                self.assertEqual((row["item_key"], row["contact_id"], row["source_snapshot_json"]), ("manual:key", None, '{"kind":"manual"}'))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM email_bulk_dispatches").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_default_application_statuses_are_seeded(self):
        self.assertEqual(tuple(self.db.execute("SELECT version,name FROM schema_migrations WHERE version=11").fetchone()),(11,"workspace_expansion"))
        rows = self.db.execute(
            "SELECT code, label, is_terminal FROM application_statuses ORDER BY sort_order"
        ).fetchall()
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in rows],
            [
                ("draft", "Entwurf", 0),
                ("preparing", "In Vorbereitung", 0),
                ("sent", "Versendet", 0),
                ("interview", "Gespräch", 0),
                ("offer", "Angebot", 0),
                ("accepted", "Angenommen", 1),
                ("rejected", "Abgelehnt", 1),
                ("withdrawn", "Zurückgezogen", 1),
            ],
        )

    def test_workspace_expansion_migrates_receipts_and_preserves_existing_dispatch(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            old = Path(folder)
            for migration in MIGRATIONS.glob("*.sql"):
                if int(migration.name.split("_")[0]) <= 10:
                    shutil.copyfile(migration,old / migration.name)
            db = connect(":memory:")
            try:
                apply_migrations(db,old)
                db.execute("INSERT INTO applications(id,status_id,title,created_at,updated_at) SELECT 'app',id,'Alt','now','now' FROM application_statuses WHERE code='draft'")
                db.execute("INSERT INTO email_provider_accounts(id,provider,account_email,created_at,updated_at) VALUES('account','gmail','sender@example.test','now','now')")
                db.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at) VALUES('template','Alt','email','now','now')")
                db.execute("INSERT INTO template_versions(id,template_id,version_number,created_at) VALUES('version','template',1,'now')")
                db.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES('batch','Alt','version','now')")
                db.execute("INSERT INTO email_jobs(id,application_id,provider_account_id,recipients_snapshot_json,subject_snapshot,body_snapshot,body_format,timezone_id,status,approval_status,idempotency_key,created_at,updated_at) VALUES('job','app','account','{}','Betreff','Text','plain','UTC','Queued','approved','key','now','now')")
                db.execute("INSERT INTO email_bulk_dispatches(id,batch_id,provider_account_id,timezone_id,interval_seconds,status,created_at,updated_at) VALUES('group','batch','account','UTC',5,'Running','now','now')")
                self.assertEqual(apply_migrations(db,MIGRATIONS),[11, 12, 13, 14])
                self.assertEqual(tuple(db.execute("SELECT status,approval_status,subject_snapshot FROM email_jobs").fetchone()),('Queued','approved','Betreff'))
                self.assertEqual(tuple(db.execute("SELECT status,daily_budget,window_start,window_end,background FROM email_bulk_dispatches").fetchone()),('Running',100,'00:00','00:00',0))
                self.assertEqual(tuple(db.execute("SELECT application_id,job_id,status FROM application_mail_receipts").fetchone()),('app','job','Queued'))
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(),[])
            finally:
                db.close()

    def test_required_tables_exist(self):
        required = {
            "companies", "contacts", "company_contacts", "job_postings", "applications",
            "documents", "templates", "template_versions", "email_drafts", "email_jobs",
            "email_attempts", "email_attachments", "import_runs", "workflow_runs",
            "reminders", "activity_log",
            "email_draft_batches", "email_draft_batch_items",
        }
        existing = {
            row[0]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertTrue(required.issubset(existing), f"Missing: {required - existing}")

    def test_foreign_key_targets_exist_and_initial_integrity_is_clean(self):
        tables = self.db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        missing_targets = []
        for (table,) in tables:
            for foreign_key in self.db.execute(f'PRAGMA foreign_key_list("{table}")'):
                target = foreign_key[2]
                exists = self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (target,),
                ).fetchone()
                if not exists:
                    missing_targets.append(f"{table}->{target}")
        self.assertEqual(missing_targets, [])
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_reapplying_migrations_is_a_no_op(self):
        self.assertEqual(apply_migrations(self.db, MIGRATIONS), [])
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 14
        )

    def test_foreign_key_constraints_reject_invalid_references(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO job_postings(id, company_id, title, created_at, updated_at) "
                "VALUES ('job-1', 'missing-company', 'Engineer', 'now', 'now')"
            )

    def test_migration_discovery_rejects_version_gaps(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            migration_directory = Path(temporary_directory)
            (migration_directory / "001_base.sql").write_text("SELECT 1;", encoding="utf-8")
            (migration_directory / "003_later.sql").write_text("SELECT 1;", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "contiguous"):
                discover_migrations(migration_directory)

    def test_migration_failure_rolls_back_all_its_changes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            migration_directory = Path(temporary_directory)
            (migration_directory / "001_base.sql").write_text(
                "CREATE TABLE schema_migrations("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);\n"
                "CREATE TABLE project_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);\n",
                encoding="utf-8",
            )
            (migration_directory / "002_broken.sql").write_text(
                "CREATE TABLE must_rollback(id INTEGER PRIMARY KEY);\n"
                "THIS IS NOT VALID SQL;\n",
                encoding="utf-8",
            )
            connection = connect(":memory:")
            try:
                with self.assertRaisesRegex(MigrationError, "002_broken.sql"):
                    apply_migrations(connection, migration_directory)
                self.assertIsNone(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE name = 'must_rollback'"
                    ).fetchone()
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )],
                    [(1,)],
                )
            finally:
                connection.close()


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        apply_migrations(self.db, MIGRATIONS)
        self.companies = CompanyRepository(self.db)
        self.contacts = ContactRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_company_can_be_created_and_read(self):
        company = self.companies.create(
            "  Example GmbH  ", website="https://example.test", industry="Software"
        )
        self.assertEqual(company["name"], "Example GmbH")
        self.assertEqual(company["website"], "https://example.test")
        self.assertEqual(company["created_at"], company["updated_at"])
        self.assertTrue(str(company["created_at"]).endswith("Z"))
        self.assertEqual(self.companies.get(str(company["id"])), company)

    def test_contact_query_values_are_parameterized(self):
        hostile_name = "X'); DROP TABLE companies; --"
        contact = self.contacts.create(hostile_name, email="hello@example.test")
        self.assertEqual(contact["display_name"], hostile_name)
        self.assertIsNotNone(
            self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'companies'"
            ).fetchone()
        )

    def test_repositories_list_in_stable_order_with_pagination(self):
        self.companies.create("Beta")
        self.companies.create("Alpha")
        self.companies.create("Charlie")
        self.assertEqual(
            [company["name"] for company in self.companies.list(limit=2)],
            ["Alpha", "Beta"],
        )
        self.assertEqual(
            [company["name"] for company in self.companies.list(limit=2, offset=2)],
            ["Charlie"],
        )

    def test_repositories_reject_empty_required_values_and_invalid_pages(self):
        with self.assertRaises(ValueError):
            self.companies.create("  ")
        with self.assertRaises(ValueError):
            self.contacts.create("")
        with self.assertRaises(ValueError):
            self.companies.list(limit=0)
        with self.assertRaises(ValueError):
            self.contacts.list(offset=-1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
