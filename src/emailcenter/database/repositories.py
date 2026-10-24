"""Small parameterized repositories for the first project entities."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
import json
import re
import sqlite3
from typing import Iterator
from uuid import uuid4

from .timestamps import utc_timestamp


class CompanyRepository:
    """Create and read company records using an existing project connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        name: str,
        *,
        company_id: str | None = None,
        website: str | None = None,
        industry: str | None = None,
        notes: str | None = None,
    ) -> dict[str, object]:
        if not name.strip():
            raise ValueError("Company name must not be empty.")
        record_id = company_id or str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO companies "
            "(id, name, website, industry, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record_id, name.strip(), website, industry, notes, now, now),
        )
        record = self.get(record_id)
        if record is None:
            raise RuntimeError("Inserted company could not be read back.")
        return record

    def get(self, company_id: str, *, include_deleted: bool = False) -> dict[str, object] | None:
        query = "SELECT * FROM companies WHERE id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        row = self._connection.execute(query, (company_id,)).fetchone()
        return dict(row) if row is not None else None

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict[str, object]]:
        _validate_page(limit, offset)
        query = "SELECT * FROM companies"
        if not include_deleted:
            query += " WHERE deleted_at IS NULL"
        query += " ORDER BY name COLLATE NOCASE, id LIMIT ? OFFSET ?"
        rows = self._connection.execute(query, (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def link_contact(
        self,
        company_id: str,
        contact_id: str,
        *,
        relationship_type: str | None = None,
        is_primary: bool = False,
    ) -> None:
        if not isinstance(is_primary, bool):
            raise ValueError("is_primary must be a boolean.")
        self._connection.execute(
            "INSERT INTO company_contacts "
            "(company_id, contact_id, relationship_type, is_primary, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (company_id, contact_id, relationship_type, int(is_primary), utc_timestamp()),
        )

    def list_contacts(self, company_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT c.*, cc.relationship_type, cc.is_primary "
            "FROM contacts AS c JOIN company_contacts AS cc ON cc.contact_id = c.id "
            "WHERE cc.company_id = ? AND c.deleted_at IS NULL "
            "ORDER BY cc.is_primary DESC, c.display_name COLLATE NOCASE",
            (company_id,),
        ).fetchall()
        return [dict(row) for row in rows]


class ContactRepository:
    """Create and read contact records using an existing project connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        display_name: str,
        *,
        contact_id: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        position: str | None = None,
        notes: str | None = None,
    ) -> dict[str, object]:
        if not display_name.strip():
            raise ValueError("Contact display name must not be empty.")
        record_id = contact_id or str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO contacts "
            "(id, first_name, last_name, display_name, email, phone, position, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                first_name,
                last_name,
                display_name.strip(),
                email,
                phone,
                position,
                notes,
                now,
                now,
            ),
        )
        record = self.get(record_id)
        if record is None:
            raise RuntimeError("Inserted contact could not be read back.")
        return record

    def get(self, contact_id: str, *, include_deleted: bool = False) -> dict[str, object] | None:
        query = "SELECT * FROM contacts WHERE id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        row = self._connection.execute(query, (contact_id,)).fetchone()
        return dict(row) if row is not None else None

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict[str, object]]:
        _validate_page(limit, offset)
        query = "SELECT * FROM contacts"
        if not include_deleted:
            query += " WHERE deleted_at IS NULL"
        query += " ORDER BY display_name COLLATE NOCASE, id LIMIT ? OFFSET ?"
        rows = self._connection.execute(query, (limit, offset)).fetchall()
        return [dict(row) for row in rows]


class JobPostingRepository:
    """Create and read job postings linked to companies."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        company_id: str,
        title: str,
        *,
        job_posting_id: str | None = None,
        reference_number: str | None = None,
        location: str | None = None,
        source_url: str | None = None,
        description: str | None = None,
        employment_type: str | None = None,
        deadline: str | None = None,
    ) -> dict[str, object]:
        if not title.strip():
            raise ValueError("Job title must not be empty.")
        record_id = job_posting_id or str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO job_postings "
            "(id, company_id, title, reference_number, location, source_url, description, "
            "employment_type, deadline, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                company_id,
                title.strip(),
                reference_number,
                location,
                source_url,
                description,
                employment_type,
                deadline,
                now,
                now,
            ),
        )
        record = self.get(record_id)
        if record is None:
            raise RuntimeError("Inserted job posting could not be read back.")
        return record

    def get(self, job_posting_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT * FROM job_postings WHERE id = ? AND deleted_at IS NULL",
            (job_posting_id,),
        ).fetchone()
        return dict(row) if row is not None else None


class ApplicationStatusRepository:
    """List and configure application status values."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def list(self, *, include_terminal: bool = True) -> list[dict[str, object]]:
        query = "SELECT * FROM application_statuses"
        if not include_terminal:
            query += " WHERE is_terminal = 0"
        rows = self._connection.execute(query + " ORDER BY sort_order, label COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]

    def get_by_code(self, code: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT * FROM application_statuses WHERE code = ?", (code,)
        ).fetchone()
        return dict(row) if row is not None else None

    def create(
        self,
        code: str,
        label: str,
        *,
        sort_order: int = 100,
        is_terminal: bool = False,
    ) -> dict[str, object]:
        if re.fullmatch(r"[a-z][a-z0-9_]*", code) is None:
            raise ValueError("Status code must contain lowercase letters, digits, or underscores.")
        if not label.strip():
            raise ValueError("Status label must not be empty.")
        status_id = str(uuid4())
        self._connection.execute(
            "INSERT INTO application_statuses "
            "(id, code, label, sort_order, is_system, is_terminal, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?)",
            (status_id, code, label.strip(), sort_order, int(is_terminal), utc_timestamp()),
        )
        status = self.get_by_code(code)
        if status is None:
            raise RuntimeError("Inserted application status could not be read back.")
        return status

    def rename(self, code: str, label: str) -> None:
        if not label.strip():
            raise ValueError("Status label must not be empty.")
        cursor = self._connection.execute(
            "UPDATE application_statuses SET label = ? WHERE code = ?",
            (label.strip(), code),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Unknown application status: {code}")


class ApplicationRepository:
    """Create applications and enforce basic status transition rules."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self, title: str, **fields,
    ) -> dict[str, object]:
        return self._create(title, _manage_transaction=True, **fields)

    def create_in_transaction(self, title: str, **fields) -> dict[str, object]:
        """Let an import persist the application and row receipt in one transaction."""
        if not self._connection.in_transaction:
            raise RuntimeError("An existing transaction is required.")
        return self._create(title, _manage_transaction=False, **fields)

    def _create(
        self,
        title: str,
        *,
        status_code: str = "draft",
        application_id: str | None = None,
        applicant_profile_id: str | None = None,
        company_id: str | None = None,
        job_posting_id: str | None = None,
        application_date: str | None = None,
        next_follow_up_at: str | None = None,
        source: str | None = None,
        notes: str | None = None,
        custom_fields: dict[str, object] | None = None,
        _manage_transaction: bool = True,
    ) -> dict[str, object]:
        if not title.strip():
            raise ValueError("Application title must not be empty.")
        status = self._status_by_code(status_code)
        if job_posting_id is not None:
            posting = self._connection.execute(
                "SELECT company_id FROM job_postings WHERE id = ? AND deleted_at IS NULL",
                (job_posting_id,),
            ).fetchone()
            if posting is None:
                raise KeyError(f"Unknown job posting: {job_posting_id}")
            posting_company_id = posting[0]
            if company_id is not None and company_id != posting_company_id:
                raise ValueError("Application company must match the job posting's company.")
            company_id = posting_company_id

        fields_json = _serialize_json_object(
            custom_fields if custom_fields is not None else {}, "custom_fields"
        )
        record_id = application_id or str(uuid4())
        now = utc_timestamp()
        with _atomic(self._connection) if _manage_transaction else nullcontext():
            self._connection.execute(
                "INSERT INTO applications "
                "(id, applicant_profile_id, company_id, job_posting_id, status_id, title, "
                "application_date, next_follow_up_at, source, notes, custom_fields_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    applicant_profile_id,
                    company_id,
                    job_posting_id,
                    status["id"],
                    title.strip(),
                    application_date,
                    next_follow_up_at,
                    source,
                    notes,
                    fields_json,
                    now,
                    now,
                ),
            )
            _write_activity(
                self._connection,
                "application.created",
                "applications",
                record_id,
                f"Application created with status {status_code}.",
                {"status_code": status_code},
                now,
            )
        record = self.get(record_id)
        if record is None:
            raise RuntimeError("Inserted application could not be read back.")
        return record

    def get(self, application_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT a.*, s.code AS status_code, s.label AS status_label, "
            "s.is_terminal AS status_is_terminal "
            "FROM applications AS a JOIN application_statuses AS s ON s.id = a.status_id "
            "WHERE a.id = ? AND a.deleted_at IS NULL",
            (application_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        _validate_page(limit, offset)
        rows = self._connection.execute(
            "SELECT a.*, s.code AS status_code, s.label AS status_label, "
            "s.is_terminal AS status_is_terminal "
            "FROM applications AS a JOIN application_statuses AS s ON s.id = a.status_id "
            "WHERE a.deleted_at IS NULL ORDER BY a.updated_at DESC, a.id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def link_contact(
        self,
        application_id: str,
        contact_id: str,
        *,
        relationship_type: str | None = None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO application_contacts "
            "(application_id, contact_id, relationship_type, created_at) "
            "VALUES (?, ?, ?, ?)",
            (application_id, contact_id, relationship_type, utc_timestamp()),
        )

    def list_contacts(self, application_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT c.*, ac.relationship_type "
            "FROM contacts AS c JOIN application_contacts AS ac ON ac.contact_id = c.id "
            "WHERE ac.application_id = ? AND c.deleted_at IS NULL "
            "ORDER BY c.display_name COLLATE NOCASE",
            (application_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def change_status(self, application_id: str, new_status_code: str) -> dict[str, object]:
        new_status = self._status_by_code(new_status_code)
        now = utc_timestamp()
        with _atomic(self._connection):
            current = self._connection.execute(
                "SELECT a.status_id, s.code, s.is_terminal FROM applications AS a "
                "JOIN application_statuses AS s ON s.id = a.status_id "
                "WHERE a.id = ? AND a.deleted_at IS NULL",
                (application_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f"Unknown application: {application_id}")
            if current["code"] == new_status_code:
                unchanged = self.get(application_id)
                if unchanged is None:
                    raise KeyError(f"Unknown application: {application_id}")
                return unchanged
            if current["is_terminal"]:
                raise ValueError(
                    f"Application in terminal status {current['code']!r} cannot transition."
                )
            self._connection.execute(
                "UPDATE applications SET status_id = ?, updated_at = ? WHERE id = ?",
                (new_status["id"], now, application_id),
            )
            _write_activity(
                self._connection,
                "application.status_changed",
                "applications",
                application_id,
                f"Application status changed from {current['code']} to {new_status_code}.",
                {"from": current["code"], "to": new_status_code},
                now,
            )
        record = self.get(application_id)
        if record is None:
            raise RuntimeError("Updated application could not be read back.")
        return record

    def _status_by_code(self, code: str) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT * FROM application_statuses WHERE code = ?", (code,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown application status: {code}")
        return dict(row)


class TemplateRepository:
    """Create document templates and append immutable template versions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, name: str, *, description: str | None = None) -> dict[str, object]:
        if not name.strip():
            raise ValueError("Template name must not be empty.")
        template_id = str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO templates(id, name, template_type, description, created_at, updated_at) "
            "VALUES (?, ?, 'document', ?, ?, ?)",
            (template_id, name.strip(), description, now, now),
        )
        row = self._connection.execute(
            "SELECT * FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        return dict(row)

    def add_version(
        self,
        template_id: str,
        *,
        file_path: str,
        placeholders: list[str],
        content_hash: str,
        configuration: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not isinstance(placeholders, list) or not all(
            isinstance(value, str) for value in placeholders
        ):
            raise ValueError("placeholders must be a list of strings.")
        version_id = str(uuid4())
        now = utc_timestamp()
        with _atomic(self._connection):
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 "
                "FROM template_versions WHERE template_id = ?",
                (template_id,),
            ).fetchone()
            version_number = int(row[0])
            self._connection.execute(
                "INSERT INTO template_versions "
                "(id, template_id, version_number, file_path, placeholders_json, "
                "configuration_json, content_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    template_id,
                    version_number,
                    file_path,
                    json.dumps(sorted(set(placeholders)), ensure_ascii=False),
                    _serialize_json_object(
                        configuration if configuration is not None else {}, "configuration"
                    ),
                    content_hash,
                    now,
                ),
            )
            self._connection.execute(
                "UPDATE templates SET updated_at = ? WHERE id = ?", (now, template_id)
            )
        version = self.get_version(version_id)
        if version is None:
            raise RuntimeError("Inserted template version could not be read back.")
        return version

    def get_version(self, version_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT tv.*, t.name AS template_name, t.template_type "
            "FROM template_versions AS tv JOIN templates AS t ON t.id = tv.template_id "
            "WHERE tv.id = ?",
            (version_id,),
        ).fetchone()
        return dict(row) if row is not None else None


class DocumentSetRepository:
    """Group generated documents and their format variants."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, name: str, *, application_id: str | None = None) -> dict[str, object]:
        if not name.strip():
            raise ValueError("Document set name must not be empty.")
        set_id = str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO document_sets(id, application_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (set_id, application_id, name.strip(), now, now),
        )
        record = self.get(set_id)
        if record is None:
            raise RuntimeError("Inserted document set could not be read back.")
        return record

    def get(self, set_id: str) -> dict[str, object] | None:
        row = self._connection.execute("SELECT * FROM document_sets WHERE id = ?", (set_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_documents(self, set_id: str) -> list[dict[str, object]]:
        return [dict(row) for row in self._connection.execute(
            "SELECT * FROM documents WHERE document_set_id = ? AND deleted_at IS NULL "
            "ORDER BY created_at, id", (set_id,),
        )]


class DocumentRepository:
    """Record generated project documents and their template provenance."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        file_path: str,
        original_filename: str,
        file_size_bytes: int,
        file_hash: str,
        template_version_id: str | None,
        document_type: str,
        application_id: str | None = None,
        file_format: str = "docx",
        source_document_id: str | None = None,
        document_set_id: str | None = None,
    ) -> dict[str, object]:
        mime_types = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
        }
        if file_format not in mime_types:
            raise ValueError(f"Unsupported document format: {file_format}")
        if document_set_id is not None:
            document_set = DocumentSetRepository(self._connection).get(document_set_id)
            if document_set is None:
                raise KeyError(f"Unknown document set: {document_set_id}")
            if document_set["application_id"] != application_id:
                raise ValueError("Document and document set must belong to the same application.")
        document_id = str(uuid4())
        now = utc_timestamp()
        self._connection.execute(
            "INSERT INTO documents "
            "(id, application_id, template_version_id, source_document_id, document_type, "
            "format, file_path, original_filename, mime_type, file_size_bytes, file_hash, "
            "created_at, updated_at, document_set_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                application_id,
                template_version_id,
                source_document_id,
                document_type,
                file_format,
                file_path,
                original_filename,
                mime_types[file_format],
                file_size_bytes,
                file_hash,
                now,
                now,
                document_set_id,
            ),
        )
        row = self._connection.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        return dict(row)


def _validate_page(limit: int, offset: int) -> None:
    if limit < 1:
        raise ValueError("limit must be greater than zero.")
    if offset < 0:
        raise ValueError("offset must be non-negative.")


def _serialize_json_object(value: dict[str, object], field_name: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must contain valid JSON values.") from error


def _write_activity(
    connection: sqlite3.Connection,
    event_type: str,
    entity_type: str,
    entity_id: str,
    message: str,
    details: dict[str, object],
    created_at: str,
) -> None:
    connection.execute(
        "INSERT INTO activity_log "
        "(id, event_type, entity_type, entity_id, message, details_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid4()),
            event_type,
            entity_type,
            entity_id,
            message,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
            created_at,
        ),
    )


@contextmanager
def _atomic(connection: sqlite3.Connection) -> Iterator[None]:
    if connection.in_transaction:
        raise RuntimeError("Repository operation cannot run inside an existing transaction.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except Exception:
        connection.rollback()
        raise

