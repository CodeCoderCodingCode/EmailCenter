"""Single-thread-owned workspace use cases; no Qt dependency."""

from __future__ import annotations

from ..language import translate as _ui_tr, format_text as _ui_format

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from ..database import (
    ApplicationRepository, ApplicationStatusRepository, CompanyRepository,
    ContactRepository, JobPostingRepository, utc_timestamp,
)
from ..document_service import DocumentService, find_libreoffice, resolve_mapping
from ..documents import analyze_docx, extract_docx_text
from ..project import Project, create_project, open_project
from ..import_service import ImportService
from ..mail_service import MailService
from ..mail_context import compose_context
from ..mail_templates import MailTemplateService
from ..mail_bulk import BulkMailService
from ..bulk_delivery import BulkDeliveryService
from ..bulk_sources import BulkSourceService
from ..data_source_library import DataSourceLibrary
from ..export_service import ExportService
from ..document_tables import extract_tables
from ..document_bundle import DocumentBundleService
from ..builder_transfer import BuilderTransferService
from ..word_replace import WordReplaceService
from ..project_defaults import ProjectDefaultsService
from ..email_builder import EmailBuilderService
from ..builder_workspace import BuilderWorkspaceService
from ..record_service import RECORDS, RecordService, fingerprint
from ..administration import AdministrationService
from ..builder_groups import BuilderGroupsService
from ..reminder_service import ReminderService


# Whitelisted projections prevent user-provided table or column identifiers.
LISTS = {
    "applicants": ("applicant_profiles c", "c.*", "c.deleted_at IS NULL", ("c.display_name", "c.email", "c.phone"), "c.display_name COLLATE NOCASE, c.id"),
    "jobs": ("job_postings j JOIN companies c ON c.id=j.company_id", "j.*, c.name AS company_name", "j.deleted_at IS NULL", ("j.title", "c.name", "j.location", "j.reference_number"), "j.title COLLATE NOCASE, j.id"),
    "companies": ("companies c", "c.*", "c.deleted_at IS NULL", ("c.name", "c.industry", "c.website"), "c.name COLLATE NOCASE, c.id"),
    "contacts": ("contacts c", "c.*", "c.deleted_at IS NULL", ("c.display_name", "c.email", "c.position"), "c.display_name COLLATE NOCASE, c.id"),
    "applications": (
        "applications a JOIN application_statuses s ON s.id=a.status_id LEFT JOIN companies c ON c.id=a.company_id",
        "a.*, s.label AS status_label, s.code AS status_code, s.is_terminal AS status_is_terminal, c.name AS company_name, (SELECT status FROM application_mail_receipts r WHERE r.application_id=a.id ORDER BY r.updated_at DESC,r.rowid DESC LIMIT 1) AS mail_status",
        "a.deleted_at IS NULL", ("a.title", "c.name", "s.label"), "a.updated_at DESC, a.id",
    ),
    "templates": (
        "template_versions v JOIN templates t ON t.id=v.template_id",
        "v.*, t.name AS template_name", "t.deleted_at IS NULL AND t.template_type='document'",
        ("t.name",), "t.name COLLATE NOCASE, v.version_number DESC",
    ),
    "documents": (
        "documents d LEFT JOIN applications a ON a.id=d.application_id",
        "d.*, a.title AS application_title", "d.deleted_at IS NULL",
        ("d.original_filename", "a.title", "d.format"), "d.created_at DESC, d.id",
    ),
}


class WorkspaceService:
    """Keep project connections and preview contexts on the owning worker thread."""

    def __init__(self, cancel_requested=lambda: False, progress_callback=lambda value: None) -> None:
        self.project: Project | None = None
        self._preview_context = None
        self._bulk_preview = None
        self._export_preview = None
        self._document_bundle_preview = None
        self._word_replace_preview = None
        self._builder_preview = None
        self.cancel_requested = cancel_requested
        self.progress_callback = progress_callback

    def execute(self, action: str, payload: dict[str, object]) -> object:
        operations = {
            'administration_list': self.administration_list,
            'administration_cleanup': self.administration_cleanup,
            'administration_export_path': self.administration_export_path,
            'administration_lifecycle': self.administration_lifecycle,
            'administration_status_save': self.administration_status_save,
            'administration_status_delete': self.administration_status_delete,
            'administration_signature_save': self.administration_signature_save,
            'builder_groups_list': self.builder_groups_list,
            'builder_groups_save': self.builder_groups_save,
            'builder_groups_delete': self.builder_groups_delete,
            "create_project": self.create, "open_project": self.open,
            "close_project": self.close, "snapshot": self.snapshot,
            "set_workspace_mode": self.set_workspace_mode,
            "project_setup_details": self.project_setup_details, "project_setup_save": self.project_setup_save,
            "recipient_library_save": self.recipient_library_save, "recipient_library_delete": self.recipient_library_delete,
            "mail_bulk_background": self.mail_bulk_background,
            "mail_job_details": self.mail_job_details,
            "workspace_mail_snapshot": self.mail_snapshot,
            "mail_compose_details": self.mail_compose_details,
            "mail_context_details": self.mail_context_details,
            "mail_template_list": self.mail_template_list, "mail_template_details": self.mail_template_details,
            "mail_template_save": self.mail_template_save, "mail_template_duplicate": self.mail_template_duplicate,
            "mail_template_render": self.mail_template_render,
            "document_template_duplicate": self.document_template_duplicate,
            "mail_bulk_details": self.mail_bulk_details, "mail_bulk_context": self.mail_bulk_context,
            "mail_bulk_preview": self.mail_bulk_preview, "mail_bulk_create": self.mail_bulk_create,
            "mail_bulk_batch": self.mail_bulk_batch,
            "mail_bulk_source_rows": self.mail_bulk_source_rows,
            "inspect_builder_source": self.inspect_import,
            "prepare_builder_source": self.prepare_builder_source,
            "mail_bulk_source_select": self.mail_bulk_source_select,
            "mail_bulk_docx_text": self.mail_bulk_docx_text,
            "source_document_tables": self.source_document_tables,
            "source_profile_save": self.source_profile_save,
            "source_list_save": self.source_list_save,
            "source_list_details": self.source_list_details,
            "source_list_select": self.source_list_select,
            "export_preview": self.export_preview, "export_write": self.export_write,
            "document_bundle_preview": self.document_bundle_preview, "document_bundle_write": self.document_bundle_write,
            "word_replace_details": self.word_replace_details, "word_replace_analyze": self.word_replace_analyze,
            "word_replace_run_load": self.word_replace_run_load, "word_replace_run_next": self.word_replace_run_next,
            "word_replace_run_pause": self.word_replace_run_pause,
            "word_replace_preview": self.word_replace_preview, "word_replace_create": self.word_replace_create,
            "builder_details": self.builder_details, "builder_load": self.builder_load,
            "builder_save": self.builder_save, "builder_preview": self.builder_preview,
            "builtin_template_install": self.builtin_template_install,
            "builder_create": self.builder_create, "builder_asset_preview": self.builder_asset_preview,
            "builder_workspace_save": self.builder_workspace_save,
            "builder_export": self.builder_export, "builder_import": self.builder_import,
            "mail_bulk_delivery_details": self.mail_bulk_delivery_details,
            "mail_bulk_delivery_begin": self.mail_bulk_delivery_begin,
            "mail_bulk_delivery_prepare_next": self.mail_bulk_delivery_prepare_next,
            "mail_bulk_delivery_snapshot": self.mail_bulk_delivery_snapshot,
            "mail_bulk_delivery_approve": self.mail_bulk_delivery_approve,
            "mail_bulk_delivery_start": self.mail_bulk_delivery_start,
            "mail_bulk_delivery_next": self.mail_bulk_delivery_next,
            "mail_bulk_delivery_pause": self.mail_bulk_delivery_pause,
            "mail_bulk_delivery_cancel": self.mail_bulk_delivery_cancel,
            "mail_bulk_delivery_item": self.mail_bulk_delivery_item,
            "list": self.list_records, "create_record": self.create_record,
            "record_details": self.record_details, "update_record": self.update_record,
            "record_links": self.record_links, "save_record_link": self.save_record_link,
            "followup_list": self.followup_list, "followup_summary": self.followup_summary,
            "reminder_details": self.reminder_details, "reminder_save": self.reminder_save,
            "reminder_finish": self.reminder_finish,
            "change_status": self.change_status, "backup": self.backup,
            "backup_inspect": self.backup_inspect, "backup_restore": self.backup_restore,
            "diagnostic_export": self.diagnostic_export,
            "analyze_template": self.analyze_template, "import_template": self.import_template,
            "document_values": self.document_values, "generate_document": self.generate_document,
            "preview_document": self.preview_document, "release_preview": self.release_preview,
            "create_pdf": self.create_pdf, "document_path": self.document_path,
            "inspect_import": self.inspect_import, "prepare_import": self.prepare_import,
            "import_runs": self.import_runs, "import_rows": self.import_rows,
            "process_import": self.process_import, "edit_import_row": self.edit_import_row,
            "review_import_row": self.review_import_row,
            "mail_snapshot": self.mail_snapshot, "mail_connect": self.mail_connect,
            "mail_disconnect": self.mail_disconnect, "mail_save_draft": self.mail_save_draft,
            "mail_sync_draft": self.mail_sync_draft, "mail_save_signature": self.mail_save_signature,
            "mail_prepare_job": self.mail_prepare_job, "mail_approve": self.mail_approve,
            "mail_cancel": self.mail_cancel, "mail_send": self.mail_send,
            "mail_approve_and_send": self.mail_approve_and_send,
            "mail_reconcile": self.mail_reconcile, "mail_retry": self.mail_retry,
            "mail_due": self.mail_due, "mail_mark_overdue": self.mail_mark_overdue,
        }
        if action not in operations:
            raise ValueError(_ui_format('Unbekannte Aktion: {0}', f'{action}'))
        return operations[action](**payload)

    def create(self, path: str, name: str, workspace_mode="applications", goal="",
               initial_profile=None, initial_signature=None, defaults=None, initial_document=None, initial_source=None) -> dict[str, object]:
        candidate = create_project(path, name=name, workspace_mode=workspace_mode, goal=goal,
                                   initial_profile=initial_profile, initial_signature=initial_signature,
                                   defaults=defaults, initial_document=initial_document, initial_source=initial_source)
        self._replace_project(candidate)
        return self.snapshot()

    def open(self, path: str) -> dict[str, object]:
        candidate = open_project(path)
        self._replace_project(candidate)
        return self.snapshot()

    def _replace_project(self, candidate: Project) -> None:
        try:
            MailService(candidate).recover()
            self.close()
        except BaseException:
            candidate.close()
            raise
        self.project = candidate

    def close(self) -> None:
        self._builder_preview = None
        self._bulk_preview = None
        self._export_preview = None
        self._document_bundle_preview = None
        self._word_replace_preview = None
        try:
            self.release_preview()
        finally:
            if self.project is not None:
                self.project.connection.execute("UPDATE email_bulk_dispatches SET status='Paused',last_error='Projekt geschlossen; vor Fortsetzung prüfen.' WHERE status='Running'")
                self.project.close()
                self.project = None

    def _project(self) -> Project:
        if self.project is None:
            raise ValueError(_ui_tr('Bitte zuerst ein Projekt öffnen oder erstellen.'))
        return self.project

    def snapshot(self) -> dict[str, object]:
        project = self._project()
        connection = project.connection
        counts = {}
        for entity,table in (('companies','companies'),('contacts','contacts'),('applications','applications'),('documents','documents'),('templates','templates'),('applicants','applicant_profiles'),('jobs','job_postings')):
            condition="deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type=? AND r.entity_id="+table+".id)"
            if entity=='templates':condition+=" AND template_type='document'"
            counts[entity]=connection.execute('SELECT COUNT(*) FROM '+table+' WHERE '+condition,(entity,)).fetchone()[0]
        counts["followups"] = self.followup_summary()["due"]
        counts["mail_jobs"] = connection.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0]
        counts["mail_drafts"] = connection.execute("SELECT COUNT(*) FROM email_drafts WHERE deleted_at IS NULL").fetchone()[0]
        counts['connected_accounts'] = connection.execute('SELECT COUNT(*) FROM email_provider_accounts WHERE is_enabled=1 AND deleted_at IS NULL').fetchone()[0]
        counts['approved_jobs'] = connection.execute("SELECT COUNT(*) FROM email_jobs WHERE approval_status='approved'").fetchone()[0]
        counts['sent_jobs'] = connection.execute("SELECT COUNT(*) FROM email_jobs WHERE status='Sent'").fetchone()[0]
        metadata = dict(connection.execute("SELECT key,value FROM project_metadata WHERE key IN ('workspace_mode','project_goal')"))
        choices = {
            "jobs": [dict(row) for row in connection.execute(
                "SELECT j.id,j.title,j.company_id,c.name AS company_name FROM job_postings j JOIN companies c ON c.id=j.company_id WHERE j.deleted_at IS NULL AND c.deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE (r.entity_type='jobs' AND r.entity_id=j.id) OR (r.entity_type='companies' AND r.entity_id=c.id)) ORDER BY j.title COLLATE NOCASE,j.id")],
            "companies": [dict(row) for row in connection.execute(
                "SELECT id, name FROM companies WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='companies' AND r.entity_id=companies.id) ORDER BY name COLLATE NOCASE")],
            "applicants": [dict(row) for row in connection.execute(
                "SELECT id, display_name FROM applicant_profiles WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='applicants' AND r.entity_id=applicant_profiles.id) ORDER BY display_name COLLATE NOCASE")],
            "applications": [dict(row) for row in connection.execute(
                "SELECT id, title FROM applications WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='applications' AND r.entity_id=applications.id) ORDER BY updated_at DESC")],
            "contacts": [dict(row) for row in connection.execute(
                "SELECT id,display_name FROM contacts WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type='contacts' AND r.entity_id=contacts.id) ORDER BY display_name COLLATE NOCASE,id")],
        }
        return {"name": project.name, "path": str(project.path), "counts": counts,
                "statuses": ApplicationStatusRepository(connection).list(), "choices": choices,
                "workspace_mode": metadata.get("workspace_mode", "applications"),
                "project_goal": metadata.get("project_goal", ""),
                "project_settings": ProjectDefaultsService(project).details(),
                "bulk_groups": BulkDeliveryService(project).groups(),
                "recent_applications": self.list_records("applications", limit=6)["rows"],
                "recent_mail_jobs": [dict(row) for row in connection.execute(
                    "SELECT id,subject_snapshot,status,approval_status FROM email_jobs ORDER BY created_at DESC,rowid DESC LIMIT 6")],
                "workspace_templates": self.list_records("templates", limit=50)["rows"],
                "libreoffice": find_libreoffice()}

    def set_workspace_mode(self, mode):
        if mode not in ("applications", "mail"):
            raise ValueError(_ui_tr('Ungültiger Arbeitsmodus.'))
        self._project().connection.execute(
            "INSERT INTO project_metadata(key,value) VALUES ('workspace_mode',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (mode,))
        return self.snapshot()

    def project_setup_details(self, purpose="edit"):
        return {**ProjectDefaultsService(self._project()).choices(), "purpose": purpose}

    def project_setup_save(self, **values):
        ProjectDefaultsService(self._project()).save(**values)
        return self.snapshot()

    def recipient_library_save(self, **values):
        from ..recipient_library import RecipientLibrary
        return RecipientLibrary(self._project().connection).save(**values)

    def recipient_library_delete(self, **values):
        from ..recipient_library import RecipientLibrary
        return RecipientLibrary(self._project().connection).delete(**values)

    def mail_bulk_background(self, require_review=False):
        return BulkDeliveryService(self._project()).background_next(require_review)

    def mail_job_details(self, job_id):
        return MailService(self._project()).job(job_id)

    def mail_compose_details(self, draft_id=None, application_id=None, contact_id=None):
        if draft_id and (application_id or contact_id):
            raise ValueError(_ui_tr('Bestehenden Entwurf und neuen Kontext getrennt auswählen.'))
        return {"snapshot": self.mail_snapshot(limit=1),
                "draft": MailService(self._project()).draft(draft_id) if draft_id else None,
                "context": self.mail_context_details(application_id, contact_id) if application_id or contact_id else None}

    def mail_context_details(self, application_id=None, contact_id=None):
        return compose_context(self._project().connection, application_id=application_id, contact_id=contact_id)

    def mail_template_list(self, **options):
        return MailTemplateService(self._project().connection).list(**options)

    def mail_template_details(self, template_id):
        return MailTemplateService(self._project().connection).details(template_id)

    def mail_template_save(self, **options):
        return MailTemplateService(self._project().connection).save(**options)

    def mail_template_duplicate(self, version_id):
        return MailTemplateService(self._project().connection).duplicate(version_id)

    def mail_template_render(self, **options):
        return MailTemplateService(self._project().connection).render(**options)

    def mail_bulk_details(self):
        return BulkMailService(self._project()).details()

    def mail_bulk_context(self, **options):
        return BulkMailService(self._project()).context(**options)

    def mail_bulk_preview(self, **options):
        self._bulk_preview = None
        result = BulkMailService(self._project()).preview(cancelled=self.cancel_requested, progress=self.progress_callback, **options)
        identifier = str(uuid4())
        self._bulk_preview = (identifier, deepcopy(options), result["fingerprint"])
        return {**result, "preview_id": identifier}

    def mail_bulk_create(self, name, preview_id):
        if not self._bulk_preview or self._bulk_preview[0] != preview_id:
            raise ValueError(_ui_tr('Vorschau erneut laden und prüfen.'))
        _, options, fingerprint_value = self._bulk_preview
        result = BulkMailService(self._project()).create(name=name, expected_fingerprint=fingerprint_value, cancelled=self.cancel_requested, progress=self.progress_callback, **options)
        self._bulk_preview = None
        return result

    def mail_bulk_batch(self, batch_id):
        return BulkMailService(self._project()).batch(batch_id)

    def mail_bulk_source_rows(self, **options):
        return BulkSourceService(self._project().connection).rows(**options)

    def mail_bulk_source_select(self, **options):
        return BulkSourceService(self._project().connection).select(**options)

    def mail_bulk_docx_text(self, path):
        source = Path(path)
        if source.suffix.lower() != ".docx" or not source.is_file():
            raise ValueError(_ui_tr('Eine vorhandene DOCX-Datei auswählen.'))
        text = extract_docx_text(source)
        if len(text) > 32768:
            raise ValueError(_ui_tr('Dokumenttext ist zu lang (maximal 32768 Zeichen).'))
        return {"text": text}

    def source_profile_save(self, **options):
        return DataSourceLibrary(self._project().connection).save_profile(**options)

    def source_document_tables(self, **options):
        self._project()
        return extract_tables(cancelled=self.cancel_requested, **options)

    def source_list_save(self, **options):
        return DataSourceLibrary(self._project().connection).save_list(**options)

    def source_list_details(self, list_id):
        return DataSourceLibrary(self._project().connection).list(list_id)

    def source_list_select(self, **options):
        return BulkSourceService(self._project().connection).select_list(**options)

    def export_preview(self, **options):
        self._export_preview = None
        value = ExportService(self._project()).preview(**options)
        identifier = str(uuid4())
        self._export_preview = (identifier, deepcopy(options), value["fingerprint"])
        return {**value, "preview_id": identifier}

    def document_bundle_preview(self, **options):
        self._document_bundle_preview = None
        value = DocumentBundleService(self._project()).preview(cancelled=self.cancel_requested, **options)
        identifier = str(uuid4())
        self._document_bundle_preview = (identifier, deepcopy(options), value["fingerprint"])
        return {**value, "preview_id": identifier}

    def document_bundle_write(self, preview_id, **options):
        if not self._document_bundle_preview or self._document_bundle_preview[0] != preview_id:
            raise ValueError(_ui_tr('Dokumentvorschau erneut laden.'))
        _, query, expected = self._document_bundle_preview
        service = DocumentBundleService(self._project())
        value = service.preview(cancelled=self.cancel_requested, **query)
        if value["fingerprint"] != expected:
            self._document_bundle_preview = None
            raise ValueError(_ui_tr('Dokumente oder Dateiinhalte verändert. Vorschau erneut laden und prüfen.'))
        result = service.write(value, cancelled=self.cancel_requested, **options)
        AdministrationService(self._project()).log_export("documents",result,query)
        self._document_bundle_preview = None
        return result

    def export_write(self, preview_id, **options):
        if not self._export_preview or self._export_preview[0] != preview_id:
            raise ValueError(_ui_tr('Exportvorschau erneut laden.'))
        identifier, query, expected = self._export_preview
        service = ExportService(self._project())
        preview = service.preview(**query)
        if preview["fingerprint"] != expected:
            self._export_preview = None
            raise ValueError(_ui_tr('Exportdaten wurden geändert. Vorschau erneut laden und prüfen.'))
        result = service.write(preview=preview, cancelled=self.cancel_requested, **options)
        AdministrationService(self._project()).log_export("records",result,query)
        self._export_preview = None
        return result

    def word_replace_details(self):
        return WordReplaceService(self._project()).details()

    def builder_details(self):
        return {**EmailBuilderService(self._project()).details(), "workspace": BuilderWorkspaceService(self._project()).load()}

    def builder_groups_list(self):
        return BuilderGroupsService(self._project()).list()

    def builder_groups_save(self, **options):
        return BuilderGroupsService(self._project()).save(**options)

    def builder_groups_delete(self, **options):
        return BuilderGroupsService(self._project()).delete(**options)

    def builder_workspace_save(self, **options):
        return BuilderWorkspaceService(self._project()).save(**options)

    def builder_export(self, **options):
        return BuilderTransferService(self._project()).export(cancelled=self.cancel_requested, **options)

    def builder_import(self, path):
        return BuilderTransferService(self._project()).import_file(path)

    def builder_load(self, version_id):
        return EmailBuilderService(self._project()).version(version_id)

    def builder_save(self, **options):
        self._builder_preview = None
        return EmailBuilderService(self._project()).save(**options)

    def builder_preview(self, **options):
        self._builder_preview = None
        value = EmailBuilderService(self._project()).preview(cancelled=self.cancel_requested, **options)
        if 'evaluation_time' in value:
            options['evaluation_time'] = value['evaluation_time']
        identifier = str(uuid4())
        self._builder_preview = (identifier, deepcopy(options), value["fingerprint"])
        return {**value, "preview_id": identifier}

    def builder_asset_preview(self, **options):
        request_id = options.pop("request_id")
        return {**EmailBuilderService(self._project()).asset_preview(cancelled=self.cancel_requested, **options), "request_id": request_id}

    def builtin_template_install(self, kind, key):
        from ..builtin_templates import install_document, install_mail
        if kind == 'document':
            return install_document(self._project(), key)
        if kind == 'email':
            return install_mail(self._project(), key)
        raise ValueError('Unknown built-in template type.')

    def builder_create(self, name, preview_id, delivery_plan=None):
        if not self._builder_preview or self._builder_preview[0] != preview_id:
            raise ValueError(_ui_tr('Builder-Vorschau erneut laden und prüfen.'))
        _, options, expected = self._builder_preview
        value = EmailBuilderService(self._project()).create(name, expected_fingerprint=expected, delivery_plan=delivery_plan, cancelled=self.cancel_requested, **options)
        self._builder_preview = None
        if value["dispatch"]:
            delivery = BulkDeliveryService(self._project())
            for _ in value["batch"]["items"]:
                if self.cancel_requested():
                    break
                value["dispatch"] = delivery.prepare_next(value["dispatch"]["id"])
                if value["dispatch"]["last_error"] or value["dispatch"]["status"] != "Preparing":
                    break
        return value

    def word_replace_analyze(self, source_path):
        return WordReplaceService(self._project()).analyze(source_path)

    def word_replace_preview(self, **options):
        self._word_replace_preview = None
        result = WordReplaceService(self._project()).preview(cancelled=self.cancel_requested, progress=self.progress_callback, **options)
        identifier = str(uuid4())
        self._word_replace_preview = (identifier, deepcopy(options), result["fingerprint"])
        return {**result, "preview_id": identifier}

    def word_replace_create(self, preview_id, durable=False, **options):
        if not self._word_replace_preview or self._word_replace_preview[0] != preview_id:
            raise ValueError(_ui_tr('Word-Replace-Vorschau erneut laden und prüfen.'))
        identifier, configuration, expected = self._word_replace_preview
        if durable:
            from ..word_replace_runs import WordReplaceRuns
            result = {"run": WordReplaceRuns(self._project()).begin(expected_fingerprint=expected, cancelled=self.cancel_requested, **configuration, **options)}
        else:
            result = WordReplaceService(self._project()).create(expected_fingerprint=expected, cancelled=self.cancel_requested, **configuration, **options)
        self._word_replace_preview = None
        return result

    def word_replace_run_load(self, run_id):
        from ..word_replace_runs import WordReplaceRuns
        return WordReplaceRuns(self._project()).pause(run_id)

    def word_replace_run_next(self, run_id):
        from ..word_replace_runs import WordReplaceRuns
        return WordReplaceRuns(self._project()).next(run_id, self.cancel_requested)

    def word_replace_run_pause(self, run_id):
        from ..word_replace_runs import WordReplaceRuns
        return WordReplaceRuns(self._project()).pause(run_id)

    def mail_bulk_delivery_details(self, batch_id):
        return BulkDeliveryService(self._project()).details(batch_id)

    def mail_bulk_delivery_begin(self, **options):
        return BulkDeliveryService(self._project()).begin(**options)

    def mail_bulk_delivery_prepare_next(self, dispatch_id):
        return BulkDeliveryService(self._project()).prepare_next(dispatch_id)

    def mail_bulk_delivery_snapshot(self, dispatch_id):
        return BulkDeliveryService(self._project()).snapshot(dispatch_id)

    def mail_bulk_delivery_approve(self, **options):
        return BulkDeliveryService(self._project()).approve(**options)

    def mail_bulk_delivery_start(self, **options):
        return BulkDeliveryService(self._project()).start(**options)

    def mail_bulk_delivery_next(self, dispatch_id):
        return BulkDeliveryService(self._project()).next(dispatch_id)

    def mail_bulk_delivery_pause(self, dispatch_id, require_review=False):
        return BulkDeliveryService(self._project()).pause(dispatch_id, require_review=require_review)

    def mail_bulk_delivery_cancel(self, dispatch_id):
        return BulkDeliveryService(self._project()).cancel(dispatch_id)

    def mail_bulk_delivery_item(self, **options):
        return BulkDeliveryService(self._project()).item_action(**options)

    def list_records(self, entity: str, *, search: str = "", offset: int = 0, limit: int = 50, template_type="document") -> dict[str, object]:
        if entity not in LISTS or offset < 0 or not 1 <= limit <= 200:
            raise ValueError(_ui_tr('Ungültige Listenanfrage.'))
        table, projection, condition, search_columns, ordering = LISTS[entity]
        parameters: list[object] = []
        if entity == "templates":
            if template_type not in ("all", "document", "email"):
                raise ValueError(_ui_tr('Ungültiger Vorlagentyp.'))
            projection += ", t.template_type, CASE t.template_type WHEN 'document' THEN 'DOCX' ELSE 'E-Mail' END AS type_label"
            condition = "t.deleted_at IS NULL AND t.template_type IN ('document','email')"
            if template_type != "all":
                condition += " AND t.template_type=?"
                parameters.append(template_type)
        if search.strip():
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            condition += " AND (" + " OR ".join(f"{column} LIKE ? ESCAPE '\\'" for column in search_columns) + ")"
            parameters.extend([f"%{escaped}%"] * len(search_columns))
        connection = self._project().connection
        archive_alias = {'companies':'c','contacts':'c','applicants':'c','jobs':'j','applications':'a','templates':'t','documents':'d'}[entity]
        condition += f' AND NOT EXISTS(SELECT 1 FROM record_archive ar WHERE ar.entity_type=? AND ar.entity_id={archive_alias}.id)'
        parameters.append(entity)
        total = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {condition}", parameters).fetchone()[0]
        rows = connection.execute(
            f"SELECT {projection} FROM {table} WHERE {condition} ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
        return {"entity": entity, "rows": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}

    def administration_list(self, **options):
        return AdministrationService(self._project()).list(**options)

    def administration_cleanup(self, **options):
        return AdministrationService(self._project()).cleanup(**options)

    def administration_export_path(self, **options):
        return AdministrationService(self._project()).export_path(**options)

    def administration_lifecycle(self, **options):
        return AdministrationService(self._project()).lifecycle(**options)

    def administration_status_save(self, **options):
        return AdministrationService(self._project()).save_status(**options)

    def administration_status_delete(self, **options):
        return AdministrationService(self._project()).delete_status(**options)

    def administration_signature_save(self, fields, record_id=None, expected_version=None):
        return MailService(self._project()).save_signature(signature_id=record_id,expected_version=expected_version,**fields)

    def create_record(self, entity, fields):
        from ..database.repositories import _atomic, _write_activity
        connection = self._project().connection
        values = RecordService(connection).validate(entity,fields,creating=True)
        extra = {key:values.pop(key) for key in ('address_json','custom_fields_json','start_date') if key in values}
        with _atomic(connection):
            record = self._create_record_base(entity,values)
            if extra:
                connection.execute('UPDATE '+RECORDS[entity][0]+' SET '+','.join(key+'=?' for key in extra)+' WHERE id=?',(*extra.values(),record['id']))
            _write_activity(connection,'record.created',RECORDS[entity][0],record['id'],'Datensatz erstellt.',{'fields':sorted(fields)},utc_timestamp())
        return RecordService(connection).get(entity,record['id'])

    def _create_record_base(self, entity: str, fields: dict[str, object]) -> dict[str, object]:
        connection = self._project().connection
        fields = RecordService(connection).validate(entity, fields, creating=True)
        if entity == "jobs":
            return JobPostingRepository(connection).create(**fields)
        if entity == "companies":
            return CompanyRepository(connection).create(**fields)
        if entity == "contacts":
            return ContactRepository(connection).create(**fields)
        if entity == "applications":
            return ApplicationRepository(connection).create_in_transaction(**fields)
        if entity == "applicants":
            name = str(fields.get("display_name", "")).strip()
            if not name:
                raise ValueError(_ui_tr('Bitte einen Profilnamen eingeben.'))
            record_id, now = str(uuid4()), utc_timestamp()
            connection.execute(
                "INSERT INTO applicant_profiles(id, display_name, email, phone, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (record_id, name, fields.get("email"), fields.get("phone"), now, now),
            )
            return {"id": record_id, "display_name": name}
        raise ValueError(_ui_format('Nicht unterstützter Datensatztyp: {0}', f'{entity}'))

    def record_details(self, entity, record_id=None):
        if entity not in RECORDS:
            raise ValueError(_ui_tr('Unbekannter Datensatztyp.'))
        service = RecordService(self._project().connection)
        record = service.get(entity, record_id) if record_id else None
        snapshot = self.snapshot()
        return {"entity": entity, "record": record, "version": fingerprint(record) if record else None,
                "defaults": snapshot["project_settings"]["defaults"],
                "mail_receipts": [dict(r) for r in self._project().connection.execute("SELECT * FROM application_mail_receipts WHERE application_id=? ORDER BY updated_at DESC", (record_id,))] if entity == "applications" and record_id else [],
                "choices": snapshot["choices"], "statuses": snapshot["statuses"]}

    def update_record(self, entity, record_id, fields, expected_version):
        return RecordService(self._project().connection).update(entity, record_id, fields, expected_version)

    def record_links(self, entity, record_id):
        return RecordService(self._project().connection).links(entity, record_id)

    def save_record_link(self, entity, record_id, contact_id, **options):
        return RecordService(self._project().connection).save_link(entity, record_id, contact_id, **options)

    def followup_list(self, **options):
        return ReminderService(self._project().connection).list(**options)

    def followup_summary(self):
        return ReminderService(self._project().connection).summary()

    def reminder_details(self, **options):
        return ReminderService(self._project().connection).details(**options)

    def reminder_save(self, **options):
        return ReminderService(self._project().connection).save(**options)

    def reminder_finish(self, **options):
        return ReminderService(self._project().connection).finish(**options)

    def change_status(self, application_id: str, status_code: str) -> dict[str, object]:
        return ApplicationRepository(self._project().connection).change_status(application_id, status_code)

    def backup(self, directory="", retention=0) -> str:
        if type(retention) is not int or not 0 <= retention <= 1000:
            raise ValueError(_ui_tr('Ungültige Backup-Aufbewahrung.'))
        from ..backups import prune_backups
        project = self._project()
        path = project.create_backup(directory)
        try:
            prune_backups(project, path.parent, retention)
        except OSError as error:
            raise ValueError(_ui_format('Backup wurde erstellt: {0}; Aufbewahrung konnte nicht ausgeführt werden: {1}', str(path), str(error))) from error
        return str(path)

    def backup_inspect(self, path):
        from ..backups import inspect_backup
        return inspect_backup(path)

    def diagnostic_export(self, directory, libreoffice_path=""):
        from ..diagnostics import diagnostic_report
        import json
        target = Path(directory)
        if not target.is_absolute() or not target.is_dir():
            raise ValueError(_ui_tr('Vorhandenen absoluten Diagnoseordner wählen.'))
        report = diagnostic_report(self.project, libreoffice_path=libreoffice_path)
        path = target / ("emailcenter-diagnostic-" + str(uuid4())[:8] + ".json")
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        return str(path)

    def backup_restore(self, **options):
        from ..backups import restore_backup
        return restore_backup(**options, cancelled=self.cancel_requested)

    def analyze_template(self, source_path: str) -> dict[str, object]:
        return {"source_path": source_path, "placeholders": list(analyze_docx(source_path).placeholders)}

    def import_template(self, source_path: str, name: str, mapping: dict[str, str], required_placeholders: list[str],
                        template_id: str | None = None) -> dict[str, object]:
        service = DocumentService(self._project())
        if template_id is not None:
            return service.add_template_version(template_id, source_path, mapping=mapping,
                                                required_placeholders=required_placeholders)
        return service.import_template(source_path, name=name, mapping=mapping, required_placeholders=required_placeholders)

    def document_template_duplicate(self, version_id, name=None):
        return DocumentService(self._project()).duplicate_template(version_id, name)

    def document_values(self, template_version_id: str, application_id: str | None) -> dict[str, object]:
        project = self._project()
        version = DocumentService(project).templates.get_version(template_version_id)
        if version is None:
            raise KeyError(_ui_tr('Vorlagenversion nicht gefunden.'))
        context: dict[str, object] = {}
        if application_id:
            application = ApplicationRepository(project.connection).get(application_id)
            if application is None:
                raise KeyError(_ui_tr('Bewerbung nicht gefunden.'))
            context["application"] = application
            for key, table, identifier in (("applicant", "applicant_profiles", application["applicant_profile_id"]),
                                           ("company", "companies", application["company_id"])):
                row = project.connection.execute(f"SELECT * FROM {table} WHERE id = ? AND deleted_at IS NULL", (identifier,)).fetchone()
                if row is not None:
                    context[key] = dict(row)
            contacts = ApplicationRepository(project.connection).list_contacts(application_id)
            if len(contacts) == 1:
                context["contact"] = contacts[0]
        config = json.loads(version["configuration_json"])
        return {"values": resolve_mapping(config.get("mapping", {}), context)}

    def generate_document(self, **options) -> dict[str, object]:
        result, document = DocumentService(self._project()).generate_document(cancelled=self.cancel_requested, **options)
        return {"path": str(result.output_path), "document": document, "unresolved": list(result.unresolved)}

    def preview_document(self, template_version_id: str, values: dict[str, object], with_pdf: bool = False) -> dict[str, object]:
        self.release_preview()
        context = DocumentService(self._project()).preview_document(template_version_id, values, with_pdf=with_pdf, cancelled=self.cancel_requested)
        preview = context.__enter__()
        try:
            result = {"before": extract_docx_text(preview.template_path),
                      "after": extract_docx_text(preview.generated.output_path),
                      "pdf_path": str(preview.pdf_path) if preview.pdf_path else None,
                      "pdf_bytes": preview.pdf_path.read_bytes() if preview.pdf_path else None,
                      "unresolved": list(preview.generated.unresolved)}
        except BaseException:
            context.__exit__(None, None, None)
            raise
        self._preview_context = context
        return result

    def release_preview(self) -> None:
        if self._preview_context is not None:
            context = self._preview_context
            self._preview_context = None
            context.__exit__(None, None, None)

    def create_pdf(self, document_id: str) -> dict[str, object]:
        return DocumentService(self._project()).create_pdf_version(document_id, cancelled=self.cancel_requested)

    def document_path(self, document_id: str) -> dict[str, object]:
        project = self._project()
        row = project.connection.execute("SELECT file_path, format FROM documents WHERE id = ? AND deleted_at IS NULL", (document_id,)).fetchone()
        if row is None:
            raise KeyError(_ui_tr('Dokument nicht gefunden.'))
        path = project.file_path(row["file_path"])
        if not path.is_file():
            raise ValueError(_ui_tr('Die gespeicherte Dokumentdatei fehlt.'))
        result = {"path": str(path), "format": row["format"]}
        if row["format"] == "pdf":
            result["pdf_bytes"] = path.read_bytes()
        return result

    def inspect_import(self, source_path: str, options=None):
        return ImportService(self._project()).inspect(source_path, options)

    def prepare_import(self, **options):
        return ImportService(self._project()).prepare(**options)

    def prepare_builder_source(self, **options):
        if options.get('entity') != 'data_rows':
            raise ValueError('Builder source import requires the data-only target.')
        run = ImportService(self._project()).prepare(**options)
        return {'run': run, 'runs': BulkSourceService(self._project().connection).runs()}

    def import_runs(self, **options):
        return ImportService(self._project()).list_runs(**options)

    def import_rows(self, **options):
        return ImportService(self._project()).list_rows(**options)

    def process_import(self, run_id, max_rows=100):
        return ImportService(self._project()).process(run_id, max_rows, self.cancel_requested)

    def edit_import_row(self, row_id, fields):
        return ImportService(self._project()).edit_row(row_id, fields)

    def review_import_row(self, row_id, decision):
        return ImportService(self._project()).review_row(row_id, decision)

    def mail_snapshot(self, **options):
        value = MailService(self._project()).snapshot(**options)
        value["mail_templates"] = MailTemplateService(self._project().connection).choices()
        value["project_settings"] = ProjectDefaultsService(self._project()).details()
        value["applications"] = self.snapshot()["choices"]["applications"]
        value["documents"] = [dict(row) for row in self._project().connection.execute(
            "SELECT id,original_filename,format FROM documents WHERE deleted_at IS NULL ORDER BY created_at DESC")]
        return value

    def mail_connect(self, client_path):
        return MailService(self._project()).connect_gmail(client_path)

    def mail_disconnect(self, account_id):
        return MailService(self._project()).disconnect(account_id)

    def mail_save_draft(self, **options):
        return MailService(self._project()).save_draft(**options)

    def mail_sync_draft(self, draft_id):
        return MailService(self._project()).sync_draft(draft_id)

    def mail_save_signature(self, **options):
        return MailService(self._project()).save_signature(**options)

    def mail_prepare_job(self, **options):
        return MailService(self._project()).prepare_job(**options)

    def mail_approve(self, **options):
        return MailService(self._project()).approve(**options)

    def mail_cancel(self, job_id):
        return MailService(self._project()).cancel(job_id)

    def mail_send(self, job_id, send_now=False):
        return MailService(self._project()).send_job(job_id, send_now=send_now)

    def mail_approve_and_send(self, job_id, confirm_overdue=False):
        return MailService(self._project()).approve_and_send(job_id, confirm_overdue=confirm_overdue)

    def mail_reconcile(self, job_id):
        return MailService(self._project()).reconcile(job_id)

    def mail_retry(self, job_id):
        return MailService(self._project()).retry_failed(job_id)

    def mail_due(self, max_jobs=1):
        return MailService(self._project()).process_due(max_jobs=max_jobs, cancelled=self.cancel_requested)

    def mail_mark_overdue(self):
        return MailService(self._project()).mark_overdue()
