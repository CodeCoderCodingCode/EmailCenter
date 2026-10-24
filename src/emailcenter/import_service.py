"""Durable previews, duplicate review and atomic row-by-row local imports."""

from __future__ import annotations

from .language import translate as _ui_tr, format_text as _ui_format

from contextlib import contextmanager
from datetime import date, datetime
import json
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4

from .database import ApplicationRepository, CompanyRepository, ContactRepository, utc_timestamp
from .import_sources import FIELDS, read_source, source_hash, suggest_mapping
from .project import Project


class ImportServiceError(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _key(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


@contextmanager
def _transaction(connection):
    if connection.in_transaction:
        raise ImportServiceError(_ui_tr('Bitte die laufende Transaktion zuerst abschließen.'))
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


class ImportService:
    def __init__(self, project: Project):
        self.project = project
        self.db = project.connection
        self.db.create_function("ec_import_key", 1, _key)
        self._duplicate_indexes = {}
        self._cache_stamp = None

    def inspect(self, source_path: str, options: dict | None = None) -> dict:
        before = source_hash(source_path)
        table = read_source(source_path, options)
        if source_hash(source_path) != before:
            raise ImportServiceError(_ui_tr('Die Quelldatei wurde beim Lesen geändert. Bitte erneut auswählen.'))
        return {"source_path": source_path, "source_hash": before,
                "file_type": Path(source_path).suffix.lower()[1:], "headers": list(table.headers),
                "sample": [row.values for row in table.rows[:20]], "total_rows": len(table.rows),
                "options": table.options, "sheets": list(table.sheets), "fields": FIELDS,
                "suggestions": {entity: suggest_mapping(table.headers, entity) for entity in FIELDS},
                "profiles": self.list_profiles()}

    def list_profiles(self):
        profiles = [dict(row) for row in self.db.execute(
            "SELECT * FROM import_profiles WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE, id")]
        for profile in profiles:
            profile["mapping"] = json.loads(profile["mapping_json"])
            profile["options"] = json.loads(profile["options_json"])
        return profiles

    def prepare(self, source_path: str, entity: str, mapping: dict[str, str], *, options: dict | None = None,
                expected_hash: str | None = None, profile_name: str | None = None, profile_id: str | None = None) -> dict:
        if entity == "data_rows":
            if mapping or profile_name or profile_id:
                raise ImportServiceError('Data sources use their original columns without a domain import profile.')
            return self.prepare_data_source(source_path, options=options, expected_hash=expected_hash)
        if entity not in FIELDS:
            raise ImportServiceError(_ui_tr('Unbekanntes Importziel.'))
        if profile_name is not None and not profile_name.strip():
            raise ImportServiceError(_ui_tr('Bitte einen Profilnamen eingeben oder das Speichern deaktivieren.'))
        if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
            raise ImportServiceError(_ui_tr('Ungültige Spaltenzuordnung.'))
        allowed = {field for field, _, _ in FIELDS[entity]}
        required = {field for field, _, mandatory in FIELDS[entity] if mandatory}
        if set(mapping) - allowed or not required <= set(mapping) or len(set(mapping.values())) != len(mapping):
            raise ImportServiceError(_ui_tr('Pflichtfelder zuordnen und jede Quellspalte höchstens einmal verwenden.'))
        source = Path(source_path).resolve()
        run_id = str(uuid4())
        relative = Path("imports") / run_id / source.name
        archive_path = self.project.file_path(relative, create_parent=True)
        try:
            before = source_hash(source)
            if expected_hash is not None and before != expected_hash:
                raise ImportServiceError(_ui_tr('Die Quelldatei wurde seit der Vorschau geändert. Bitte erneut einlesen.'))
            shutil.copyfile(source, archive_path)
            if source_hash(archive_path) != before:
                raise ImportServiceError(_ui_tr('Die Quelldatei wurde während der Kopie geändert.'))
            table = read_source(archive_path, options)
            if set(mapping.values()) - set(table.headers):
                raise ImportServiceError(_ui_tr('Eine zugeordnete Spalte fehlt in der Datei.'))
            config = {"entity": entity, "mapping": mapping, "options": table.options}
            prepared, seen = [], set()
            for row in table.rows:
                raw_fields = {field: row.values.get(column, "") for field, column in mapping.items()}
                fields, resolved, errors = self._validate(entity, raw_fields)
                errors = [*row.errors, *errors]
                identity = self._identity(entity, fields, resolved)
                if not row.errors and not any(value.strip() for value in row.values.values()):
                    status, errors = "Skipped", ["Leere Zeile."]
                elif errors:
                    status = "Invalid"
                else:
                    duplicates = self._duplicates(entity, fields, resolved)
                    if duplicates or identity in seen:
                        status = "DuplicateReview"
                        errors = ["Mögliches Duplikat im Projekt." if duplicates else "Mögliches Duplikat innerhalb der Datei."]
                    else:
                        status = "Valid"
                    seen.add(identity)
                prepared.append((str(uuid4()), run_id, row.number, _json(row.values),
                                 _json({"fields": fields, "allow_duplicate": False}), status, _json(errors), utc_timestamp()))
            with _transaction(self.db):
                if profile_id is not None:
                    profile = self.db.execute("SELECT file_type FROM import_profiles WHERE id=? AND deleted_at IS NULL", (profile_id,)).fetchone()
                    if profile is None or profile["file_type"] != source.suffix.lower()[1:]:
                        raise ImportServiceError(_ui_tr('Das ausgewählte Importprofil passt nicht zur Datei.'))
                if profile_name:
                    profile_id, now = str(uuid4()), utc_timestamp()
                    self.db.execute(
                        "INSERT INTO import_profiles(id,name,file_type,mapping_json,options_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (profile_id, profile_name.strip(), source.suffix.lower()[1:], _json(mapping),
                         _json({"entity": entity, **table.options}), now, now),
                    )
                self.db.execute(
                    "INSERT INTO import_runs(id,import_profile_id,source_filename,source_file_path,status,total_rows,created_at,configuration_json,source_file_hash) "
                    "VALUES(?,?,?,?,'Pending',?,?,?,?)",
                    (run_id, profile_id, source.name, relative.as_posix(), len(prepared), utc_timestamp(), _json(config), before),
                )
                self.db.executemany(
                    "INSERT INTO import_rows(id,import_run_id,row_number,source_data_json,mapped_data_json,status,errors_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    prepared,
                )
                self._sync(run_id, finalize=False)
            return self.detail(run_id)
        except BaseException:
            archive_path.unlink(missing_ok=True)
            raise

    def prepare_data_source(self, source_path, *, options=None, expected_hash=None):
        """Persist raw workflow rows without creating contacts or applications."""
        source = Path(source_path).resolve()
        run_id = str(uuid4())
        relative = Path('imports') / run_id / source.name
        archived = self.project.file_path(relative, create_parent=True)
        try:
            before = source_hash(source)
            if expected_hash is not None and before != expected_hash:
                raise ImportServiceError(_ui_tr('Die Quelldatei wurde seit der Vorschau geändert. Bitte erneut einlesen.'))
            shutil.copyfile(source, archived)
            if source_hash(archived) != before:
                raise ImportServiceError(_ui_tr('Die Quelldatei wurde während der Kopie geändert.'))
            table = read_source(archived, options)
            config = {'entity': 'data_rows', 'mapping': {}, 'options': table.options}
            records = []
            for row in table.rows:
                status = 'Invalid' if row.errors else 'Imported' if any(v.strip() for v in row.values.values()) else 'Skipped'
                records.append((str(uuid4()), run_id, row.number, _json(row.values),
                                _json({'fields': {}, 'allow_duplicate': False}), status, _json(row.errors), utc_timestamp()))
            with _transaction(self.db):
                self.db.execute("INSERT INTO import_runs(id,source_filename,source_file_path,status,total_rows,created_at,configuration_json,source_file_hash) VALUES(?,?,?,'Pending',?,?,?,?)",
                                (run_id, source.name, relative.as_posix(), len(records), utc_timestamp(), _json(config), before))
                self.db.executemany('INSERT INTO import_rows(id,import_run_id,row_number,source_data_json,mapped_data_json,status,errors_json,created_at) VALUES(?,?,?,?,?,?,?,?)', records)
                self._sync(run_id, finalize=True)
            return self.detail(run_id)
        except BaseException:
            archived.unlink(missing_ok=True)
            raise

    def _validate(self, entity, values):
        if not isinstance(values, dict) or not all(value is None or isinstance(value, str) for value in values.values()):
            raise ImportServiceError(_ui_tr('Importfelder müssen Textwerte enthalten.'))
        allowed = {field for field, _, _ in FIELDS[entity]}
        if set(values) - allowed:
            raise ImportServiceError(_ui_tr('Nicht unterstützte Importfelder.'))
        fields = {field: str(value).strip() for field, value in values.items() if value is not None and str(value).strip()}
        errors, resolved = [], {}
        if any(len(value) > 32768 for value in fields.values()):
            errors.append(_ui_tr('Ein Feld enthält mehr als 32.768 Zeichen.'))
        for field, caption, mandatory in FIELDS[entity]:
            if mandatory and not fields.get(field):
                errors.append(_ui_format('Pflichtwert fehlt: {0}.', _ui_tr(caption)))
        for field in ("email", "applicant_email"):
            if fields.get(field) and re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", fields[field]) is None:
                errors.append(_ui_tr('Ungültige E-Mail-Adresse.'))
        if fields.get("website"):
            website = fields["website"]
            if "://" not in website:
                website = "https://" + website
            try:
                parsed = urlsplit(website)
                valid = parsed.scheme in ("http", "https") and parsed.hostname and not re.search(r"\s", website)
            except ValueError:
                valid = False
            if not valid:
                errors.append(_ui_tr('Ungültige Website-Adresse.'))
            else:
                fields["website"] = website
        if fields.get("application_date"):
            value = fields["application_date"]
            try:
                if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
                    parsed_date = datetime.strptime(value, "%d.%m.%Y").date()
                elif "T" in value:
                    parsed_time = datetime.fromisoformat(value)
                    if parsed_time.time().isoformat() != "00:00:00":
                        raise ValueError("Non-midnight datetime")
                    parsed_date = parsed_time.date()
                else:
                    parsed_date = date.fromisoformat(value)
                fields["application_date"] = parsed_date.isoformat()
            except ValueError:
                errors.append(_ui_tr('Ungültiges Datum: JJJJ-MM-TT oder TT.MM.JJJJ verwenden.'))
        if entity == "applications":
            fields.setdefault("status_code", "draft")
            if self.db.execute("SELECT 1 FROM application_statuses WHERE code=?", (fields["status_code"],)).fetchone() is None:
                errors.append(_ui_tr('Unbekannter Statuscode.'))
            for field, table, column, target, caption in (
                ("company_name", "companies", "name", "company_id", "Unternehmen"),
                ("applicant_email", "applicant_profiles", "email", "applicant_profile_id", "Bewerberprofil"),
            ):
                if fields.get(field):
                    matches = self.db.execute(f"SELECT id FROM {table} WHERE deleted_at IS NULL AND ec_import_key({column})=?", (_key(fields[field]),)).fetchall()
                    if len(matches) != 1:
                        errors.append(_ui_format('{0} fehlt oder ist nicht eindeutig. Zuerst im Projekt anlegen.', _ui_tr(caption)))
                    else:
                        resolved[target] = matches[0]["id"]
        return fields, resolved, errors

    def _identity(self, entity, fields, resolved):
        if entity == "companies":
            return (entity, _key(fields.get("name")))
        if entity == "contacts":
            return (entity, "email", _key(fields["email"])) if fields.get("email") else (
                entity, "name", _key(fields.get("display_name")), _key(fields.get("phone")))
        return (entity, _key(fields.get("title")), resolved.get("company_id"), resolved.get("applicant_profile_id"))

    def _duplicates(self, entity, fields, resolved):
        if entity == 'data_rows':
            return []
        stamp = (self.db.execute("PRAGMA data_version").fetchone()[0], self.db.total_changes)
        if stamp != self._cache_stamp:
            self._duplicate_indexes = {}
            self._cache_stamp = stamp
        if entity not in self._duplicate_indexes:
            columns = {"companies": "id,name", "contacts": "id,display_name,email,phone",
                       "applications": "id,title,company_id,applicant_profile_id"}[entity]
            index = {}
            for row in self.db.execute(f"SELECT {columns} FROM {entity} WHERE deleted_at IS NULL"):
                data = dict(row)
                identity = self._identity(entity, data, data)
                index.setdefault(identity, []).append(data["id"])
                # Name/phone matching remains conservative when the imported contact has no email.
                if entity == "contacts" and data.get("email"):
                    index.setdefault((entity, "name", _key(data.get("display_name")), _key(data.get("phone"))), []).append(data["id"])
            self._duplicate_indexes[entity] = index
        return self._duplicate_indexes[entity].get(self._identity(entity, fields, resolved), [])

    def _remember_record(self, entity, fields, resolved, record_id):
        index = self._duplicate_indexes[entity]
        index.setdefault(self._identity(entity, fields, resolved), []).append(record_id)
        if entity == "contacts" and fields.get("email"):
            index.setdefault((entity, "name", _key(fields.get("display_name")), _key(fields.get("phone"))), []).append(record_id)
        self._cache_stamp = (self.db.execute("PRAGMA data_version").fetchone()[0], self.db.total_changes)

    def _run(self, run_id):
        row = self.db.execute("SELECT * FROM import_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ImportServiceError(_ui_tr('Importlauf nicht gefunden.'))
        run = dict(row)
        run["configuration"] = json.loads(run["configuration_json"])
        if run["configuration"].get("entity") not in FIELDS:
            raise ImportServiceError(_ui_tr('Dieser ältere Importlauf hat keine unterstützte Konfiguration.'))
        return run

    def detail(self, run_id):
        run = self._run(run_id)
        run["counts"] = {row["status"]: row["amount"] for row in self.db.execute(
            "SELECT status, COUNT(*) AS amount FROM import_rows WHERE import_run_id=? GROUP BY status", (run_id,))}
        return run

    def list_runs(self, offset=0, limit=25):
        if offset < 0 or not 1 <= limit <= 100:
            raise ImportServiceError(_ui_tr('Ungültige Listenseite.'))
        rows = [dict(row) for row in self.db.execute(
            "SELECT id,source_filename,status,total_rows,processed_rows,error_rows,created_at FROM import_runs ORDER BY created_at DESC,id LIMIT ? OFFSET ?", (limit, offset))]
        total = self.db.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0]
        return {"rows": rows, "total": total, "offset": offset, "limit": limit}

    def list_rows(self, run_id, offset=0, limit=50):
        if offset < 0 or not 1 <= limit <= 200:
            raise ImportServiceError(_ui_tr('Ungültige Listenseite.'))
        run = self.detail(run_id)
        rows = [dict(row) for row in self.db.execute(
            "SELECT * FROM import_rows WHERE import_run_id=? ORDER BY row_number LIMIT ? OFFSET ?", (run_id, limit, offset))]
        for row in rows:
            row["source_data"] = json.loads(row["source_data_json"])
            row["mapped_data"] = json.loads(row["mapped_data_json"])
            row["errors"] = json.loads(row["errors_json"])
        return {"run": run, "rows": rows, "offset": offset, "limit": limit, "total": run["total_rows"]}

    def _sync(self, run_id, finalize):
        run = self.detail(run_id)
        counts = run["counts"]
        processed = sum(counts.get(key, 0) for key in ("Imported", "Skipped", "Invalid", "Failed"))
        errors = counts.get("Invalid", 0) + counts.get("Failed", 0)
        pending = counts.get("Valid", 0) + counts.get("Pending", 0)
        status = "Pending"
        if finalize and not pending:
            status = "CompletedWithErrors" if errors or counts.get("DuplicateReview", 0) else "Completed"
        self.db.execute("UPDATE import_runs SET processed_rows=?,error_rows=?,status=?,finished_at=? WHERE id=?",
                        (processed, errors, status, utc_timestamp() if status.startswith("Completed") else None, run_id))

    def process(self, run_id: str, max_rows: int = 100, cancelled=lambda: False) -> dict:
        if not 1 <= max_rows <= 1000:
            raise ImportServiceError(_ui_tr('Ungültige Stapelgröße.'))
        run = self._run(run_id)
        entity = run["configuration"]["entity"]
        if entity == 'data_rows':
            return self.detail(run_id)  # Raw rows are already archived; never create domain records.
        with _transaction(self.db):
            self.db.execute("UPDATE import_runs SET status='Running',started_at=COALESCE(started_at,?),finished_at=NULL WHERE id=?", (utc_timestamp(), run_id))
        candidates = self.db.execute("SELECT id FROM import_rows WHERE import_run_id=? AND status='Valid' ORDER BY row_number LIMIT ?", (run_id, max_rows)).fetchall()
        paused = False
        for candidate in candidates:
            if cancelled():
                paused = True
                break
            try:
                with _transaction(self.db):
                    row = self.db.execute("SELECT * FROM import_rows WHERE id=?", (candidate["id"],)).fetchone()
                    if row["status"] != "Valid":
                        continue
                    mapped = json.loads(row["mapped_data_json"])
                    fields, resolved, errors = self._validate(entity, mapped["fields"])
                    if errors:
                        status = "Invalid"
                    elif self._duplicates(entity, fields, resolved) and not mapped.get("allow_duplicate", False):
                        status, errors = "DuplicateReview", ["Mögliches Duplikat im Projekt; seit der Vorschau neu erkannt."]
                    else:
                        if entity == "companies":
                            record = CompanyRepository(self.db).create(**fields)
                        elif entity == "contacts":
                            record = ContactRepository(self.db).create(**fields)
                        else:
                            record_fields = {key: value for key, value in fields.items() if key not in ("company_name", "applicant_email")}
                            record = ApplicationRepository(self.db).create_in_transaction(**record_fields, **resolved)
                        self.db.execute("UPDATE import_rows SET status='Imported',errors_json='[]',created_record_type=?,created_record_id=? WHERE id=?", (entity, record["id"], candidate["id"]))
                        self._remember_record(entity, fields, resolved, record["id"])
                        continue
                    self.db.execute("UPDATE import_rows SET status=?,errors_json=? WHERE id=?", (status, _json(errors), candidate["id"]))
            except Exception as error:
                self._cache_stamp = None
                # Domain creation rolled back with its receipt; retries cannot leave an unlogged record.
                with _transaction(self.db):
                    self.db.execute("UPDATE import_rows SET status='Failed',errors_json=? WHERE id=? AND status='Valid'", (_json([str(error)]), candidate["id"]))
        with _transaction(self.db):
            self._sync(run_id, finalize=True)
        result = self.detail(run_id)
        result["paused"] = paused
        return result

    def edit_row(self, row_id: str, fields: dict) -> dict:
        with _transaction(self.db):
            row = self._editable_row(row_id)
            run = self._run(row["import_run_id"])
            entity = run["configuration"]["entity"]
            if entity == 'data_rows':
                raise ImportServiceError('Raw data sources must be corrected in the source file and imported again.')
            normalized, resolved, errors = self._validate(entity, fields)
            status = "Invalid" if errors else "Valid"
            if not errors and self._duplicates(entity, normalized, resolved):
                status, errors = "DuplicateReview", ["Mögliches Duplikat im Projekt."]
            self.db.execute("UPDATE import_rows SET mapped_data_json=?,status=?,errors_json=? WHERE id=?",
                            (_json({"fields": normalized, "allow_duplicate": False}), status, _json(errors), row_id))
            self._sync(row["import_run_id"], finalize=False)
        return self.detail(row["import_run_id"])

    def review_row(self, row_id: str, decision: str) -> dict:
        if decision not in ("skip", "import_new"):
            raise ImportServiceError(_ui_tr('Ungültige Zeilenentscheidung.'))
        with _transaction(self.db):
            row = self._editable_row(row_id)
            mapped = json.loads(row["mapped_data_json"])
            if decision == "import_new" and row["status"] != "DuplicateReview":
                raise ImportServiceError(_ui_tr('Nur erkannte Duplikate können als neu freigegeben werden.'))
            mapped["allow_duplicate"] = decision == "import_new"
            self.db.execute("UPDATE import_rows SET status=?,mapped_data_json=?,errors_json=? WHERE id=?",
                            ("Valid" if decision == "import_new" else "Skipped", _json(mapped),
                             _json(["Duplikat ausdrücklich als neu freigegeben."] if decision == "import_new" else ["Vom Benutzer übersprungen."]), row_id))
            self._sync(row["import_run_id"], finalize=False)
        return self.detail(row["import_run_id"])

    def _editable_row(self, row_id):
        row = self.db.execute("SELECT * FROM import_rows WHERE id=?", (row_id,)).fetchone()
        if row is None or row["status"] in ("Imported", "Skipped"):
            raise ImportServiceError(_ui_tr('Diese Zeile ist bereits erledigt oder wurde nicht gefunden.'))
        return row
