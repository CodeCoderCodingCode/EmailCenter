"""SQLite connection factory with consistent project database settings."""

from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path


def connect(database: str | PathLike[str], *, timeout: float = 5.0) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign keys on that connection.

    Parent directories are created for file-backed databases. ``:memory:`` is
    passed through unchanged, which is useful for isolated tests.
    """
    database_name = str(database)
    if not database_name:
        raise ValueError("A database path is required.")
    if timeout < 0:
        raise ValueError("timeout must be non-negative.")

    if database_name != ":memory:":
        path = Path(database_name).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        database_name = str(path)

    connection = sqlite3.connect(database_name, timeout=timeout, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise sqlite3.DatabaseError("Could not enable SQLite foreign key enforcement.")
    return connection

