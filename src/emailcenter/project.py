"""Local project lifecycle, safe project paths, and database backup support."""

from __future__ import annotations

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from uuid import uuid4
import zipfile

from .database import apply_migrations, connect, utc_timestamp
from .project_setup import initial_records


PROJECT_FORMAT_VERSION = 1
MANIFEST_FILENAME = "emailcenter.json"
DATABASE_FILENAME = "emailcenter.sqlite3"
PROJECT_DIRECTORIES = ("imports", "templates", "documents", "exports", "backups", "tmp", "logs")
from .resources import resource_path
DEFAULT_MIGRATIONS_DIRECTORY = resource_path('migrations')


class ProjectError(RuntimeError):
    """Raised when a project is incomplete, invalid, or cannot be recovered."""


class Project:
    """An opened local project and its live database connection."""

    def __init__(self, path: Path, manifest: dict[str, object], connection: sqlite3.Connection):
        self.path = path
        self.manifest = manifest
        self.connection = connection
        self._closed = False

    @property
    def project_id(self) -> str:
        return str(self.manifest["project_id"])

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def database_path(self) -> Path:
        return self.path / DATABASE_FILENAME

    @property
    def is_closed(self) -> bool:
        return self._closed

    def file_path(self, relative_path: str | Path, *, create_parent: bool = False) -> Path:
        """Resolve a project-relative path and reject absolute/path-traversal paths."""
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ProjectError("Project file paths must be relative to the project folder.")
        root = self.path.resolve()
        result = (root / relative).resolve()
        if not result.is_relative_to(root) or result == root:
            raise ProjectError("Project file path escapes the project folder.")
        if create_parent:
            result.parent.mkdir(parents=True, exist_ok=True)
        return result

    def create_backup(self, directory=None) -> Path:
        """Create and verify an atomic archive of the database and project files."""
        self._ensure_open()
        if self.connection.in_transaction:
            raise ProjectError("Finish the current database transaction before creating a backup.")
        backup_id = str(uuid4())
        created_at = utc_timestamp()
        timestamp = created_at.replace(":", "").replace("-", "")
        backup_name = f"project-{timestamp}-{backup_id[:8]}.zip"
        relative_backup_path = Path("backups") / backup_name
        backup_path = self.file_path(relative_backup_path, create_parent=True)
        metadata_path = str(relative_backup_path)
        if directory:
            target = Path(directory).expanduser()
            if not target.is_absolute():
                raise ProjectError(_ui_tr('Backup-Ziel muss ein absoluter Pfad sein.'))
            target = target.resolve() / hashlib.sha256(self.project_id.encode()).hexdigest()[:16]
            for content_directory in ("imports", "templates", "documents", "exports"):
                if target.is_relative_to((self.path / content_directory).resolve()):
                    raise ProjectError(_ui_tr('Backup-Ziel darf nicht in den gesicherten Projektdateien liegen.'))
            target.mkdir(parents=True, exist_ok=True)
            backup_path = target / backup_name
            metadata_path = str(backup_path)

        self.connection.execute(
            "INSERT INTO backup_metadata "
            "(id, file_path, backup_type, encrypted, status, created_at) "
            "VALUES (?, ?, 'Manual', 0, 'Created', ?)",
            (backup_id, metadata_path, created_at),
        )
        try:
            with tempfile.TemporaryDirectory(prefix="emailcenter-backup-", dir=backup_path.parent) as temporary_directory:
                staging_directory = Path(temporary_directory)
                staged_database = staging_directory / DATABASE_FILENAME
                staged_archive = staging_directory / backup_name

                target = connect(staged_database)
                try:
                    self.connection.backup(target)
                    integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                    foreign_key_violations = target.execute("PRAGMA foreign_key_check").fetchall()
                    if integrity != "ok" or foreign_key_violations:
                        raise ProjectError(
                            "Database backup failed verification "
                            f"(integrity={integrity!r}, foreign_keys={foreign_key_violations!r})."
                        )
                finally:
                    target.close()

                with zipfile.ZipFile(staged_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(self.path / MANIFEST_FILENAME, MANIFEST_FILENAME)
                    archive.write(staged_database, DATABASE_FILENAME)
                    for directory_name in ("imports", "templates", "documents", "exports"):
                        source_directory = self.path / directory_name
                        for source_path in source_directory.rglob("*"):
                            if source_path.is_symlink():
                                raise ProjectError(
                                    f"Project backups do not follow symbolic links: {source_path}"
                                )
                            if source_path.is_file():
                                relative = source_path.relative_to(self.path)
                                self.file_path(relative)
                                archive.write(source_path, relative.as_posix())
                from .backups import write_index, inspect_backup
                write_index(staged_archive, self.project_id)
                inspect_backup(staged_archive)

                with zipfile.ZipFile(staged_archive, "r") as archive:
                    corrupted_member = archive.testzip()
                    if corrupted_member is not None:
                        raise ProjectError(f"Backup archive verification failed at {corrupted_member}.")
                    required_members = {MANIFEST_FILENAME, DATABASE_FILENAME}
                    if not required_members.issubset(archive.namelist()):
                        raise ProjectError("Backup archive is missing its manifest or database.")
                    verification_database = staging_directory / "verification.sqlite3"
                    verification_database.write_bytes(archive.read(DATABASE_FILENAME))

                verification_connection = connect(verification_database)
                try:
                    integrity = verification_connection.execute("PRAGMA integrity_check").fetchone()[0]
                    violations = verification_connection.execute("PRAGMA foreign_key_check").fetchall()
                    if integrity != "ok" or violations:
                        raise ProjectError("Archived project database failed verification.")
                finally:
                    verification_connection.close()

                os.replace(staged_archive, backup_path)

            file_size = backup_path.stat().st_size
            file_hash = _sha256(backup_path)
            self.connection.execute(
                "UPDATE backup_metadata "
                "SET file_size_bytes = ?, file_hash = ?, status = 'Verified', verified_at = ? "
                "WHERE id = ?",
                (file_size, file_hash, utc_timestamp(), backup_id),
            )
            return backup_path
        except Exception as error:
            backup_path.unlink(missing_ok=True)
            self.connection.execute(
                "UPDATE backup_metadata SET status = 'Failed' WHERE id = ?", (backup_id,)
            )
            if isinstance(error, ProjectError):
                raise
            raise ProjectError(f"Could not create database backup: {error}") from error

    def close(self) -> None:
        if not self._closed:
            self.connection.close()
            self._closed = True

    def __enter__(self) -> Project:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProjectError("Project is already closed.")


def _publish_project(staging_path: Path, project_path: Path) -> None:
    """Allow brief Windows sharing/access locks after the database is closed."""
    delays = (0.05, 0.1, 0.2, 0.4)
    for attempt in range(len(delays) + 1):
        if project_path.exists():
            raise ProjectError(f"Project path already exists: {project_path}")
        try:
            staging_path.rename(project_path)
            return
        except OSError as error:
            if (getattr(error, "winerror", None) not in (5, 32)
                    or attempt == len(delays) or project_path.exists()
                    or not staging_path.is_dir() or staging_path.is_symlink()):
                raise
            time.sleep(delays[attempt])


def create_project(
    path: str | Path,
    *,
    name: str | None = None,
    workspace_mode: str = "applications",
    goal: str = "",
    initial_profile: dict | None = None,
    initial_signature: dict | None = None,
    defaults: dict | None = None,
    initial_document: dict | None = None,
    initial_source: dict | None = None,
    migrations_directory: str | Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> Project:
    """Create a new project folder and initialize its database."""
    if workspace_mode not in ("applications", "mail"):
        raise ProjectError(_ui_tr('Ungültiger Arbeitsmodus.'))
    if not isinstance(goal, str) or len(goal) > 4000:
        raise ProjectError(_ui_tr('Das Projektziel darf höchstens 4000 Zeichen enthalten.'))
    try:
        profile, signature = initial_records(initial_profile, initial_signature)
        from .project_defaults import validate_defaults
        project_defaults = validate_defaults(defaults or {})
        if any(project_defaults[key] for key in ("document_version_id", "applicant_profile_id", "source_list_id")):
            raise ValueError(_ui_tr('Zuordnungen entstehen erst im neuen Projekt.'))
    except ValueError as error:
        raise ProjectError(str(error)) from error
    project_path = Path(path).expanduser().resolve()
    if project_path.exists():
        raise ProjectError(f"Project path already exists: {project_path}")
    project_name = (name or project_path.name).strip()
    if not project_name:
        raise ProjectError("Project name must not be empty.")
    project_path.parent.mkdir(parents=True, exist_ok=True)

    staging_path = project_path.with_name(f".{project_path.name}.creating-{uuid4().hex}")
    try:
        staging_path.mkdir()
        for directory_name in PROJECT_DIRECTORIES:
            (staging_path / directory_name).mkdir()

        manifest = {
            "project_format_version": PROJECT_FORMAT_VERSION,
            "project_id": str(uuid4()),
            "name": project_name,
            "created_at": utc_timestamp(),
            "updated_at": utc_timestamp(),
            "database": DATABASE_FILENAME,
        }
        _write_manifest(staging_path / MANIFEST_FILENAME, manifest)

        connection = connect(staging_path / DATABASE_FILENAME)
        try:
            apply_migrations(connection, migrations_directory)
            connection.executemany(
                "INSERT INTO project_metadata(key,value) VALUES (?,?)",
                (("workspace_mode", workspace_mode), ("project_goal", goal.strip())),
            )
            timestamp = utc_timestamp()
            if profile:
                profile_id = str(uuid4())
                connection.execute(
                    "INSERT INTO applicant_profiles(id,display_name,email,phone,address_json,custom_fields_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (profile_id, profile["display_name"], profile["email"] or None,
                     profile["phone"] or None, profile.get("address_json", "{}"), profile.get("custom_fields_json", "{}"), timestamp, timestamp),
                )
                project_defaults["applicant_profile_id"] = profile_id
            if signature:
                connection.execute(
                    "INSERT INTO email_signatures(id,name,content_text,is_default,created_at,updated_at) "
                    "VALUES (?,?,?,1,?,?)",
                    (str(uuid4()), signature["name"], signature["content_text"], timestamp, timestamp),
                )
            staged = Project(staging_path, manifest, connection)
            if initial_document:
                from .document_service import DocumentService
                document_options = dict(initial_document)
                expected_hash = document_options.pop("expected_hash", None)
                imported = DocumentService(staged).import_template(**document_options)
                if expected_hash and imported["version"]["content_hash"] != expected_hash:
                    raise ProjectError(_ui_tr('Übernommene Vorlagenversion wurde geändert; neu wählen.'))
                project_defaults["document_version_id"] = imported["version"]["id"]
            if initial_source:
                from .data_source_library import DataSourceLibrary
                rows = [{"fields": row["fields"]} for row in initial_source["rows"]]
                saved = DataSourceLibrary(connection).save_list(initial_source["name"], rows)
                project_defaults["source_list_id"] = saved["list"]["id"]
            connection.execute("INSERT INTO project_metadata(key,value) VALUES('project_defaults',?)", (json.dumps(project_defaults),))
        finally:
            connection.close()

        _publish_project(staging_path, project_path)
        return open_project(project_path, migrations_directory=migrations_directory)
    except Exception as error:
        # The staging directory name is generated beside the requested target;
        # clean up only that exact temporary directory, never a user project.
        if staging_path.exists() and staging_path.parent == project_path.parent:
            shutil.rmtree(staging_path)
        if isinstance(error, ProjectError):
            raise
        raise ProjectError(f"Could not create project at {project_path}: {error}") from error


def open_project(
    path: str | Path,
    *,
    migrations_directory: str | Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> Project:
    """Validate and open an existing project, applying pending migrations."""
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        raise ProjectError(f"Project folder does not exist: {project_path}")

    manifest_path = project_path / MANIFEST_FILENAME
    database_path = project_path / DATABASE_FILENAME
    if not manifest_path.is_file() or not database_path.is_file():
        raise ProjectError("Project is incomplete: manifest or database file is missing.")
    missing_directories = [
        directory_name
        for directory_name in PROJECT_DIRECTORIES
        if not (project_path / directory_name).is_dir()
    ]
    if missing_directories:
        raise ProjectError(f"Project is incomplete; missing folders: {missing_directories}.")

    manifest = _read_manifest(manifest_path)
    if manifest.get("project_format_version") != PROJECT_FORMAT_VERSION:
        raise ProjectError(
            "Unsupported project format version: "
            f"{manifest.get('project_format_version')!r}."
        )
    if manifest.get("database") != DATABASE_FILENAME:
        raise ProjectError("Project manifest points to an unsupported database filename.")

    connection = connect(database_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ProjectError(f"Project database failed integrity check: {integrity}")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ProjectError(f"Project database has foreign-key violations: {violations!r}")
        apply_migrations(connection, migrations_directory)
    except Exception as error:
        connection.close()
        if isinstance(error, ProjectError):
            raise
        raise ProjectError(f"Could not open project database: {error}") from error

    return Project(project_path, manifest, connection)


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectError(f"Project manifest cannot be read: {error}") from error
    if not isinstance(value, dict):
        raise ProjectError("Project manifest must contain a JSON object.")
    for key in ("project_id", "name", "created_at", "database"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ProjectError(f"Project manifest has an invalid {key!r} value.")
    return value


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary_path, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

