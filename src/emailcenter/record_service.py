"""Atomic editing and contact relationships for the desktop workspace."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json
import math
import re
from datetime import date, datetime

from .database.repositories import _atomic, _write_activity
from .database import utc_timestamp


RECORDS = {
    "companies": ("companies", "name", ("name", "website", "industry", "notes")),
    "contacts": ("contacts", "display_name", ("display_name", "first_name", "last_name", "email", "phone", "position", "notes")),
    "applicants": ("applicant_profiles", "display_name", ("display_name", "email", "phone")),
    "jobs": ("job_postings", "title", ("title", "company_id", "reference_number", "location", "source_url", "description", "employment_type", "deadline")),
    "applications": ("applications", "title", ("title", "company_id", "applicant_profile_id", "job_posting_id", "application_date", "next_follow_up_at", "source", "notes")),
}
for _entity, (_table, _title, _fields) in list(RECORDS.items()):
    RECORDS[_entity] = (_table, _title, (*_fields, 'custom_fields_json', *(('address_json',) if _entity in ('companies','contacts','applicants') else ()), *(('start_date',) if _entity == 'jobs' else ())))


def validate_structured(value, *, address=False):
    if value is None:
        value = '{}'
    if not isinstance(value, str) or len(value.encode('utf-8')) > 65536:
        raise ValueError(_ui_tr('Zusatzfelder/Adresse sind zu groß.'))
    try:
        data = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError):
        raise ValueError(_ui_tr('Adresse/Zusatzfelder müssen gültige Objekte sein.')) from None
    if not isinstance(data,dict) or len(data)>100 or any(not isinstance(k,str) or not re.fullmatch(r'[\w.-]{1,100}',k) for k in data):
        raise ValueError(_ui_tr('Höchstens 100 Zusatzfelder mit gültigen Namen verwenden.'))
    def check(item,depth=0):
        if depth>8:
            raise ValueError(_ui_tr('Zusatzfelder sind zu tief verschachtelt.'))
        if isinstance(item,str) and ('\x00' in item or len(item)>16000):
            raise ValueError(_ui_tr('Zusatzfeld ist zu lang oder ungültig.'))
        if isinstance(item,float) and not math.isfinite(item):
            raise ValueError(_ui_tr('Ungültige Zahl im Zusatzfeld.'))
        if isinstance(item,dict):
            for key, child in item.items():
                if not isinstance(key,str) or '\x00' in key:
                    raise ValueError(_ui_tr('Ungültiger Zusatzfeldname.'))
                check(child,depth+1)
        elif isinstance(item,list):
            for child in item:
                check(child,depth+1)
    check(data)
    if address and any(k in data and (not isinstance(data[k],str) or len(data[k])>300 or '\n' in data[k]) for k in ('street','postcode','city','country')):
        raise ValueError(_ui_tr('Adressfelder müssen einzeiliger Text bis 300 Zeichen sein.'))
    return json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class RecordService:
    def __init__(self, connection):
        self.connection = connection

    def get(self, entity, record_id):
        if entity not in RECORDS:
            raise ValueError(_ui_tr('Unbekannter Datensatztyp.'))
        table = RECORDS[entity][0]
        row = self.connection.execute(f"SELECT * FROM {table} WHERE id=? AND deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive WHERE entity_type=? AND entity_id={table}.id)", (record_id,entity)).fetchone()
        if row is None:
            raise ValueError(_ui_tr('Datensatz nicht gefunden. Bitte die Liste aktualisieren.'))
        return dict(row)

    def validate(self, entity, fields, *, current=None, creating=False):
        if entity not in RECORDS or not isinstance(fields, dict):
            raise ValueError(_ui_tr('Ungültige Datensatzanfrage.'))
        _, required, allowed = RECORDS[entity]
        extras = {"status_code"} if creating and entity == "applications" else set()
        if set(fields) - set(allowed) - extras:
            raise ValueError(_ui_tr('Nicht bearbeitbare Felder übergeben.'))
        result = dict(fields)
        if any(value is not None and not isinstance(value, str) for value in result.values()):
            raise ValueError(_ui_tr('Feldwerte müssen Text sein.'))
        merged = {**(current or {}), **result}
        if not (merged.get(required) or "").strip():
            raise ValueError(_ui_tr('Bitte einen Namen bzw. Titel eingeben.'))
        if required in result:
            result[required] = result[required].strip()
        for key in ('address_json','custom_fields_json'):
            if key in result:
                result[key] = validate_structured(result[key],address=key=='address_json')
        for key in ("application_date", "deadline", "start_date"):
            if result.get(key):
                try:
                    date.fromisoformat(result[key])
                except ValueError as error:
                    raise ValueError(_ui_tr('Datum bitte als JJJJ-MM-TT eingeben.')) from error
        if result.get("next_follow_up_at"):
            try:
                timestamp = datetime.fromisoformat(result["next_follow_up_at"].replace("Z", "+00:00"))
                if timestamp.utcoffset() is None:
                    raise ValueError()
            except ValueError as error:
                raise ValueError(_ui_tr('Nachfassen benötigt Datum, Uhrzeit und Zeitzone, z. B. 2026-10-20T09:00:00+02:00.')) from error
        if entity in ("applications", "jobs"):
            references = (("company_id", "companies"),)
            if entity == "applications":
                references += (("applicant_profile_id", "applicants"), ("job_posting_id", "jobs"))
            for key, target in references:
                identifier = merged.get(key)
                # Existing archived references may be retained, but never newly assigned.
                if identifier and (creating or not current or identifier != current.get(key)):
                    self.get(target, identifier)
            job_id = merged.get("job_posting_id") if entity == "applications" else None
            if job_id:
                row = self.connection.execute("SELECT company_id FROM job_postings WHERE id=?", (job_id,)).fetchone()
                if row is None:
                    raise ValueError(_ui_tr('Stelle nicht gefunden.'))
                if creating or not current or job_id != current.get("job_posting_id"):
                    self.get("companies", row[0])
                if merged.get("company_id") and merged["company_id"] != row[0]:
                    raise ValueError(_ui_tr('Bewerbung und Stelle müssen zum selben Unternehmen gehören.'))
                result["company_id"] = row[0]
            if entity == "jobs":
                if not merged.get("company_id"):
                    raise ValueError(_ui_tr('Bitte ein Unternehmen für die Stelle auswählen.'))
                if current and merged["company_id"] != current["company_id"]:
                    linked = self.connection.execute("SELECT 1 FROM applications WHERE job_posting_id=? LIMIT 1", (current["id"],)).fetchone()
                    if linked:
                        raise ValueError(_ui_tr('Diese Stelle wird von Bewerbungen verwendet. Zuerst deren Stellenzuordnung lösen.'))
        return result

    def update(self, entity, record_id, fields, expected_version):
        with _atomic(self.connection):
            current = self.get(entity, record_id)
            if fingerprint(current) != expected_version:
                raise ValueError(_ui_tr('Datensatz wurde zwischenzeitlich geändert. Dialog schließen und erneut öffnen.'))
            values = self.validate(entity, fields, current=current)
            changed = {key: value for key, value in values.items() if current[key] != value}
            if changed:
                table = RECORDS[entity][0]
                now = utc_timestamp()
                self.connection.execute(f"UPDATE {table} SET " + ", ".join(f"{key}=?" for key in changed) + ", updated_at=? WHERE id=?",
                                        (*changed.values(), now, record_id))
                _write_activity(self.connection, "record.updated", table, record_id,
                                "Datensatz bearbeitet.", {"fields": sorted(changed)}, now)
            return self.get(entity, record_id)

    def _relationship(self, entity, record_id):
        if entity not in ("companies", "applications"):
            raise ValueError(_ui_tr('Kontakte können Unternehmen oder Bewerbungen zugeordnet werden.'))
        self.get(entity, record_id)
        return ("company_contacts", "company_id") if entity == "companies" else ("application_contacts", "application_id")

    def links(self, entity, record_id):
        table, key = self._relationship(entity, record_id)
        raw = [dict(row) for row in self.connection.execute(f"SELECT * FROM {table} WHERE {key}=? ORDER BY contact_id", (record_id,))]
        rows = [dict(row) for row in self.connection.execute(
            f"SELECT c.id, c.display_name, c.email, c.deleted_at, r.relationship_type" +
            (", r.is_primary" if entity == "companies" else "") +
            f" FROM {table} r JOIN contacts c ON c.id=r.contact_id WHERE r.{key}=? ORDER BY c.display_name COLLATE NOCASE, c.id", (record_id,))]
        choices = [dict(row) for row in self.connection.execute("SELECT id,display_name FROM contacts WHERE deleted_at IS NULL ORDER BY display_name COLLATE NOCASE, id")]
        return {"entity": entity, "record_id": record_id, "rows": rows, "choices": choices, "version": fingerprint(raw)}

    def save_link(self, entity, record_id, contact_id, relationship_type=None, is_primary=False, *, expected_version, remove=False):
        if not isinstance(is_primary, bool) or not isinstance(remove, bool) or (relationship_type is not None and not isinstance(relationship_type, str)):
            raise ValueError(_ui_tr('Ungültige Kontaktzuordnung.'))
        with _atomic(self.connection):
            table, key = self._relationship(entity, record_id)
            if self.links(entity, record_id)["version"] != expected_version:
                raise ValueError(_ui_tr('Kontaktzuordnungen wurden geändert. Bitte aktualisieren und erneut bearbeiten.'))
            if remove:
                cursor = self.connection.execute(f"DELETE FROM {table} WHERE {key}=? AND contact_id=?", (record_id, contact_id))
                if not cursor.rowcount:
                    raise ValueError(_ui_tr('Kontaktzuordnung nicht gefunden.'))
            else:
                self.get("contacts", contact_id)
                if entity == "companies":
                    if is_primary:
                        self.connection.execute("UPDATE company_contacts SET is_primary=0 WHERE company_id=?", (record_id,))
                    self.connection.execute("INSERT INTO company_contacts(company_id,contact_id,relationship_type,is_primary,created_at) VALUES(?,?,?,?,?) "
                                            "ON CONFLICT(company_id,contact_id) DO UPDATE SET relationship_type=excluded.relationship_type,is_primary=excluded.is_primary",
                                            (record_id, contact_id, relationship_type, int(is_primary), utc_timestamp()))
                else:
                    self.connection.execute("INSERT INTO application_contacts(application_id,contact_id,relationship_type,created_at) VALUES(?,?,?,?) "
                                            "ON CONFLICT(application_id,contact_id) DO UPDATE SET relationship_type=excluded.relationship_type",
                                            (record_id, contact_id, relationship_type, utc_timestamp()))
            _write_activity(self.connection, "contact.unlinked" if remove else "contact.linked", RECORDS[entity][0], record_id,
                            "Kontaktzuordnung geändert.", {"contact_id": contact_id}, utc_timestamp())
            return self.links(entity, record_id)
