"""Versioned mail templates and literal, non-recursive placeholder rendering."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import html
import json
import re
from uuid import uuid4

from .database import utc_timestamp
from .database.repositories import _atomic, _write_activity
from .mail_context import compose_context
from .mail_models import header
from .record_service import RecordService


FIELDS = (
    "application.title", "application.application_date", "company.name", "company.website",
    "applicant.display_name", "applicant.email", "applicant.phone", "job.title",
    "job.reference_number", "job.location", "contact.display_name", "contact.email",
)
TOKEN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)\s*\}\}")


def placeholders(subject, body):
    names = sorted(set(TOKEN.findall(subject) + TOKEN.findall(body)))
    rest = TOKEN.sub("", subject + body)
    if "{{" in rest or "}}" in rest or len(names) > 50:
        raise ValueError(_ui_tr('Platzhalter als {{NAME}} oder {{company.name}} angeben; maximal 50 verschiedene Werte.'))
    return names


def _payload(subject, body, body_format):
    header(subject, _ui_tr('Betreff'))
    if not isinstance(body, str) or not body.strip() or len(body) > 100000 or "\x00" in body:
        raise ValueError(_ui_tr('Vorlagentext fehlt oder ist zu lang (maximal 100000 Zeichen).'))
    if body_format not in ("plain", "html"):
        raise ValueError(_ui_tr('Ungültiges Nachrichtenformat.'))
    return {"subject": subject, "body": body, "body_format": body_format}


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class MailTemplateService:
    def __init__(self, connection):
        self.db = connection

    def choices(self):
        return [dict(row) for row in self.db.execute(
            "SELECT v.id,v.template_id,v.version_number,t.name AS template_name "
            "FROM templates t JOIN template_versions v ON v.template_id=t.id "
            "WHERE t.template_type='email' AND t.deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='templates' AND r.entity_id=t.id) "
            "ORDER BY t.name COLLATE NOCASE,v.version_number DESC,t.id")]

    def list(self, *, search="", offset=0, limit=25):
        if not isinstance(search, str) or not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError(_ui_tr('Ungültige Vorlagenanfrage.'))
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condition = "t.template_type='email' AND t.deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='templates' AND r.entity_id=t.id) AND t.name LIKE ? ESCAPE '\\'"
        total = self.db.execute(f"SELECT COUNT(*) FROM templates t WHERE {condition}", (f"%{escaped}%",)).fetchone()[0]
        rows = [dict(row) for row in self.db.execute(
            "SELECT t.id,t.name,v.id AS version_id,v.version_number FROM templates t "
            "JOIN template_versions v ON v.template_id=t.id AND v.version_number="
            "(SELECT MAX(version_number) FROM template_versions WHERE template_id=t.id) "
            f"WHERE {condition} ORDER BY t.name COLLATE NOCASE,t.id LIMIT ? OFFSET ?",
            (f"%{escaped}%", limit, offset))]
        return {"rows": rows, "total": total, "offset": offset, "limit": limit, "choices": self.choices()}

    def version(self, version_id):
        row = self.db.execute(
            "SELECT v.*,t.name AS template_name FROM template_versions v JOIN templates t ON t.id=v.template_id "
            "WHERE v.id=? AND t.template_type='email' AND t.deleted_at IS NULL", (version_id,)).fetchone()
        if row is None:
            raise ValueError(_ui_tr('E-Mail-Vorlagenversion nicht gefunden.'))
        value = dict(row)
        try:
            config = json.loads(value["configuration_json"])
            payload = _payload(config["subject"], value["content_text"], config["body_format"])
            names = placeholders(payload["subject"], payload["body"])
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(_ui_tr('Die gespeicherte E-Mail-Vorlage ist ungültig.')) from error
        if _hash(payload) != value["content_hash"] or names != json.loads(value["placeholders_json"]):
            raise ValueError(_ui_tr('Die gespeicherte E-Mail-Vorlagenversion wurde verändert.'))
        return {"id": value["id"], "template_id": value["template_id"], "name": value["template_name"],
                "version_number": value["version_number"], "placeholders": names, **payload}

    def details(self, template_id):
        versions = [self.version(row[0]) for row in self.db.execute(
            "SELECT id FROM template_versions WHERE template_id=? ORDER BY version_number DESC", (template_id,))]
        if not versions:
            raise ValueError(_ui_tr('E-Mail-Vorlage nicht gefunden.'))
        return {"versions": versions, "latest_version_id": versions[0]["id"]}

    def save(self, *, name, subject, body, body_format="plain", template_id=None, base_version_id=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 200 or any(c in name for c in "\r\n\x00"):
            raise ValueError(_ui_tr('Bitte einen Vorlagennamen angeben (maximal 200 Zeichen).'))
        payload = _payload(subject, body, body_format)
        names = placeholders(subject, body)
        identifier, version_id, now = template_id or str(uuid4()), str(uuid4()), utc_timestamp()
        with _atomic(self.db):
            if template_id:
                details = self.details(template_id)
                if details["latest_version_id"] != base_version_id:
                    raise ValueError(_ui_tr('Die Vorlage wurde geändert. Versionen neu laden und Änderungen prüfen.'))
                number = details["versions"][0]["version_number"] + 1
                self.db.execute("UPDATE templates SET name=?,updated_at=? WHERE id=?", (name.strip(), now, identifier))
            else:
                number = 1
                self.db.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at) VALUES (?,?,'email',?,?)",
                                (identifier, name.strip(), now, now))
            self.db.execute(
                "INSERT INTO template_versions(id,template_id,version_number,content_text,placeholders_json,configuration_json,content_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (version_id, identifier, number, body, json.dumps(names),
                json.dumps({"subject": subject, "body_format": body_format}, ensure_ascii=False), _hash(payload), now))
            _write_activity(self.db, "email_template.saved", "templates", identifier,
                            "E-Mail-Vorlagenversion gespeichert.", {"version_id": version_id, "version_number": number}, now)
        return self.version(version_id)

    def duplicate(self, version_id):
        value = self.version(version_id)
        return self.save(name=value["name"][:192] + " (Kopie)", subject=value["subject"],
                         body=value["body"], body_format=value["body_format"])

    def context_values(self, *, application_id=None, contact_id=None):
        """Resolve the same domain fields for mail and document personalization."""
        context = {}
        records = RecordService(self.db)
        if application_id:
            application = records.get("applications", application_id)
            context["application"] = application
            for group, table, identifier in (
                ("company", "companies", application["company_id"]),
                ("applicant", "applicant_profiles", application["applicant_profile_id"]),
                ("job", "job_postings", application["job_posting_id"]),
            ):
                row = self.db.execute(f"SELECT * FROM {table} WHERE id=? AND deleted_at IS NULL", (identifier,)).fetchone()
                if row:
                    context[group] = dict(row)
        if contact_id:
            if application_id:
                compose_context(self.db, application_id=application_id, contact_id=contact_id)
            context["contact"] = records.get("contacts", contact_id)
        effective = {}
        for name in FIELDS:
            group, field = name.split(".")
            value = context.get(group, {}).get(field)
            if value is not None:
                effective[name] = str(value)
        return effective

    def render(self, version_id, *, application_id=None, contact_id=None, values=None):
        version = self.version(version_id)
        resolved = self.context_values(application_id=application_id, contact_id=contact_id)
        effective = {key: value for key, value in resolved.items() if key in version["placeholders"]}
        values = {} if values is None else values
        if not isinstance(values, dict) or set(values) - set(version["placeholders"]):
            raise ValueError(_ui_tr('Unbekannte Platzhalterwerte.'))
        if any(not isinstance(value, str) or len(value) > 10000 or "\x00" in value for value in values.values()):
            raise ValueError(_ui_tr('Platzhalterwerte müssen Text sein (maximal 10000 Zeichen).'))
        effective.update(values)
        missing = [name for name in version["placeholders"] if not effective.get(name, "").strip()]
        def substitute(text, *, escape=False):
            def replacement(match):
                key = match.group(1)
                if key in missing:
                    return match.group(0)
                value = effective[key]
                return html.escape(value, quote=True) if escape else value
            return TOKEN.sub(replacement, text)
        subject = substitute(version["subject"])
        body = substitute(version["body"], escape=version["body_format"] == "html")
        header(subject, _ui_tr('Betreff'))
        if len(body) > 1000000:
            raise ValueError(_ui_tr('Die ausgefüllte Nachricht ist zu lang.'))
        return {"version_id": version_id, "name": version["name"], "version_number": version["version_number"],
                "subject": subject, "body": body, "body_format": version["body_format"],
                "values": effective, "placeholders": version["placeholders"], "missing": missing}
