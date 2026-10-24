"""Explicit contact collections and reusable filters; no arbitrary query execution."""

from .language import translate as _ui_tr, format_text as _ui_format

import json
from uuid import uuid4
from .database import utc_timestamp
from .mail_models import MailError, address, header
from .mail_service import _transaction, _json


class RecipientLibrary:
    def __init__(self, db):
        self.db = db

    def details(self):
        groups = []
        for row in self.db.execute("SELECT * FROM recipient_groups ORDER BY name"):
            groups.append({**dict(row), "contact_ids": [r[0] for r in self.db.execute(
                "SELECT m.contact_id FROM recipient_group_members m JOIN contacts c ON c.id=m.contact_id WHERE m.group_id=? AND c.deleted_at IS NULL ORDER BY m.contact_id", (row["id"],))]})
        filters = [{**dict(row), "configuration": json.loads(row["configuration_json"])} for row in self.db.execute("SELECT * FROM recipient_filters ORDER BY name")]
        return {"recipient_groups": groups, "recipient_filters": filters}

    def save(self, kind, name, contact_ids=None, configuration=None):
        name = header(name, _ui_tr('Name'))
        identifier = str(uuid4())
        with _transaction(self.db):
            if kind == "group":
                if not isinstance(contact_ids, list) or not 1 <= len(contact_ids) <= 1000 or len(set(contact_ids)) != len(contact_ids):
                    raise MailError(_ui_tr('1 bis 1000 unterschiedliche Projektkontakte auswählen.'))
                if any(not self.db.execute("SELECT 1 FROM contacts WHERE id=? AND deleted_at IS NULL", (c,)).fetchone() for c in contact_ids):
                    raise MailError(_ui_tr('Kontaktgruppen enthalten ausschließlich vorhandene Projektkontakte.'))
                self.db.execute("INSERT INTO recipient_groups VALUES(?,?,?)", (identifier, name, utc_timestamp()))
                self.db.executemany("INSERT INTO recipient_group_members VALUES(?,?)", ((identifier, c) for c in contact_ids))
            elif kind == "filter":
                value = self.validate(configuration)
                self.db.execute("INSERT INTO recipient_filters VALUES(?,?,?,?)", (identifier, name, _json(value), utc_timestamp()))
            else:
                raise MailError(_ui_tr('Unbekannte Empfängersammlung.'))
        return self.details()

    def delete(self, kind, identifier):
        table = {"group": "recipient_groups", "filter": "recipient_filters"}.get(kind)
        if not table:
            raise MailError(_ui_tr('Unbekannte Empfängersammlung.'))
        self.db.execute(f"DELETE FROM {table} WHERE id=?", (identifier,))
        return self.details()

    def validate(self, value):
        if not isinstance(value, dict) or set(value) - {"search", "group_id", "valid_only"}:
            raise MailError(_ui_tr('Ungültiger Empfängerfilter.'))
        result = {"search": "", "group_id": None, "valid_only": False, **value}
        if not isinstance(result["search"], str) or len(result["search"]) > 200 or type(result["valid_only"]) is not bool:
            raise MailError(_ui_tr('Empfängerfilter prüfen.'))
        if result["group_id"] and not self.db.execute("SELECT 1 FROM recipient_groups WHERE id=?", (result["group_id"],)).fetchone():
            raise MailError(_ui_tr('Kontaktgruppe ist nicht mehr verfügbar.'))
        return result
