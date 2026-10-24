"""Discovery and transactional application of numbered SQLite migrations."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from pathlib import Path
from typing import Iterator

from .timestamps import utc_timestamp


_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]+)_(?P<name>[a-z][a-z0-9_]*)\.sql$")
_TRANSACTION_START = re.compile(r"^(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", re.IGNORECASE)


class MigrationError(RuntimeError):
    """Raised when migrations are missing, inconsistent, or fail to apply."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def discover_migrations(directory: str | Path) -> list[Migration]:
    """Return numbered SQL migrations, rejecting ambiguous or missing versions."""
    migration_dir = Path(directory)
    if not migration_dir.is_dir():
        raise MigrationError(f"Migration directory does not exist: {migration_dir}")

    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(migration_dir.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(
                f"Invalid migration filename {path.name!r}; expected '<number>_<name>.sql'."
            )
        version = int(match.group("version"))
        if version < 1:
            raise MigrationError(f"Migration versions must be positive: {path.name}")
        if version in seen_versions:
            raise MigrationError(f"Duplicate migration version {version}.")
        seen_versions.add(version)
        migrations.append(Migration(version, match.group("name"), path))

    migrations.sort(key=lambda migration: migration.version)
    expected_versions = list(range(1, len(migrations) + 1))
    actual_versions = [migration.version for migration in migrations]
    if actual_versions != expected_versions:
        raise MigrationError(
            f"Migration versions must be contiguous from 1; found {actual_versions}."
        )
    return migrations


def apply_migrations(
    connection: sqlite3.Connection,
    directory: str | Path,
) -> list[int]:
    """Apply pending migrations atomically and return their version numbers.

    The connection factory's foreign-key setting is required. Migration files
    contain schema statements only; this runner owns transaction boundaries and
    records each successful version in ``schema_migrations``.
    """
    if connection.in_transaction:
        raise MigrationError("Migrations cannot run inside an existing transaction.")
    try:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    except sqlite3.Error as error:
        raise MigrationError("Could not inspect SQLite foreign key setting.") from error
    if not foreign_keys_enabled:
        raise MigrationError("Use emailcenter.database.connect() so foreign keys are enabled.")

    migrations = discover_migrations(directory)
    applied = _read_applied_migrations(connection)
    available_versions = {migration.version for migration in migrations}
    unknown_versions = sorted(set(applied) - available_versions)
    if unknown_versions:
        raise MigrationError(
            f"Database contains migration versions missing from disk: {unknown_versions}."
        )

    applied_now: list[int] = []
    for migration in migrations:
        previous_name = applied.get(migration.version)
        if previous_name is not None:
            if previous_name != migration.name:
                raise MigrationError(
                    f"Migration {migration.version} is recorded as {previous_name!r}, "
                    f"but the file is named {migration.name!r}."
                )
            continue

        try:
            sql = migration.path.read_text(encoding="utf-8")
            connection.execute("BEGIN IMMEDIATE")
            for statement in _iter_statements(sql):
                if _TRANSACTION_START.match(_without_leading_comments(statement).lstrip()):
                    raise MigrationError(
                        f"{migration.path.name} must not manage its own transactions."
                    )
                connection.execute(statement)

            if not _table_exists(connection, "schema_migrations"):
                raise MigrationError(
                    f"{migration.path.name} did not create schema_migrations."
                )
            connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, utc_timestamp()),
            )
            _update_project_schema_version(connection, migration.version)
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise MigrationError(
                    f"{migration.path.name} leaves foreign key violations: {violations!r}."
                )
            connection.commit()
            applied_now.append(migration.version)
        except Exception as error:
            if connection.in_transaction:
                connection.rollback()
            if isinstance(error, MigrationError):
                raise MigrationError(
                    f"Failed to apply migration {migration.path.name}: {error}"
                ) from error
            raise MigrationError(
                f"Failed to apply migration {migration.path.name}: {error}"
            ) from error

    return applied_now


def _read_applied_migrations(connection: sqlite3.Connection) -> dict[int, str]:
    if not _table_exists(connection, "schema_migrations"):
        return {}
    try:
        rows = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version")
        return {int(row[0]): str(row[1]) for row in rows}
    except sqlite3.Error as error:
        raise MigrationError("schema_migrations has an invalid structure.") from error


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
    ).fetchone() is not None


def _update_project_schema_version(connection: sqlite3.Connection, version: int) -> None:
    if _table_exists(connection, "project_metadata"):
        connection.execute(
            "UPDATE project_metadata SET value = ? WHERE key = 'schema_version'",
            (str(version),),
        )


def _iter_statements(sql: str) -> Iterator[str]:
    """Split a SQL script at complete statement boundaries, respecting strings."""
    buffer: list[str] = []
    for character in sql:
        buffer.append(character)
        if character == ";":
            candidate = "".join(buffer)
            if sqlite3.complete_statement(candidate):
                if _without_leading_comments(candidate).strip():
                    yield candidate
                buffer.clear()

    remainder = "".join(buffer)
    if _without_leading_comments(remainder).strip():
        raise MigrationError("Migration contains an incomplete SQL statement.")


def _without_leading_comments(statement: str) -> str:
    """Remove SQL comments for transaction-control checks and empty detection."""
    remaining = statement.lstrip()
    while remaining:
        if remaining.startswith("--"):
            newline = remaining.find("\n")
            if newline == -1:
                return ""
            remaining = remaining[newline + 1 :].lstrip()
        elif remaining.startswith("/*"):
            closing = remaining.find("*/", 2)
            if closing == -1:
                return ""
            remaining = remaining[closing + 2 :].lstrip()
        else:
            return remaining
    return ""

