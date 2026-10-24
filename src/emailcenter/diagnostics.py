"""Allowlisted support information; never include mail contents or credentials."""

from importlib.metadata import version, PackageNotFoundError
import platform
import sqlite3
from .database import utc_timestamp


def diagnostic_report(project=None, *, libreoffice_path=""):
    packages = {}
    for name in ("PySide6", "openpyxl", "pdfplumber", "google-auth", "keyring", "tzdata"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    from .document_service import find_libreoffice
    from pathlib import Path
    converter = libreoffice_path or find_libreoffice()
    report = {"format_version": 1, "created_at_utc": utc_timestamp(),
              "runtime": {"python": platform.python_version(), "system": platform.system(),
                          "system_release": platform.release(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version},
              "packages": packages, "pdf_converter_available": bool(converter and Path(converter).is_file()), "project": None}
    if project:
        db = project.connection
        values = {"schema_version": db.execute("SELECT value FROM project_metadata WHERE key='schema_version'").fetchone()[0],
                  "database_integrity_ok": db.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                  "foreign_keys_ok": not bool(db.execute("PRAGMA foreign_key_check").fetchall()),
                  "enabled_gmail_accounts": db.execute("SELECT COUNT(*) FROM email_provider_accounts WHERE is_enabled=1 AND deleted_at IS NULL").fetchone()[0]}
        values["mail_job_status_counts"] = {row["status"]: row["count"] for row in db.execute("SELECT status,COUNT(*) AS count FROM email_jobs GROUP BY status")}
        values["bulk_status_counts"] = {row["status"]: row["count"] for row in db.execute("SELECT status,COUNT(*) AS count FROM email_bulk_dispatches GROUP BY status")}
        values["word_run_status_counts"] = {row["status"]: row["count"] for row in db.execute("SELECT status,COUNT(*) AS count FROM word_replace_runs GROUP BY status")}
        report["project"] = values
    return report
