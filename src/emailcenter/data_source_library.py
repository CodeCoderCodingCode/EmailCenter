"""Project-owned mappings and editable lists shared by mail and document workflows."""

from .language import translate as _ui_tr, format_text as _ui_format

import json
import hashlib
from uuid import UUID, uuid4

from .bulk_sources import FIELD_NAME, text_values
from .database.repositories import _write_activity
from .mail_models import MailError, header
from .mail_service import _json, _transaction
from .database import utc_timestamp


def digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def validate_defaults(values):
    values = text_values(values)
    if any(not FIELD_NAME.fullmatch(key) for key in values):
        raise MailError(_ui_tr('Ungültiger Datenfeldname.'))
    return values


def validate_mapping(mapping):
    if not isinstance(mapping, dict) or len(mapping) > 100 or any(
            not isinstance(key, str) or not FIELD_NAME.fullmatch(key) or not isinstance(value, str) or
            not value or len(value) > 200 or "\x00" in value for key, value in mapping.items()):
        raise MailError(_ui_tr('Ungültige Spaltenzuordnung.'))
    return mapping


class DataSourceLibrary:
    def __init__(self, connection):
        self.db = connection

    def profiles(self):
        return [self.profile(row[0]) for row in self.db.execute("SELECT id FROM data_source_profiles ORDER BY name COLLATE NOCASE,id")]

    def profile(self, profile_id):
        row = self.db.execute("SELECT * FROM data_source_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Zuordnungsprofil nicht gefunden.'))
        value = dict(row)
        value["mapping"] = json.loads(value.pop("mapping_json"))
        value["defaults"] = json.loads(value.pop("defaults_json"))
        return {**value, "version": digest(value)}

    def save_profile(self, name, mapping, defaults=None, empty_policy="fallback", profile_id=None, expected_version=None):
        name, mapping = header(name, _ui_tr('Profilname')), validate_mapping(mapping)
        defaults = validate_defaults(defaults or {})
        if empty_policy not in ("fallback", "keep"):
            raise MailError(_ui_tr('Ungültige Leerwertregel.'))
        identifier, now = profile_id or str(uuid4()), utc_timestamp()
        with _transaction(self.db):
            if profile_id and self.profile(profile_id)["version"] != expected_version:
                raise MailError(_ui_tr('Profil wurde geändert. Neu laden und erneut bearbeiten.'))
            same = self.db.execute("SELECT id FROM data_source_profiles WHERE name=? COLLATE NOCASE AND id<>?", (name, identifier)).fetchone()
            if same:
                raise MailError(_ui_tr('Ein Profil mit diesem Namen existiert bereits.'))
            if profile_id:
                self.db.execute("UPDATE data_source_profiles SET name=?,mapping_json=?,defaults_json=?,empty_policy=?,updated_at=? WHERE id=?",
                                (name, _json(mapping), _json(defaults), empty_policy, now, identifier))
            else:
                self.db.execute("INSERT INTO data_source_profiles VALUES(?,?,?,?,?,?,?)", (identifier, name, _json(mapping), _json(defaults), empty_policy, now, now))
            _write_activity(self.db, "data_source.profile_saved", "data_source_profiles", identifier, "Zuordnungsprofil gespeichert.", {}, now)
        return {"profile": self.profile(identifier), "profiles": self.profiles()}

    def lists(self):
        return [dict(row) for row in self.db.execute(
            "SELECT l.*,COUNT(r.id) AS count FROM data_source_lists l LEFT JOIN data_source_list_rows r ON r.list_id=l.id GROUP BY l.id ORDER BY l.name COLLATE NOCASE,l.id")]

    def list(self, list_id):
        row = self.db.execute("SELECT * FROM data_source_lists WHERE id=?", (list_id,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Datenliste nicht gefunden.'))
        rows = [{"id": r["id"], "fields": json.loads(r["fields_json"])} for r in self.db.execute(
            "SELECT * FROM data_source_list_rows WHERE list_id=? ORDER BY position,id", (list_id,))]
        value = {**dict(row), "rows": rows}
        return {**value, "version": digest(value)}

    def save_list(self, name, rows, list_id=None, expected_version=None):
        name = header(name, _ui_tr('Listenname'))
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise MailError(_ui_tr('Eine Datenliste benötigt 1 bis 100 Zeilen.'))
        entries, ids = [], set()
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"id", "fields"} or "fields" not in row:
                raise MailError(_ui_tr('Ungültige Listenzeile.'))
            identifier = row.get("id") or str(uuid4())
            try:
                UUID(identifier)
            except (ValueError, TypeError, AttributeError):
                raise MailError(_ui_tr('Ungültige Zeilenkennung.')) from None
            if identifier in ids:
                raise MailError(_ui_tr('Jede Listenzeile nur einmal speichern.'))
            fields = validate_defaults(row["fields"])
            if not any(value.strip() for value in fields.values()):
                raise MailError(_ui_tr('Leere Zeilen vor dem Speichern entfernen.'))
            entries.append((identifier, fields))
            ids.add(identifier)
        identifier, now = list_id or str(uuid4()), utc_timestamp()
        with _transaction(self.db):
            if list_id and self.list(list_id)["version"] != expected_version:
                raise MailError(_ui_tr('Liste wurde geändert. Neu laden und erneut bearbeiten.'))
            if self.db.execute("SELECT 1 FROM data_source_lists WHERE name=? COLLATE NOCASE AND id<>?", (name, identifier)).fetchone():
                raise MailError(_ui_tr('Eine Liste mit diesem Namen existiert bereits.'))
            if any(self.db.execute("SELECT 1 FROM data_source_list_rows WHERE id=? AND list_id<>?", (key, identifier)).fetchone() for key, _ in entries):
                raise MailError(_ui_tr('Zeile gehört zu einer anderen Liste. Als neue Kopie speichern.'))
            if list_id:
                self.db.execute("UPDATE data_source_lists SET name=?,updated_at=? WHERE id=?", (name, now, identifier))
                self.db.execute("DELETE FROM data_source_list_rows WHERE list_id=?", (identifier,))
            else:
                self.db.execute("INSERT INTO data_source_lists VALUES(?,?,?,?)", (identifier, name, now, now))
            for position, (key, fields) in enumerate(entries):
                self.db.execute("INSERT INTO data_source_list_rows VALUES(?,?,?,?)", (key, identifier, position, _json(fields)))
            _write_activity(self.db, "data_source.list_saved", "data_source_lists", identifier, "Wiederverwendbare Datenliste gespeichert.", {"count": len(entries)}, now)
        return {"list": self.list(identifier), "lists": self.lists()}
