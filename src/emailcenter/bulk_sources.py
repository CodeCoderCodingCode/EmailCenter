"""Shared row data for mail, document placeholders and later Word Replace workflows."""

from .language import translate as _ui_tr, format_text as _ui_format

import json
import re
import unicodedata

from .mail_models import MailError, address


SOURCE_FIELDS = {
    "contact.display_name": "Ansprechpartner", "contact.email": "E-Mail",
    "contact.salutation": "Anrede", "company.name": "Firmenname",
    "job.title": "Stelle", "application.cover_letter": "Anschreiben",
}
FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z")


def column_fields(headers):
    """Stable readable tokens for every source column, including German headers."""
    result = {}
    # Reserve literal valid identifiers before deriving aliases to prevent collisions.
    reserved = {h for h in headers if FIELD_NAME.fullmatch(h)}
    for header in headers:
        if header in reserved:
            name = header
        else:
            text = unicodedata.normalize('NFKD', header.replace('ß', 'ss')).encode('ascii', 'ignore').decode()
            base = re.sub(r'[^A-Za-z0-9_]+', '_', text).strip('_') or 'column'
            if base[0].isdigit():
                base = 'column_' + base
            name, number = base, 2
            while name in result or name in reserved:
                name = f'{base}_{number}'
                number += 1
        result[name] = header
    return result


def text_values(values):
    if (not isinstance(values, dict) or len(values) > 200 or
            any(not isinstance(k, str) or not k or len(k) > 200 or not isinstance(v, str) or len(v) > 32768 or "\x00" in v for k, v in values.items())):
        raise MailError(_ui_tr('Zeilenwerte müssen Text sein (maximal 32768 Zeichen je Feld).'))
    return values


class BulkSourceService:
    def __init__(self, connection):
        self.db = connection

    def runs(self):
        result = []
        for row in self.db.execute("SELECT id,source_filename,total_rows,status,created_at,configuration_json FROM import_runs ORDER BY created_at DESC,id"):
            value = dict(row)
            value["sheet"] = json.loads(value.pop("configuration_json")).get("options", {}).get("sheet")
            result.append(value)
        return result

    def _row(self, row_id):
        row = self.db.execute(
            "SELECT r.*,i.source_filename,i.configuration_json FROM import_rows r JOIN import_runs i ON i.id=r.import_run_id WHERE r.id=?", (row_id,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Importzeile nicht gefunden.'))
        row = dict(row)
        values = text_values(json.loads(row["source_data_json"]))
        # Corrections made in import review override their original source column.
        mapping = json.loads(row["configuration_json"]).get("mapping", {})
        fields = json.loads(row["mapped_data_json"]).get("fields", {})
        for field, column in mapping.items():
            if field in fields and column in values:
                values[column] = fields[field]
        return row, text_values(values)

    def rows(self, run_id, offset=0, limit=25):
        if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MailError(_ui_tr('Ungültige Listenseite.'))
        run = self.db.execute("SELECT id,source_filename FROM import_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise MailError(_ui_tr('Importlauf nicht gefunden.'))
        first = self.db.execute("SELECT id FROM import_rows WHERE import_run_id=? ORDER BY row_number LIMIT 1", (run_id,)).fetchone()
        headers = list(self._row(first[0])[1]) if first else []
        rows = []
        for record in self.db.execute("SELECT id FROM import_rows WHERE import_run_id=? ORDER BY row_number LIMIT ? OFFSET ?", (run_id, limit, offset)):
            row, values = self._row(record[0])
            rows.append({"id": row["id"], "number": row["row_number"], "status": row["status"], "values": values,
                         "eligible": row["status"] in ("Valid", "Imported"), "errors": json.loads(row['errors_json'])})
        total = self.db.execute("SELECT COUNT(*) FROM import_rows WHERE import_run_id=?", (run_id,)).fetchone()[0]
        return {"run": dict(run), "headers": headers, "rows": rows, "offset": offset, "limit": limit, "total": total}

    def resolve(self, source):
        if not isinstance(source, dict):
            raise MailError(_ui_tr('Ungültige Datenquelle.'))
        kind = source.get("kind")
        linked_contact = None
        if kind == "import" and {"kind", "row_id", "mapping"} <= set(source) and not set(source) - {"kind", "row_id", "mapping", "defaults", "empty_policy", "purpose"}:
            row, raw = self._row(source["row_id"])
            if row["status"] not in ("Valid", "Imported"):
                raise MailError(_ui_tr('Importzeile zuerst korrigieren bzw. Duplikatentscheidung im Datenimport treffen.'))
            mapping = source["mapping"]
            purpose = source.get("purpose", "mail")
            if not isinstance(mapping, dict) or len(mapping) > 100:
                raise MailError(_ui_tr('Ungültige Spaltenzuordnung.'))
            if purpose not in ('mail', 'documents'):
                raise MailError(_ui_tr('Ungültiger Datenquellenmodus.'))
            missing = [SOURCE_FIELDS[key] for key in ('contact.display_name', 'contact.email') if key not in mapping]
            if purpose == 'mail' and missing:
                raise MailError(_ui_format('Pflichtzuordnung fehlt: {0}. Bitte die passende Excel-Spalte auswählen.', ', '.join(_ui_tr(caption) for caption in missing)))
            for field, column in mapping.items():
                if not isinstance(field, str) or not FIELD_NAME.fullmatch(field):
                    raise MailError(_ui_format('Ungültiger Datenfeldname: {0}. Für Platzhalter den Spaltennamen mit Unterstrichen verwenden.', str(field)))
                if not isinstance(column, str) or column not in raw:
                    raise MailError(_ui_format('Quellspalte fehlt: {0}. Spaltenzuordnung für diesen Importlauf erneut prüfen.', str(column)))
            defaults = text_values(source.get("defaults", {}))
            policy = source.get("empty_policy", "fallback")
            if policy not in ("fallback", "keep") or any(not FIELD_NAME.fullmatch(key) for key in defaults):
                raise MailError(_ui_tr('Ungültige Standardwerte oder Leerwertregel.'))
            fields = {field: raw[column] for field, column in column_fields(list(raw)).items()}
            fields.update(defaults)
            fields.update({key: defaults.get(key, value) if not value.strip() and policy == "fallback" else value
                           for key, column in mapping.items() for value in [raw[column]]})
            if row["created_record_type"] == "contacts":
                linked_contact = row["created_record_id"]
            snapshot = {"kind": kind, "run_id": row["import_run_id"], "row_id": row["id"], "row_number": row["row_number"],
                        "filename": row["source_filename"], "sheet": json.loads(row["configuration_json"]).get("options", {}).get("sheet"),
                        "mapping": mapping, "raw_values": raw, "defaults": defaults, "empty_policy": policy}
            if purpose == "documents":
                snapshot["purpose"] = purpose
        elif kind == "manual" and set(source) == {"kind", "fields"}:
            fields = text_values(source["fields"])
            if any(not FIELD_NAME.fullmatch(k) for k in fields):
                raise MailError(_ui_tr('Ungültiger Feldname in der manuellen Liste.'))
            snapshot = {"kind": kind}
        elif kind == "list" and set(source) == {"kind", "list_id", "row_id"}:
            row = self.db.execute("SELECT r.*,l.name,l.updated_at FROM data_source_list_rows r JOIN data_source_lists l ON l.id=r.list_id WHERE r.id=? AND l.id=?",
                                  (source["row_id"], source["list_id"])).fetchone()
            if row is None:
                raise MailError(_ui_tr('Listenzeile wurde entfernt. Datenliste erneut laden.'))
            fields = text_values(json.loads(row["fields_json"]))
            snapshot = {"kind": kind, "list_id": row["list_id"], "list_name": row["name"], "row_id": row["id"],
                        "row_number": row["position"] + 1, "updated_at": row["updated_at"]}
        else:
            raise MailError(_ui_tr('Ungültige Datenquelle.'))
        return {"fields": fields, "contact_id": linked_contact, "snapshot": {**snapshot, "fields": fields}}

    def select(self, row_ids, mapping, defaults=None, empty_policy="fallback", require_mail_fields=True):
        if type(require_mail_fields) is not bool:
            raise MailError(_ui_tr('Ungültiger Datenquellenmodus.'))
        if not isinstance(row_ids, list) or not 1 <= len(row_ids) <= 100 or len(set(row_ids)) != len(row_ids):
            raise MailError(_ui_tr('1 bis 100 verschiedene Importzeilen auswählen.'))
        result = []
        for row_id in row_ids:
            source = {"kind": "import", "row_id": row_id, "mapping": mapping}
            if not require_mail_fields:
                source["purpose"] = "documents"
            if defaults is not None or empty_policy != "fallback":
                source.update(defaults=defaults or {}, empty_policy=empty_policy)
            resolved = self.resolve(source)
            fields = resolved["fields"]
            try:
                address(fields.get("contact.email", ""))
                error = ""
            except MailError as failure:
                error = str(failure)
            result.append({"id": "import:" + row_id, "display_name": fields.get("contact.display_name", ""),
                           "email": fields.get("contact.email", ""), "source": source, "source_values": fields,
                           "source_label": f"{resolved['snapshot']['filename']} · Zeile {resolved['snapshot']['row_number']}",
                           "source_order": (resolved["snapshot"]["run_id"], resolved["snapshot"]["row_number"]),
                           "error": error, "duplicate": False})
        return {"contacts": sorted(result, key=lambda contact: contact["source_order"])}

    def select_list(self, list_id, row_ids):
        if not isinstance(row_ids, list) or not 1 <= len(row_ids) <= 100 or len(set(row_ids)) != len(row_ids):
            raise MailError(_ui_tr('1 bis 100 verschiedene Listenzeilen auswählen.'))
        result = []
        for row_id in row_ids:
            source = {"kind": "list", "list_id": list_id, "row_id": row_id}
            resolved = self.resolve(source)
            fields, origin = resolved["fields"], resolved["snapshot"]
            try:
                address(fields.get("contact.email", ""))
                error = ""
            except MailError as failure:
                error = str(failure)
            result.append({"id": "list:" + row_id, "display_name": fields.get("contact.display_name", ""),
                           "email": fields.get("contact.email", ""), "source": source, "source_values": fields,
                           "source_label": f"{origin['list_name']} · Zeile {origin['row_number']}",
                           "source_order": origin["row_number"], "error": error, "duplicate": False})
        return {"contacts": sorted(result, key=lambda contact: contact["source_order"])}
