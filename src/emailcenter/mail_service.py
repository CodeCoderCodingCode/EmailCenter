"""Local drafts, immutable delivery jobs, approvals, scheduling and reconciliation."""

from .language import translate as _ui_tr, format_text as _ui_format

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
from uuid import uuid4

from .credentials import WindowsTokenStore
from .gmail import GmailProvider, ProviderError, authorize_desktop
from .mail_models import MailError, address, build_message, header, parse_time, recipients, schedule_time, utc_string


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _hash(content):
    return hashlib.sha256(content).hexdigest()


@contextmanager
def _transaction(db):
    if db.in_transaction:
        raise MailError(_ui_tr('Die laufende Transaktion zuerst abschließen.'))
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


class MailService:
    def __init__(self, project, *, token_store=None, provider_factory=None, now=None):
        self.project, self.db = project, project.connection
        self.tokens = token_store or WindowsTokenStore(project.project_id)
        self.provider_factory = provider_factory
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _timestamp(self):
        return utc_string(self.now())

    def _account(self, account_id):
        row = self.db.execute("SELECT * FROM email_provider_accounts WHERE id=? AND deleted_at IS NULL AND is_enabled=1", (account_id,)).fetchone()
        if row is None or row["provider"] != "gmail":
            raise MailError(_ui_tr('Ein verbundenes Gmail-Konto auswählen.'))
        return dict(row)

    def _provider(self, account):
        if self.provider_factory:
            return self.provider_factory(account)
        info = self.tokens.get(account["id"])
        if info is None:
            raise ProviderError(_ui_tr('Gmail-Konto erneut verbinden.'), code='credentials')
        return GmailProvider(info, persist=lambda info: self.tokens.put(account["id"], info))

    def connect_gmail(self, client_path):
        info = authorize_desktop(client_path)
        email = GmailProvider(info).profile()
        return self.register_account(email, info)

    def register_account(self, email, credential_info):
        email = address(email)
        existing = self.db.execute("SELECT id FROM email_provider_accounts WHERE provider='gmail' AND account_email=? COLLATE NOCASE", (email,)).fetchone()
        identifier = existing["id"] if existing else str(uuid4())
        try:
            previous = self.tokens.get(identifier)
        except MailError:
            previous = None
        self.tokens.put(identifier, credential_info)
        try:
            with _transaction(self.db):
                now = self._timestamp()
                if existing:
                    self.db.execute("UPDATE email_provider_accounts SET is_enabled=1,deleted_at=NULL,updated_at=? WHERE id=?", (now, identifier))
                else:
                    self.db.execute("INSERT INTO email_provider_accounts(id,provider,account_email,created_at,updated_at) VALUES(?,'gmail',?,?,?)", (identifier, email, now, now))
        except BaseException:
            if previous is None:
                self.tokens.delete(identifier)
            else:
                self.tokens.put(identifier, previous)
            raise
        return self._account(identifier)

    def disconnect(self, account_id):
        self._account(account_id)
        self.tokens.delete(account_id)
        with _transaction(self.db):
            self.db.execute("UPDATE email_provider_accounts SET is_enabled=0,updated_at=? WHERE id=?", (self._timestamp(), account_id))
            self.db.execute("UPDATE email_jobs SET approval_status='pending',requires_overdue_confirmation=1,updated_at=? WHERE provider_account_id=? AND status IN ('Scheduled','Queued')", (self._timestamp(), account_id))

    def _reference(self, table, identifier):
        if identifier and self.db.execute(f"SELECT 1 FROM {table} WHERE id=? AND deleted_at IS NULL", (identifier,)).fetchone() is None:
            raise MailError(_ui_tr('Der ausgewählte verknüpfte Datensatz fehlt.'))

    def save_signature(self, name, content_text, content_html="", signature_id=None, expected_version=None, is_default=None):
        name = header(name, _ui_tr('Signaturname'))
        if not isinstance(content_text, str) or not isinstance(content_html, str) or max(len(content_text), len(content_html)) > 100_000:
            raise MailError(_ui_tr('Ungültige oder zu lange Signatur.'))
        identifier, now = signature_id or str(uuid4()), self._timestamp()
        if is_default is not None and type(is_default) is not bool:
            raise MailError(_ui_tr('Ungültige Standardsignatur.'))
        with _transaction(self.db):
            if signature_id:
                self._reference("email_signatures", signature_id)
                if expected_version is not None:
                    from .record_service import fingerprint
                    current = dict(self.db.execute("SELECT * FROM email_signatures WHERE id=?",(signature_id,)).fetchone())
                    if fingerprint(current) != expected_version:
                        raise MailError(_ui_tr('Signatur zwischenzeitlich geändert. Verwaltung aktualisieren.'))
                self.db.execute("UPDATE email_signatures SET name=?,content_text=?,content_html=?,updated_at=? WHERE id=?", (name, content_text, content_html, now, identifier))
            else:
                self.db.execute("INSERT INTO email_signatures(id,name,content_text,content_html,created_at,updated_at) VALUES(?,?,?,?,?,?)", (identifier, name, content_text, content_html, now, now))
            if is_default is not None:
                if is_default:
                    self.db.execute('UPDATE email_signatures SET is_default=0,updated_at=? WHERE is_default=1 AND id<>?',(now,identifier))
                self.db.execute('UPDATE email_signatures SET is_default=? WHERE id=?',(int(is_default),identifier))
            from .database.repositories import _write_activity
            _write_activity(self.db,'signature.saved','email_signatures',identifier,'Signatur gespeichert.',{},now)
        return identifier

    def _copy_attachments(self, attachments, directory):
        if not isinstance(attachments, list) or len(attachments) > 20:
            raise MailError(_ui_tr('Höchstens 20 Anhänge auswählen.'))
        copied = []
        try:
            self._capture_attachments(attachments, directory, copied)
        except BaseException:
            self._cleanup_files(copied)
            raise
        return copied

    def _capture_attachments(self, attachments, directory, copied):
        total = 0
        for index, item in enumerate(attachments):
            if not isinstance(item, dict):
                raise MailError(_ui_tr('Ungültiger Anhang.'))
            document_id = item.get("document_id")
            if document_id and not item.get("stored_path"):
                row = self.db.execute("SELECT file_path,original_filename FROM documents WHERE id=? AND deleted_at IS NULL", (document_id,)).fetchone()
                if row is None:
                    raise MailError(_ui_tr('Angehängtes Dokument fehlt.'))
                source, filename = self.project.file_path(row["file_path"]), row["original_filename"]
            else:
                source = self.project.file_path(item["stored_path"]) if item.get("stored_path") else Path(item.get("path", ""))
                filename = item.get("filename") or source.name
            if not source.is_file() or not filename or Path(filename).name != filename or any(c in filename for c in "\r\n\x00"):
                raise MailError(_ui_tr('Anhang fehlt oder hat einen ungültigen Dateinamen.'))
            total += source.stat().st_size
            if total > 20 * 1024 * 1024:
                raise MailError(_ui_tr('Anhänge dürfen zusammen höchstens 20 MiB groß sein.'))
            relative = Path(directory) / f"{index:02d}" / filename
            if len(str(self.project.path / relative)) > 240:
                # Keep the public attachment name unchanged. Use a short internal
                # path on Windows when project + UUID directories exceed MAX_PATH.
                bucket = _hash((Path(directory).as_posix() + '/' + str(index)).encode('utf-8'))[:24]
                relative = Path('documents') / bucket / filename
                if len(str(self.project.path / relative).encode('utf-16-le')) // 2 > 258:
                    raise MailError(_ui_tr('Projektpfad und Dateiname sind für Windows zu lang. Projekt in einen kürzeren Ordner legen oder einen kürzeren Anhangnamen wählen.'))
            target = self.project.file_path(relative, create_parent=True)
            # Read once: captured bytes become the snapshot even if the source later changes.
            with source.open("rb") as stream:
                content = stream.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024 or sum(entry["size"] for entry in copied) + len(content) > 20 * 1024 * 1024:
                raise MailError(_ui_tr('Anhänge überschreiten das Größenlimit.'))
            if item.get("stored_path") and item.get("hash") and _hash(content) != item["hash"]:
                raise MailError(_ui_tr('Ein gespeicherter Entwurfsanhang wurde verändert. Datei erneut auswählen.'))
            copied.append({"path": relative.as_posix(), "filename": filename, "hash": _hash(content),
                           "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
                           "document_id": document_id, "size": len(content)})
            target.write_bytes(content)
            if item.get('cid'):
                import re
                cid=item['cid']
                if not isinstance(cid,str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,200}',cid):
                    raise MailError(_ui_tr('Ungültige Inline-Bildkennung.'))
                copied[-1]['cid']=cid

    def _cleanup_files(self, entries):
        for entry in entries:
            self.project.file_path(entry["path"]).unlink(missing_ok=True)

    def save_draft(self, *, subject, body, recipients_value, provider_account_id=None, application_id=None,
                   signature_id=None, body_format="plain", attachments=None, draft_id=None):
        subject, targets = header(subject, _ui_tr('Betreff')), recipients(recipients_value)
        if not isinstance(body, str) or not body.strip() or len(body) > 1_000_000 or body_format not in ("plain", "html"):
            raise MailError(_ui_tr('Nachrichtentext fehlt, ist zu lang oder hat ein ungültiges Format.'))
        if provider_account_id:
            self._account(provider_account_id)
        self._reference("applications", application_id)
        self._reference("email_signatures", signature_id)
        old = self.draft(draft_id) if draft_id else None
        identifier, now = draft_id or str(uuid4()), self._timestamp()
        copied = []
        try:
            if attachments is not None:
                copied = self._copy_attachments(attachments, Path("exports/mail/drafts") / identifier / str(uuid4()))
                config = {"attachments": copied}
            else:
                config = old["configuration"] if old else {"attachments": []}
            with _transaction(self.db):
                if old:
                    remote_id = old["provider_draft_id"] if old["provider_account_id"] == provider_account_id else None
                    self.db.execute("UPDATE email_drafts SET provider_account_id=?,application_id=?,signature_id=?,subject=?,body=?,body_format=?,recipients_json=?,configuration_json=?,provider_draft_id=?,synced_hash=NULL,updated_at=? WHERE id=?",
                                    (provider_account_id, application_id, signature_id, subject, body, body_format, _json(targets), _json(config), remote_id, now, identifier))
                else:
                    self.db.execute("INSERT INTO email_drafts(id,provider_account_id,application_id,signature_id,subject,body,body_format,recipients_json,configuration_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                    (identifier, provider_account_id, application_id, signature_id, subject, body, body_format, _json(targets), _json(config), now, now))
        except BaseException:
            self._cleanup_files(copied)
            raise
        return self.draft(identifier)

    def draft(self, identifier):
        row = self.db.execute("SELECT * FROM email_drafts WHERE id=? AND deleted_at IS NULL", (identifier,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('E-Mail-Entwurf nicht gefunden.'))
        value = dict(row)
        value["recipients"] = json.loads(value["recipients_json"])
        value["configuration"] = json.loads(value["configuration_json"])
        return value

    def _draft_values(self, draft):
        account = self._account(draft["provider_account_id"])
        body = draft["body"]
        self._reference("applications", draft["application_id"])
        if draft["signature_id"]:
            self._reference("email_signatures", draft["signature_id"])
            signature = self.db.execute("SELECT * FROM email_signatures WHERE id=?", (draft["signature_id"],)).fetchone()
            if draft["body_format"] == "html":
                import html
                body += "<br><br>" + (signature["content_html"] or html.escape(signature["content_text"]).replace("\n", "<br>"))
            else:
                body += "\n\n" + signature["content_text"]
        return account, recipients(draft["recipients"]), header(draft["subject"], _ui_tr('Betreff')), body

    def _attachment_bytes(self, entries):
        result, total = [], 0
        for entry in entries:
            path = self.project.file_path(entry["path"])
            with path.open("rb") as stream:
                content = stream.read(20 * 1024 * 1024 + 1)
            total += len(content)
            if total > 20 * 1024 * 1024 or _hash(content) != entry["hash"]:
                raise MailError(_ui_tr('Ein gespeicherter Anhang wurde verändert oder überschreitet das Limit.'))
            result.append((entry['filename'],entry['mime_type'],content,*((entry['cid'],) if entry.get('cid') else ())))
        return result

    def sync_draft(self, draft_id):
        draft = self.draft(draft_id)
        account, targets, subject, body = self._draft_values(draft)
        content = build_message(account["account_email"], targets, subject, body, draft["body_format"],
                                f"<draft-{draft_id}@emailcenter.local>", draft["created_at"], self._attachment_bytes(draft["configuration"]["attachments"]))
        provider = self._provider(account)
        if provider.profile().casefold() != account["account_email"].casefold():
            raise MailError(_ui_tr('Gmail-Zugang gehört zu einem anderen Konto. Neu verbinden.'))
        remote_id = provider.save_draft(content, draft["provider_draft_id"])
        self.db.execute("UPDATE email_drafts SET provider_draft_id=?,synced_hash=? WHERE id=?", (remote_id, _hash(content), draft_id))
        return self.draft(draft_id)

    def prepare_job(self, draft_id, *, scheduled_local=None, timezone_id="Europe/Berlin", provider_account_id=None, dispatch_id=None):
        draft = self.draft(draft_id)
        previous_account_id = draft["provider_account_id"]
        if provider_account_id is not None:
            draft["provider_account_id"] = provider_account_id
        account, targets, subject, body = self._draft_values(draft)
        scheduled = schedule_time(scheduled_local, timezone_id) if scheduled_local else None
        if scheduled and parse_time(scheduled) <= self.now():
            raise MailError(_ui_tr('Für einen neuen geplanten Auftrag einen zukünftigen Zeitpunkt wählen.'))
        # Validate timezone even for immediate jobs.
        schedule_time(self._timestamp(), timezone_id)
        identifier, now = str(uuid4()), self._timestamp()
        message_id = f"<{identifier}@emailcenter.local>"
        entries, payload_path = [], None
        try:
            original = draft["configuration"]["attachments"]
            self._attachment_bytes(original)
            entries = self._copy_attachments([{"path": str(self.project.file_path(item["path"])), "filename": item["filename"]} for item in original], Path("exports/mail/jobs") / identifier / "attachments")
            for original_entry, copy in zip(original, entries):
                if original_entry["hash"] != copy["hash"]:
                    raise MailError(_ui_tr('Ein Anhang wurde beim Vorbereiten geändert.'))
                copy["document_id"] = original_entry.get("document_id")
                if original_entry.get('cid'):copy['cid']=original_entry['cid']
            raw = build_message(account["account_email"], targets, subject, body, draft["body_format"], message_id, now, self._attachment_bytes(entries))
            relative = f"exports/mail/jobs/{identifier}/message.eml"
            payload_path = self.project.file_path(relative, create_parent=True)
            payload_path.write_bytes(raw)
            with _transaction(self.db):
                batch_id = None
                if dispatch_id:
                    dispatch = self.db.execute(
                        "SELECT d.batch_id FROM email_bulk_dispatches d JOIN email_bulk_dispatch_items i ON i.dispatch_id=d.id "
                        "WHERE d.id=? AND d.status='Preparing' AND i.draft_id=? AND i.job_id IS NULL", (dispatch_id, draft_id)).fetchone()
                    if dispatch is None:
                        raise MailError(_ui_tr('Dieser Gruppenauftrag wurde bereits vorbereitet oder gestoppt.'))
                    batch_id = dispatch["batch_id"]
                    configuration = self.db.execute("SELECT * FROM email_bulk_dispatches WHERE id=?", (dispatch_id,)).fetchone()
                    if configuration["provider_account_id"] != account["id"] or configuration["timezone_id"] != timezone_id or configuration["scheduled_local"] != scheduled_local:
                        raise MailError(_ui_tr('Versandkopie stimmt nicht mit der Gruppenplanung überein.'))
                if draft["provider_account_id"] != previous_account_id:
                    self.db.execute(
                        "UPDATE email_drafts SET provider_account_id=?,provider_draft_id=NULL,synced_hash=NULL,updated_at=? WHERE id=?",
                        (draft["provider_account_id"], now, draft_id),
                    )
                self.db.execute("INSERT INTO email_jobs(id,draft_id,application_id,provider_account_id,recipients_snapshot_json,subject_snapshot,body_snapshot,body_format,scheduled_at_utc,timezone_id,status,idempotency_key,created_at,updated_at,sender_snapshot,message_id_snapshot,payload_file_path,payload_hash) VALUES(?,?,?,?,?,?,?,?,?,?,'Draft',?,?,?,?,?,?,?)",
                                (identifier, draft_id, draft["application_id"], account["id"], _json(targets), subject, body, draft["body_format"], scheduled, timezone_id, identifier, now, now, account["account_email"], message_id, relative, _hash(raw)))
                if dispatch_id:
                    self.db.execute("UPDATE email_jobs SET batch_id=? WHERE id=?", (batch_id, identifier))
                    self.db.execute("UPDATE email_bulk_dispatch_items SET job_id=? WHERE dispatch_id=? AND draft_id=?", (identifier, dispatch_id, draft_id))
                for index, entry in enumerate(entries):
                    self.db.execute("INSERT INTO email_attachments(id,email_job_id,document_id,file_path_snapshot,filename_snapshot,mime_type_snapshot,file_hash_snapshot,sort_order,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                    (str(uuid4()), identifier, entry["document_id"], entry["path"], entry["filename"], entry["mime_type"], entry["hash"], index, now))
            return self.job(identifier)
        except BaseException:
            self._cleanup_files(entries)
            if payload_path:
                payload_path.unlink(missing_ok=True)
            raise

    def job(self, identifier):
        row = self.db.execute("SELECT * FROM email_jobs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Versandauftrag nicht gefunden.'))
        value = dict(row)
        dispatch = self.db.execute("SELECT dispatch_id FROM email_bulk_dispatch_items WHERE job_id=?", (identifier,)).fetchone()
        value["bulk_dispatch_id"] = dispatch[0] if dispatch else None
        value["recipients"] = json.loads(value["recipients_snapshot_json"])
        value["attachments"] = [dict(row) for row in self.db.execute("SELECT * FROM email_attachments WHERE email_job_id=? ORDER BY sort_order,id", (identifier,))]
        value["attempts"] = [dict(row) for row in self.db.execute("SELECT * FROM email_attempts WHERE email_job_id=? ORDER BY attempt_number", (identifier,))]
        return value

    def _payload(self, job):
        if not all(job.get(key) for key in ("sender_snapshot", "message_id_snapshot", "payload_file_path", "payload_hash")):
            raise MailError(_ui_tr('Dieser ältere Auftrag hat keinen vollständigen Versand-Snapshot. Neu vorbereiten.'))
        path = self.project.file_path(job["payload_file_path"])
        with path.open("rb") as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024 or _hash(raw) != job["payload_hash"]:
            raise MailError(_ui_tr('Die gespeicherte Versandnachricht wurde verändert. Auftrag neu vorbereiten.'))
        for entry in job["attachments"]:
            self._attachment_bytes([{"path": entry["file_path_snapshot"], "hash": entry["file_hash_snapshot"], "filename": entry["filename_snapshot"], "mime_type": entry["mime_type_snapshot"]}])
        return raw

    def approve(self, job_id, *, confirm_overdue=False):
        with _transaction(self.db):
            self._approve(job_id, confirm_overdue=confirm_overdue)
        return self.job(job_id)

    def _approve(self, job_id, *, confirm_overdue=False, allow_retry=False):
        """Validate and write within the caller's transaction (also used by bulk approval)."""
        job = self.job(job_id)
        if job["status"] not in ("Draft", "Scheduled", "Queued") or (job["attempt_count"] and not (allow_retry and job["attempts"] and job["attempts"][-1]["result"] == "Failed")):
            raise MailError(_ui_tr('Dieser Auftrag kann nicht freigegeben werden.'))
        self._account(job["provider_account_id"])
        self._payload(job)
        if job["requires_overdue_confirmation"] and not confirm_overdue:
            raise MailError(_ui_tr('Überfälligen Auftrag ausdrücklich für den Nachversand bestätigen.'))
        status = "Scheduled" if job["scheduled_at_utc"] and parse_time(job["scheduled_at_utc"]) > self.now() else "Queued"
        proof = {"approved_at": self._timestamp(), "payload_hash": job["payload_hash"], "confirmed_overdue": bool(confirm_overdue)}
        self.db.execute("UPDATE email_jobs SET status=?,approval_status='approved',approval_snapshot_json=?,requires_overdue_confirmation=0,updated_at=? WHERE id=?", (status, _json(proof), self._timestamp(), job_id))

    def cancel(self, job_id):
        with _transaction(self.db):
            job = self.job(job_id)
            if job["status"] not in ("Draft", "Scheduled", "Queued", "Failed"):
                raise MailError(_ui_tr('Laufende, versendete oder unklare Aufträge können nicht storniert werden.'))
            self.db.execute("UPDATE email_jobs SET status='Cancelled',approval_status='rejected',cancelled_at_utc=?,updated_at=? WHERE id=?", (self._timestamp(), self._timestamp(), job_id))
        return self.job(job_id)

    def recover(self):
        """On open, interrupt uncertain jobs and require a new approval for overdue work."""
        now = self._timestamp()
        with _transaction(self.db):
            self.db.execute("UPDATE email_attempts SET result='Uncertain',finished_at_utc=?,error_code='interrupted',error_message='App während Versand beendet.' WHERE result='Started' AND email_job_id IN (SELECT id FROM email_jobs WHERE status='Sending')", (now,))
            self.db.execute("UPDATE email_jobs SET status='ReconciliationRequired',last_error_code='interrupted',last_error_message='Versand nach Neustart abgleichen.',updated_at=? WHERE status='Sending'", (now,))
            self.db.execute("UPDATE email_bulk_dispatches SET status='Paused',last_error='Nach Neustart prüfen und ausdrücklich fortsetzen.',updated_at=? WHERE status='Running'", (now,))
            self.mark_overdue(in_transaction=True)

    def mark_overdue(self, *, in_transaction=False):
        def update():
            self.db.execute("UPDATE email_jobs SET requires_overdue_confirmation=1,approval_status='pending',updated_at=? WHERE status IN ('Scheduled','Queued') AND (scheduled_at_utc IS NULL OR scheduled_at_utc<=?)", (self._timestamp(), self._timestamp()))
        if in_transaction:
            update()
        else:
            with _transaction(self.db):
                update()

    def approve_and_send(self, job_id, *, confirm_overdue=False):
        job = self.job(job_id)
        if job["status"] == "Failed":
            self.retry_failed(job_id)
        else:
            self.approve(job_id, confirm_overdue=confirm_overdue)
        try:
            return self.send_job(job_id, send_now=True)
        except Exception as error:
            # Preflight failures must not leave a scheduled job approved for a
            # later automatic attempt. Sending/uncertain states are preserved.
            with _transaction(self.db):
                self.db.execute(
                    "UPDATE email_jobs SET approval_status='pending',last_error_code='preflight',last_error_message=?,updated_at=? WHERE id=? AND status IN ('Queued','Scheduled')",
                    (str(error) if isinstance(error, MailError) else "Vorprüfung fehlgeschlagen.", self._timestamp(), job_id),
                )
            raise

    def send_job(self, job_id, *, send_now=False, dispatch_id=None):
        if not isinstance(send_now, bool):
            raise MailError(_ui_tr('Sofortversand muss ausdrücklich gewählt werden.'))
        job = self.job(job_id)
        if job["status"] == "Sent":
            return job
        dispatch = self.db.execute("SELECT d.id,d.status FROM email_bulk_dispatches d JOIN email_bulk_dispatch_items i ON i.dispatch_id=d.id WHERE i.job_id=?", (job_id,)).fetchone()
        if dispatch and (dispatch["status"] != "Running" or dispatch["id"] != dispatch_id):
            raise MailError(_ui_tr('Gruppenversand ist gestoppt. In der Gruppe prüfen und fortsetzen.'))
        if job["status"] not in ("Queued", "Scheduled") or job["approval_status"] != "approved" or job["requires_overdue_confirmation"]:
            raise MailError(_ui_tr('Auftrag zuerst prüfen und freigeben. Unklare Ergebnisse müssen abgeglichen werden.'))
        if job["scheduled_at_utc"] and parse_time(job["scheduled_at_utc"]) > self.now() and not send_now:
            raise MailError(_ui_tr('Der geplante Versandzeitpunkt ist noch nicht erreicht.'))
        raw = self._payload(job)
        proof = json.loads(job["approval_snapshot_json"])
        if proof.get("payload_hash") != job["payload_hash"]:
            raise MailError(_ui_tr('Freigabe gehört nicht zur gespeicherten Nachricht.'))
        account = self._account(job["provider_account_id"])
        hold = self.db.execute("SELECT until_utc FROM email_account_holds WHERE account_id=?", (account["id"],)).fetchone()
        if hold and parse_time(hold[0]) > self.now():
            raise MailError(_ui_format('Anbietersperre bis {0}. Danach erneut prüfen.', hold[0]))
        provider = self._provider(account)
        try:
            profile = provider.profile()
        except ProviderError as error:
            if error.retry_after:
                self._provider_hold(account["id"], error)
            raise
        if profile.casefold() != job["sender_snapshot"].casefold():
            raise MailError(_ui_tr('Gmail-Zugang gehört zu einem anderen Absender. Konto neu verbinden.'))
        attempt_id, attempt_number = str(uuid4()), job["attempt_count"] + 1
        with _transaction(self.db):
            changed = self.db.execute("UPDATE email_jobs SET status='Sending',attempt_count=attempt_count+1,updated_at=? WHERE id=? AND status IN ('Queued','Scheduled') AND approval_status='approved' AND requires_overdue_confirmation=0 AND attempt_count=?", (self._timestamp(), job_id, job["attempt_count"]))
            if dispatch:
                from .delivery_policy import policy_wait
                policy = dict(self.db.execute("SELECT * FROM email_bulk_dispatches WHERE id=?", (dispatch["id"],)).fetchone())
                if policy_wait(self.db, policy, self.now())["wait_until"]:
                    raise MailError(_ui_tr('Tagesbudget, Versandfenster oder Anbietersperre noch nicht erreicht.'))
            if changed.rowcount != 1:
                raise MailError(_ui_tr('Auftrag wird bereits verarbeitet oder wurde geändert.'))
            self.db.execute("INSERT INTO email_attempts(id,email_job_id,attempt_number,started_at_utc,result) VALUES(?,?,?,?,'Started')", (attempt_id, job_id, attempt_number, self._timestamp()))
        try:
            message_id = provider.send(raw)
            if not isinstance(message_id, str) or not message_id:
                raise ProviderError(_ui_tr('Versand konnte nicht bestätigt werden.'), code='response', uncertain=True)
        except Exception as error:
            uncertain = not isinstance(error, ProviderError) or error.uncertain
            status, result = ("Uncertain", "Uncertain") if uncertain else ("Failed", "Failed")
            code = error.code if isinstance(error, ProviderError) else "unexpected_provider_error"
            message = str(error) if isinstance(error, ProviderError) else "Versandresultat ist unklar. Vor weiterem Versand abgleichen."
            with _transaction(self.db):
                self.db.execute("UPDATE email_attempts SET result=?,finished_at_utc=?,error_code=?,error_message=? WHERE id=?", (result, self._timestamp(), code, message, attempt_id))
                if isinstance(error, ProviderError) and error.retry_after:
                    self._provider_hold(account["id"], error)
                self.db.execute("UPDATE email_jobs SET status=?,approval_status='pending',last_error_code=?,last_error_message=?,updated_at=? WHERE id=?", (status, code, message, self._timestamp(), job_id))
            return self.job(job_id)
        self._finish_sent(job_id, attempt_id, message_id, reconciled=False)
        return self.job(job_id)

    def _provider_hold(self, account_id, error):
        from datetime import timedelta
        until = utc_string(self.now() + timedelta(seconds=max(10, min(604800, error.retry_after))))
        self.db.execute("INSERT INTO email_account_holds VALUES(?,?,?) ON CONFLICT(account_id) DO UPDATE SET until_utc=MAX(until_utc,excluded.until_utc),reason=excluded.reason", (account_id, until, error.code))

    def _finish_sent(self, job_id, attempt_id, provider_id, *, reconciled):
        now = self._timestamp()
        scheduled = self.job(job_id)["scheduled_at_utc"]
        before_schedule = bool(scheduled and parse_time(scheduled) > parse_time(now))
        with _transaction(self.db):
            self.db.execute("UPDATE email_attempts SET result=?,provider_message_id=?,finished_at_utc=?,reconciliation_json=? WHERE id=?", ("Reconciled" if reconciled else "Sent", provider_id, now, _json({"confirmed_sent": True}) if reconciled else "{}", attempt_id))
            self.db.execute("UPDATE email_jobs SET status='Sent',provider_message_id=?,sent_at_utc=?,last_error_code=NULL,last_error_message=NULL,updated_at=? WHERE id=?", (provider_id, now, now, job_id))
            self.db.execute("INSERT INTO activity_log(id,event_type,entity_type,entity_id,message,details_json,created_at) VALUES(?,'email_sent','email_job',?,'Gmail-Versand bestätigt.',?,?)", (str(uuid4()), job_id, _json({"provider_message_id": provider_id, "reconciled": reconciled, "sent_before_schedule": before_schedule}), now))

    def reconcile(self, job_id):
        job = self.job(job_id)
        if job["status"] not in ("Uncertain", "ReconciliationRequired") or not job["attempts"]:
            raise MailError(_ui_tr('Nur unklare Versandaufträge können abgeglichen werden.'))
        account = self._account(job["provider_account_id"])
        provider = self._provider(account)
        if provider.profile().casefold() != job["sender_snapshot"].casefold():
            raise MailError(_ui_tr('Für den Abgleich das ursprüngliche Gmail-Konto verbinden.'))
        matches = provider.find_sent(job["message_id_snapshot"])
        valid = [match for match in matches if match.get("message_id") == job["message_id_snapshot"]]
        attempt_id = job["attempts"][-1]["id"]
        if len(valid) == 1:
            self._finish_sent(job_id, attempt_id, valid[0]["id"], reconciled=True)
        else:
            with _transaction(self.db):
                self.db.execute("UPDATE email_jobs SET status='ReconciliationRequired',last_error_code='reconciliation_pending',last_error_message=?,updated_at=? WHERE id=?", ("Kein eindeutiger Versandbeleg. Später erneut abgleichen; nicht erneut senden.", self._timestamp(), job_id))
                self.db.execute("UPDATE email_attempts SET reconciliation_json=? WHERE id=?", (_json({"checked_at": self._timestamp(), "match_count": len(valid)}), attempt_id))
        return self.job(job_id)

    def retry_failed(self, job_id):
        with _transaction(self.db):
            job = self.job(job_id)
            if job["status"] != "Failed" or not job["attempts"] or job["attempts"][-1]["result"] != "Failed":
                raise MailError(_ui_tr('Nur eindeutig fehlgeschlagene Versuche können erneut freigegeben werden.'))
            self._payload(job)
            self.db.execute("UPDATE email_jobs SET status='Queued',approval_status='approved',approval_snapshot_json=?,requires_overdue_confirmation=0,updated_at=? WHERE id=?", (_json({"approved_at": self._timestamp(), "payload_hash": job["payload_hash"], "retry": True}), self._timestamp(), job_id))
        return self.job(job_id)

    def process_due(self, *, max_jobs=5, cancelled=lambda: False):
        if not 1 <= max_jobs <= 20:
            raise MailError(_ui_tr('Ungültige Versandstapelgröße.'))
        rows = self.db.execute("SELECT id FROM email_jobs WHERE status IN ('Scheduled','Queued') AND approval_status='approved' AND requires_overdue_confirmation=0 AND scheduled_at_utc IS NOT NULL AND scheduled_at_utc<=? AND NOT EXISTS (SELECT 1 FROM email_bulk_dispatch_items i WHERE i.job_id=email_jobs.id) ORDER BY scheduled_at_utc,created_at LIMIT ?", (self._timestamp(), max_jobs)).fetchall()
        results = []
        for row in rows:
            if cancelled():
                break
            try:
                result = self.send_job(row["id"])
                results.append({"id": result["id"], "status": result["status"]})
            except Exception as error:
                # Errors before POST leave the job unsent and require manual intervention.
                with _transaction(self.db):
                    self.db.execute("UPDATE email_jobs SET approval_status='pending',last_error_code='preflight',last_error_message=?,updated_at=? WHERE id=? AND status IN ('Queued','Scheduled')", (str(error) if isinstance(error, MailError) else "Vorprüfung fehlgeschlagen.", self._timestamp(), row["id"]))
                results.append({"id": row["id"], "status": "NeedsApproval"})
        return results

    def snapshot(self, *, draft_offset=0, job_offset=0, limit=50):
        if min(draft_offset, job_offset) < 0 or not 1 <= limit <= 100:
            raise MailError(_ui_tr('Ungültige E-Mail-Listenanfrage.'))
        drafts = [self.draft(row["id"]) for row in self.db.execute("SELECT id FROM email_drafts WHERE deleted_at IS NULL ORDER BY updated_at DESC,rowid DESC LIMIT ? OFFSET ?", (limit, draft_offset))]
        jobs = [self.job(row["id"]) for row in self.db.execute("SELECT id FROM email_jobs ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?", (limit, job_offset))]
        return {"accounts": [dict(row) for row in self.db.execute("SELECT * FROM email_provider_accounts WHERE deleted_at IS NULL ORDER BY account_email")],
                "signatures": [dict(row) for row in self.db.execute("SELECT * FROM email_signatures WHERE deleted_at IS NULL ORDER BY name")],
                "drafts": drafts, "jobs": jobs, "draft_offset": draft_offset, "job_offset": job_offset, "limit": limit,
                "draft_total": self.db.execute("SELECT COUNT(*) FROM email_drafts WHERE deleted_at IS NULL").fetchone()[0],
                "job_total": self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0]}
