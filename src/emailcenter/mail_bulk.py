"""Read-only bulk previews and atomic groups of local, personalized drafts."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import html
import json
import re
from pathlib import Path
from uuid import uuid4

from .database.repositories import _write_activity
from .mail_context import compose_context
from .mail_models import MailError, address, header
from .mail_service import MailService, _json, _transaction
from .mail_templates import MailTemplateService
from .bulk_sources import BulkSourceService, SOURCE_FIELDS, text_values
from .document_service import DocumentService, DocumentServiceError, find_libreoffice
from .documents import DocumentError, extract_docx_text
from .data_source_library import DataSourceLibrary
from .project_defaults import ProjectDefaultsService
from .recipient_library import RecipientLibrary


def digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class BulkMailService:
    def __init__(self, project):
        self.project, self.db = project, project.connection
        self.mail = MailService(project)
        self.templates = MailTemplateService(self.db)
        self.sources = BulkSourceService(self.db)
        self.documents = DocumentService(project)

    def details(self):
        contacts = []
        for row in self.db.execute("SELECT id,display_name,email FROM contacts WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='contacts' AND r.entity_id=contacts.id) ORDER BY display_name COLLATE NOCASE,id"):
            value = dict(row)
            try:
                value["normalized_email"] = address(value["email"])
                value["error"] = ""
            except MailError as error:
                value["normalized_email"], value["error"] = "", str(error)
            contacts.append(value)
        groups = {}
        for contact in contacts:
            if contact["normalized_email"]:
                groups.setdefault(contact["normalized_email"].casefold(), []).append(contact)
        for group in groups.values():
            for contact in group:
                contact["duplicate"] = len(group) > 1
        return {**RecipientLibrary(self.db).details(), "project_settings": ProjectDefaultsService(self.project).details(),
                "contacts": contacts, "templates": [self.templates.version(v["id"]) for v in self.templates.choices()],
                "accounts": [dict(r) for r in self.db.execute("SELECT id,account_email FROM email_provider_accounts WHERE deleted_at IS NULL AND is_enabled=1")],
                "signatures": [dict(r) for r in self.db.execute("SELECT id,name FROM email_signatures WHERE deleted_at IS NULL ORDER BY name")],
                "applications": [dict(r) for r in self.db.execute("SELECT id,title FROM applications WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='applications' AND r.entity_id=applications.id) ORDER BY title")],
                "batches": self.batches(), "source_runs": self.sources.runs(),
                "source_profiles": DataSourceLibrary(self.db).profiles(), "source_lists": DataSourceLibrary(self.db).lists(),
                "document_templates": [self.document_version(r[0]) for r in self.db.execute(
                    "SELECT v.id FROM template_versions v JOIN templates t ON t.id=v.template_id WHERE t.template_type='document' AND t.deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='templates' AND r.entity_id=t.id) ORDER BY t.name,v.version_number DESC")]}

    def document_version(self, version_id):
        version = self.documents.templates.get_version(version_id)
        active = version and self.db.execute("SELECT 1 FROM templates WHERE id=? AND deleted_at IS NULL", (version["template_id"],)).fetchone()
        if not active or version["template_type"] != "document":
            raise MailError(_ui_tr('DOCX-Vorlagenversion nicht gefunden.'))
        configuration = json.loads(version["configuration_json"])
        return {"id": version_id, "name": version["template_name"], "version_number": version["version_number"],
                "placeholders": json.loads(version["placeholders_json"]), **configuration}

    def context(self, contact_id, application_id=None, source=None):
        linked = self.sources.resolve(source)["contact_id"] if source else contact_id
        result = compose_context(self.db, contact_id=linked, application_id=application_id)
        return {**result, "selected_contact_id": contact_id}

    def batches(self):
        return [dict(r) for r in self.db.execute(
            "SELECT b.*,COUNT(i.draft_id) AS count FROM email_draft_batches b JOIN email_draft_batch_items i ON i.batch_id=b.id "
            "GROUP BY b.id ORDER BY b.created_at DESC,b.id")]

    def batch(self, batch_id):
        batch = self.db.execute("SELECT * FROM email_draft_batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise MailError(_ui_tr('Entwurfsgruppe nicht gefunden.'))
        items = [dict(r) for r in self.db.execute(
            "SELECT i.*,d.subject,d.recipients_json,d.deleted_at,d.updated_at FROM email_draft_batch_items i JOIN email_drafts d ON d.id=i.draft_id "
            "WHERE i.batch_id=? ORDER BY i.name_snapshot COLLATE NOCASE,i.contact_id", (batch_id,))]
        for item in items:
            item["recipients"] = json.loads(item.pop("recipients_json"))
            item["source_snapshot"] = json.loads(item.pop("source_snapshot_json"))
        return {**dict(batch), "items": items}

    def _attachments(self, entries, application_id):
        if not isinstance(entries, list) or len(entries) > 20:
            raise MailError(_ui_tr('Höchstens 20 Anhänge je Empfänger auswählen.'))
        documents = set()
        if application_id:
            documents = {r[0] for r in self.db.execute(
                "SELECT d.id FROM documents d LEFT JOIN document_sets s ON s.id=d.document_set_id "
                "WHERE d.deleted_at IS NULL AND COALESCE(d.application_id,s.application_id)=?", (application_id,))}
        result, total = [], 0
        for entry in entries:
            if not isinstance(entry, dict):
                raise MailError(_ui_tr('Ungültiger Anhang.'))
            if entry.get("document_id"):
                if entry["document_id"] not in documents:
                    raise MailError(_ui_tr('Dieses Dokument gehört nicht zur gewählten Bewerbung.'))
                row = self.db.execute("SELECT file_path,original_filename FROM documents WHERE id=?", (entry["document_id"],)).fetchone()
                path, filename = self.project.file_path(row["file_path"]), row["original_filename"]
                reference = {"document_id": entry["document_id"]}
            elif set(entry) == {"path"} and isinstance(entry["path"], str):
                path = Path(entry["path"]).resolve()
                filename, reference = path.name, {"path": str(path)}
            else:
                raise MailError(_ui_tr('Ungültiger Anhang.'))
            if not path.is_file() or Path(filename).name != filename or any(c in filename for c in "\r\n\x00"):
                raise MailError(_ui_tr('Anhang fehlt oder Dateiname ist ungültig.'))
            # Bound memory; verify the exact bytes again when capturing the draft.
            with path.open("rb") as stream:
                content = stream.read(20 * 1024 * 1024 + 1)
            total += len(content)
            if total > 20 * 1024 * 1024:
                raise MailError(_ui_tr('Anhänge dürfen je Nachricht zusammen höchstens 20 MiB groß sein.'))
            result.append({"reference": reference, "filename": filename, "size": len(content),
                           "hash": hashlib.sha256(content).hexdigest()})
        return result

    def preview(self, *, version_id, items, provider_account_id=None, signature_id=None, attachments=None,
                document_version_id=None, document_mapping=None, document_format="docx", cancelled=lambda: False, progress=lambda value: None):
        version = self.templates.version(version_id)
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise MailError(_ui_tr('Bitte 1 bis 100 Kontakte pro Entwurfsgruppe auswählen.'))
        account = self.mail._account(provider_account_id) if provider_account_id else None
        self.mail._reference("email_signatures", signature_id)
        signature = dict(self.db.execute("SELECT * FROM email_signatures WHERE id=?", (signature_id,)).fetchone()) if signature_id else None
        if attachments is not None and not isinstance(attachments, list):
            raise MailError(_ui_tr('Anhänge als Liste auswählen.'))
        if document_mapping is not None and (not isinstance(document_mapping, dict) or any(not isinstance(v, str) for v in document_mapping.values())):
            raise MailError(_ui_tr('Ungültige Dokumentzuordnung.'))
        rows, ids, addresses = [], set(), {}
        for item in items:
            if cancelled():
                raise MailError(_ui_tr('Bulk-Vorschau abgebrochen.'))
            progress({"current": len(rows), "total": len(items), "message": _ui_tr("Persönliche Vorschauen prüfen")})
            if not isinstance(item, dict) or set(item) - {"contact_id", "application_id", "values", "documents", "source", "attachments", "document_version_id", "document_mapping", "create_application"}:
                raise MailError(_ui_tr('Ungültiger Bulk-Empfänger.'))
            identifier = item.get("contact_id")
            if not isinstance(identifier, str) or identifier in ids:
                raise MailError(_ui_tr('Jeden Kontakt nur einmal auswählen.'))
            ids.add(identifier)
            row = {"contact_id": identifier, "name": "", "email": "", "error": "", "missing": [], "attachments": []}
            try:
                if item.get("source"):
                    source = self.sources.resolve(item["source"])
                    linked_contact = source["contact_id"]
                    fields = self.templates.context_values(application_id=item.get("application_id"), contact_id=linked_contact)
                    fields.update({key: value for key, value in source["fields"].items()
                                   if value.strip() or key in ("contact.display_name", "contact.email") or source["snapshot"].get("empty_policy") == "keep"})
                    snapshot = source["snapshot"]
                else:
                    linked_contact = identifier
                    fields = self.templates.context_values(application_id=item.get("application_id"), contact_id=identifier)
                    snapshot = {"kind": "contact", "contact_id": identifier}
                if item.get("create_application") and not item.get("application_id"):
                    default_profile = ProjectDefaultsService(self.project).details()["defaults"]["applicant_profile_id"]
                    profile = self.db.execute("SELECT * FROM applicant_profiles WHERE id=? AND deleted_at IS NULL", (default_profile,)).fetchone() if default_profile else None
                    if profile:
                        for key in ("display_name", "email", "phone"):
                            fields.setdefault("applicant." + key, profile[key] or "")
                        snapshot["applicant_profile_snapshot"] = dict(profile)
                overrides = text_values(item.get("values", {}))
                allowed = set(version["placeholders"]) | set(SOURCE_FIELDS)
                personal_version = item.get("document_version_id", document_version_id)
                personal_mapping = item.get("document_mapping", document_mapping if personal_version == document_version_id else None)
                if personal_version:
                    allowed.update((personal_mapping or self.document_version(personal_version)["mapping"]).values())
                    allowed.update(self.document_version(personal_version)["placeholders"])
                if set(overrides) - allowed:
                    raise MailError(_ui_tr('Unbekannte persönliche Werte.'))
                fields.update(overrides)
                row["name"] = fields.get("contact.display_name", "")
                if not row["name"].strip():
                    raise MailError(_ui_tr('Ansprechpartner fehlt.'))
                row["email"] = address(fields.get("contact.email", ""))
                rendered = self.templates.render(version_id, contact_id=linked_contact, application_id=item.get("application_id"),
                    values={k: v for k, v in fields.items() if k in version["placeholders"]})
                documents = item.get("documents", [])
                if not isinstance(documents, list) or any(not isinstance(d, str) for d in documents) or len(set(documents)) != len(documents):
                    raise MailError(_ui_tr('Ungültige Dokumentauswahl.'))
                row.update({key: value for key, value in rendered.items() if key != "name"})
                row["template_name"] = rendered["name"]
                row["preview_body"] = row["body"]
                if signature:
                    row["preview_body"] += ("<br><br>" + (signature["content_html"] or html.escape(signature["content_text"]).replace("\n", "<br>"))) if row["body_format"] == "html" else "\n\n" + signature["content_text"]
                row["application_id"] = item.get("application_id")
                row["linked_contact_id"] = linked_contact
                row["source_snapshot"] = {**snapshot, "effective_values": fields}
                if type(item.get("create_application", False)) is not bool:
                    raise MailError(_ui_tr('Bewerbungsanlage ausdrücklich auswählen.'))
                if item.get("create_application"):
                    if row["application_id"]:
                        raise MailError(_ui_tr('Neue Bewerbung und vorhandene Zuordnung getrennt wählen.'))
                    defaults = ProjectDefaultsService(self.project).details()["defaults"]
                    title = fields.get("job.title") or fields.get("application.title") or "Bewerbung · " + row["name"]
                    row["new_application"] = {"title": header(title, _ui_tr('Bewerbungstitel')), "applicant_profile_id": defaults["applicant_profile_id"],
                                              "values": fields}
                personal = item.get("attachments", [])
                if not isinstance(personal, list):
                    raise MailError(_ui_tr('Persönliche Anhänge als Liste auswählen.'))
                row["attachments"] = self._attachments((attachments or []) + personal + [{"document_id": d} for d in documents], row["application_id"])
                if personal_version:
                    row["generated_document"] = self.document_preview(personal_version, fields, personal_mapping, document_format, row["name"])
                    if len(row["attachments"]) >= 20:
                        raise MailError(_ui_tr('Mit Anschreiben sind höchstens 20 Anhänge erlaubt.'))
                addresses.setdefault(row["email"].casefold(), []).append(row)
            except (ValueError, OSError, DocumentError, DocumentServiceError, KeyError) as error:
                row["error"] = str(error)
            rows.append(row)
        for same in addresses.values():
            if len(same) > 1:
                for row in same:
                    row["error"] = "Doppelte Adresse: einen der Kontakte abwählen."
        ready = all(not row["error"] and not row["missing"] for row in rows)
        value = {"rows": rows, "ready": ready, "version_id": version_id,
                 "provider_account_id": provider_account_id, "signature_id": signature_id,
                 "account": account, "signature": signature, "template": version}
        return {**value, "fingerprint": digest(value)}

    def document_preview(self, version_id, fields, mapping, file_format, name):
        version = self.document_version(version_id)
        mapping = version["mapping"] if mapping is None else mapping
        if file_format not in ("docx", "pdf") or not isinstance(mapping, dict) or set(mapping) - set(version["placeholders"]):
            raise MailError(_ui_tr('Ungültige Dokumentzuordnung oder Ausgabeformat.'))
        if any(not isinstance(v, str) for v in mapping.values()):
            raise MailError(_ui_tr('Dokumentfelder auf persönliche Werte zuordnen.'))
        values = {placeholder: fields.get(mapping.get(placeholder, placeholder), "") for placeholder in version["placeholders"]}
        if file_format == "pdf" and not find_libreoffice():
            raise MailError(_ui_tr('Für PDF-Anschreiben LibreOffice installieren oder DOCX als Ausgabe wählen.'))
        with self.documents.preview_document(version_id, values, required_placeholders=version["placeholders"]) as preview:
            text = extract_docx_text(preview.generated.output_path)
        safe_name = re.sub(r"[^\w -]", "", name)[:80].strip() or "Empfänger"
        return {"version_id": version_id, "template_hash": self.documents.templates.get_version(version_id)["content_hash"],
                "values": values, "format": file_format, "text": text, "filename": f"Anschreiben-{safe_name}.{file_format}"}

    def create(self, *, name, expected_fingerprint, cancelled=lambda: False, progress=lambda value: None, **options):
        name = header(name, _ui_tr('Gruppenname'))
        batch_id, now, copied = str(uuid4()), self.mail._timestamp(), []
        try:
            with _transaction(self.db):
                # Lock database writes before re-reading; files are checked again when copied.
                preview = self.preview(cancelled=cancelled, progress=progress, **options)
                if preview["fingerprint"] != expected_fingerprint:
                    raise MailError(_ui_tr('Die Daten wurden geändert. Vorschau erneut prüfen.'))
                if not preview["ready"]:
                    raise MailError(_ui_tr('Fehlende Werte, ungültige oder doppelte Empfänger zuerst korrigieren.'))
                self.db.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES(?,?,?,?)",
                                (batch_id, name, options["version_id"], now))
                for row in preview["rows"]:
                    if cancelled():
                        raise MailError(_ui_tr('Bulk-Anlage abgebrochen; Gruppe zurückgenommen.'))
                    progress({"current": preview["rows"].index(row), "total": len(preview["rows"]), "message": _ui_tr("Entwürfe und Dokumente speichern")})
                    if row.get("new_application"):
                        from .database.repositories import ApplicationRepository
                        new = row["new_application"]
                        company_id, job_id = None, None
                        # Explicit source values create independent domain records; no guessed merge.
                        company_name = new["values"].get("company.name", "").strip()
                        job_title = new["values"].get("job.title", "").strip()
                        if company_name:
                            company_id = str(uuid4())
                            self.db.execute("INSERT INTO companies(id,name,created_at,updated_at) VALUES(?,?,?,?)", (company_id, header(company_name, _ui_tr('Firmenname')), now, now))
                            if job_title:
                                job_id = str(uuid4())
                                self.db.execute("INSERT INTO job_postings(id,company_id,title,created_at,updated_at) VALUES(?,?,?,?,?)", (job_id, company_id, header(job_title, _ui_tr('Stelle')), now, now))
                        application = ApplicationRepository(self.db).create_in_transaction(new["title"],
                            applicant_profile_id=new["applicant_profile_id"], company_id=company_id, job_posting_id=job_id, source="Bulk", notes=new["values"].get("application.cover_letter"), custom_fields={"bulk_values": new["values"]})
                        row["application_id"] = application["id"]
                        if row.get("linked_contact_id"):
                            self.db.execute("INSERT INTO application_contacts VALUES(?,?,?,?)", (application["id"], row["linked_contact_id"], "Empfänger", now))
                            if company_id:
                                self.db.execute("INSERT INTO company_contacts VALUES(?,?,?,1,?)", (company_id, row["linked_contact_id"], "Empfänger", now))
                    identifier = str(uuid4())
                    entries = self.mail._copy_attachments([a["reference"] for a in row["attachments"]],
                                                         Path("exports/mail/drafts") / identifier / str(uuid4()))
                    copied.extend(entries)
                    if [a["hash"] for a in entries] != [a["hash"] for a in row["attachments"]]:
                        raise MailError(_ui_tr('Ein Anhang wurde geändert. Vorschau erneut prüfen.'))
                    generated = row.get("generated_document")
                    if generated:
                        version = self.document_version(generated["version_id"])
                        with self.documents.preview_document(generated["version_id"], generated["values"],
                                required_placeholders=version["placeholders"], with_pdf=generated["format"] == "pdf", cancelled=cancelled) as document:
                            path = document.pdf_path or document.generated.output_path
                            extra = self.mail._copy_attachments([{"path": str(path), "filename": generated["filename"]}],
                                                               Path("exports/mail/drafts") / identifier / str(uuid4()))
                            copied.extend(extra)
                        if sum(a["size"] for a in entries + extra) > 20 * 1024 * 1024:
                            raise MailError(_ui_tr('Mit Anschreiben überschreiten die Anhänge 20 MiB.'))
                        registered = self.documents.documents.create(file_path=extra[0]["path"], original_filename=generated["filename"],
                            file_size_bytes=extra[0]["size"], file_hash=extra[0]["hash"], template_version_id=generated["version_id"],
                            document_type="bulk_cover_letter", application_id=row.get("application_id"), file_format=generated["format"])
                        extra[0]["document_id"] = registered["id"]
                        entries.extend(extra)
                    self.db.execute(
                        "INSERT INTO email_drafts(id,provider_account_id,application_id,signature_id,subject,body,body_format,recipients_json,configuration_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier, options.get("provider_account_id"), row.get("application_id"), options.get("signature_id"),
                         row["subject"], row["body"], row["body_format"], _json({"to": [row["email"]], "cc": [], "bcc": []}),
                         _json({"attachments": entries}), now, now))
                    self.db.execute("INSERT INTO email_draft_batch_items(batch_id,item_key,contact_id,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json) VALUES(?,?,?,?,?,?,?)",
                                    (batch_id, row["contact_id"], row.get("linked_contact_id"), identifier, row["email"], row["name"],
                                     _json({**row["source_snapshot"], "document": generated, "application_id": row.get("application_id")})))
                _write_activity(self.db, "email_batch.created", "email_draft_batches", batch_id,
                                "Personalisierte lokale Entwurfsgruppe erstellt.", {"count": len(preview["rows"])}, now)
        except BaseException:
            self.mail._cleanup_files(copied)
            raise
        return {"batch": self.batch(batch_id), "batches": self.batches()}
