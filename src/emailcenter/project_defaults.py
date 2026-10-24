"""Project-owned defaults, applied only to new work, with revision checks."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json

from .mail_models import address
from .mail_service import _json, _transaction
from .database import utc_timestamp
from .database.repositories import _write_activity


DEFAULTS = {"document_version_id": None, "applicant_profile_id": None,
            "account_email": "", "source_list_id": None, "body_format": "plain"}


def validate_defaults(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError(_ui_tr('Ungültige Projektvorgaben.'))
    result = {**DEFAULTS, **values}
    for key in ("document_version_id", "applicant_profile_id", "source_list_id"):
        if result[key] is not None and (not isinstance(result[key], str) or not 1 <= len(result[key]) <= 100):
            raise ValueError(_ui_format('Ungültige Projektzuordnung: {0}', key))
    result["account_email"] = address(result["account_email"]) if result["account_email"] else ""
    if result["body_format"] not in ("plain", "html"):
        raise ValueError(_ui_tr('Nachrichtenformat muss Text oder HTML sein.'))
    return result


class ProjectDefaultsService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def details(self):
        metadata = dict(self.db.execute("SELECT key,value FROM project_metadata"))
        values = validate_defaults(json.loads(metadata.get("project_defaults", "{}")))
        # Deleted records remain historical; they are no longer suggested for new work.
        for key, query in (
            ("applicant_profile_id", "SELECT 1 FROM applicant_profiles WHERE id=? AND deleted_at IS NULL"),
            ("document_version_id", "SELECT 1 FROM template_versions v JOIN templates t ON t.id=v.template_id WHERE v.id=? AND t.deleted_at IS NULL AND t.template_type='document'"),
            ("source_list_id", "SELECT 1 FROM data_source_lists WHERE id=?"),
        ):
            if values[key] and not self.db.execute(query, (values[key],)).fetchone():
                values[key] = None
        value = {"goal": metadata.get("project_goal", ""), "mode": metadata.get("workspace_mode", "applications"),
                 "defaults": values}
        value["version"] = hashlib.sha256(_json(metadata).encode()).hexdigest()
        value["account_id"] = next((row[0] for row in self.db.execute(
            "SELECT id FROM email_provider_accounts WHERE account_email=? COLLATE NOCASE AND is_enabled=1 AND deleted_at IS NULL",
            (values["account_email"],))), None)
        return value

    def save(self, goal, mode, defaults, expected_version):
        if not isinstance(goal, str) or len(goal) > 4000 or "\x00" in goal or mode not in ("applications", "mail"):
            raise ValueError(_ui_tr('Projektziel (maximal 4000 Zeichen) und Arbeitsmodus prüfen.'))
        defaults = validate_defaults(defaults)
        with _transaction(self.db):
            if self.details()["version"] != expected_version:
                raise ValueError(_ui_tr('Projektvorgaben wurden geändert. Bitte neu laden.'))
            for key, query in (
                ("applicant_profile_id", "SELECT 1 FROM applicant_profiles WHERE id=? AND deleted_at IS NULL"),
                ("document_version_id", "SELECT 1 FROM template_versions v JOIN templates t ON t.id=v.template_id WHERE v.id=? AND t.deleted_at IS NULL AND t.template_type='document'"),
                ("source_list_id", "SELECT 1 FROM data_source_lists WHERE id=?"),
            ):
                if defaults[key] and not self.db.execute(query, (defaults[key],)).fetchone():
                    raise ValueError(_ui_tr('Gewählte Projektvorgabe ist nicht mehr verfügbar.'))
            self.db.executemany("INSERT INTO project_metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                (("project_goal", goal.strip()), ("workspace_mode", mode), ("project_defaults", _json(defaults))))
            _write_activity(self.db, "project.defaults_saved", "project", self.project.project_id,
                            "Projektziel und Vorgaben gespeichert.", {}, utc_timestamp())
        return self.details()

    def choices(self):
        from .data_source_library import DataSourceLibrary
        result = {"settings": self.details(),
                "profiles": [dict(row) for row in self.db.execute("SELECT * FROM applicant_profiles WHERE deleted_at IS NULL ORDER BY display_name")],
                "templates": [dict(row) for row in self.db.execute("SELECT v.id,v.file_path,v.content_hash,v.configuration_json,v.placeholders_json,t.name,v.version_number FROM template_versions v JOIN templates t ON t.id=v.template_id WHERE t.deleted_at IS NULL AND t.template_type='document' ORDER BY t.name,v.version_number DESC")],
                "accounts": [dict(row) for row in self.db.execute("SELECT id,account_email FROM email_provider_accounts WHERE deleted_at IS NULL AND is_enabled=1 ORDER BY account_email")],
                "lists": [DataSourceLibrary(self.db).list(row["id"]) for row in DataSourceLibrary(self.db).lists()]}
        for item in result["templates"]:
            item["source_path"] = str(self.project.file_path(item["file_path"]))
        return result
