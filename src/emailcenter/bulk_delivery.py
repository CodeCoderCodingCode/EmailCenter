"""Durable, explicitly approved bulk delivery; one committed job per UI step."""

from .language import translate as _ui_tr, format_text as _ui_format

from datetime import timedelta
from uuid import uuid4

from .database.repositories import _write_activity
from .mail_bulk import BulkMailService, digest
from .mail_models import MailError, parse_time, schedule_time, utc_string
from .mail_service import MailService, _transaction
from .delivery_policy import validate_policy, policy_wait


PENDING = ("Draft", "Queued", "Scheduled")
BLOCKED = ("Failed", "Uncertain", "ReconciliationRequired", "Sending")


class BulkDeliveryService:
    def __init__(self, project, *, mail=None):
        self.project, self.db = project, project.connection
        self.mail = mail or MailService(project)

    def _repeated_recipients_allowed(self, batch):
        """Only an explicit choice in every immutable builder row permits repeats."""
        def opted_in(item):
            graph = item.get('source_snapshot', {}).get('builder_graph', {})
            sources = [n for n in graph.get('nodes', []) if n.get('kind') == 'data']
            return item.get('recipient_reuse_allowed') == 1 and len(sources) == 1 and sources[0].get('config', {}).get('allow_duplicate_recipients') is True
        return bool(batch['items']) and all(opted_in(item) for item in batch['items'])

    def details(self, batch_id):
        batch = BulkMailService(self.project).batch(batch_id)
        row = self.db.execute("SELECT id FROM email_bulk_dispatches WHERE batch_id=?", (batch_id,)).fetchone()
        return {"batch": batch, "allow_duplicate_recipients": self._repeated_recipients_allowed(batch), "dispatch": self.snapshot(row[0]) if row else None,
                "drafts": [self.mail.draft(item["draft_id"]) for item in batch["items"] if not item["deleted_at"]],
                "accounts": [dict(r) for r in self.db.execute(
                    "SELECT id,account_email FROM email_provider_accounts WHERE deleted_at IS NULL AND is_enabled=1 AND provider='gmail'")]}

    def snapshot(self, dispatch_id):
        row = self.db.execute("SELECT * FROM email_bulk_dispatches WHERE id=?", (dispatch_id,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Gruppenversand nicht gefunden.'))
        items = []
        for record in self.db.execute(
                "SELECT i.*,b.name_snapshot FROM email_bulk_dispatch_items i "
                "JOIN email_bulk_dispatches d ON d.id=i.dispatch_id "
                "JOIN email_draft_batch_items b ON b.batch_id=d.batch_id AND b.draft_id=i.draft_id "
                "WHERE i.dispatch_id=? ORDER BY i.position", (dispatch_id,)):
            items.append({**dict(record), "job": self.mail.job(record["job_id"]) if record["job_id"] else None})
        counts = {"total": len(items), "prepared": 0, "sent": 0, "cancelled": 0, "blocked": 0, "pending": 0}
        for item in items:
            job = item["job"]
            if job:
                counts["prepared"] += 1
                counts["sent"] += job["status"] == "Sent"
                counts["cancelled"] += job["status"] == "Cancelled"
                counts["blocked"] += job["status"] in BLOCKED
                counts["pending"] += job["status"] in PENDING
        value = {**dict(row), "items": items, "counts": counts, 'allow_duplicate_recipients': self._repeated_recipients_allowed(BulkMailService(self.project).batch(row['batch_id']))}
        # The exact reviewed job state, approval, attempts and file hashes are bound to the approval.
        return {**value, "fingerprint": digest(value)}

    def begin(self, batch_id, provider_account_id, *, interval_seconds=2, scheduled_local=None, timezone_id="Europe/Berlin", daily_budget=100, window_start="00:00", window_end="00:00"):
        with _transaction(self.db):
            return self._begin(batch_id, provider_account_id, interval_seconds=interval_seconds, scheduled_local=scheduled_local, timezone_id=timezone_id, daily_budget=daily_budget, window_start=window_start, window_end=window_end)

    def _begin(self, batch_id, provider_account_id, *, interval_seconds=2, scheduled_local=None, timezone_id="Europe/Berlin", daily_budget=100, window_start="00:00", window_end="00:00"):
        """Insert under the caller's transaction, including atomic builder creation."""
        if not self.db.in_transaction:
            raise MailError(_ui_tr('Versandplanung benötigt eine aktive Transaktion.'))
        if type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600:
            raise MailError(_ui_tr('Versandabstand muss zwischen 1 und 3600 Sekunden liegen.'))
        account = self.mail._account(provider_account_id)
        validate_policy(daily_budget, window_start, window_end)
        scheduled = schedule_time(scheduled_local, timezone_id) if scheduled_local else None
        schedule_time(self.mail._timestamp(), timezone_id)
        if scheduled and parse_time(scheduled) <= self.mail.now():
            raise MailError(_ui_tr('Einen zukünftigen Versandzeitpunkt wählen.'))
        identifier, now = str(uuid4()), self.mail._timestamp()
        existing = self.db.execute("SELECT id FROM email_bulk_dispatches WHERE batch_id=?", (batch_id,)).fetchone()
        if existing:
            raise MailError(_ui_tr('Diese Gruppe besitzt bereits Versandkopien. Bestehenden Gruppenversand öffnen.'))
        batch = BulkMailService(self.project).batch(batch_id)
        if not batch["items"]:
            raise MailError(_ui_tr('Die Gruppe ist leer.'))
        addresses = set()
        for item in batch["items"]:
            draft = self.mail.draft(item["draft_id"])
            draft["provider_account_id"] = account["id"]
            _, targets, _, _ = self.mail._draft_values(draft)
            if len(targets["to"]) != 1 or targets["cc"] or targets["bcc"]:
                raise MailError(_ui_tr('Bulk benötigt genau einen An-Empfänger pro Nachricht, ohne Cc/Bcc.'))
            key = targets["to"][0].casefold()
            if key in addresses and not self._repeated_recipients_allowed(batch):
                raise MailError(_ui_tr('Doppelte Empfänger zuerst in den Einzelentwürfen korrigieren.'))
            addresses.add(key)
            self.mail._attachment_bytes(draft["configuration"]["attachments"])
        self.db.execute(
            "INSERT INTO email_bulk_dispatches(id,batch_id,provider_account_id,scheduled_local,timezone_id,interval_seconds,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,'Preparing',?,?)", (identifier, batch_id, account["id"], scheduled_local, timezone_id, interval_seconds, now, now))
        for position, item in enumerate(batch["items"]):
            if position == 0:
                self.db.execute("UPDATE email_bulk_dispatches SET daily_budget=?,window_start=?,window_end=? WHERE id=?", (daily_budget, window_start, window_end, identifier))
            self.db.execute("INSERT INTO email_bulk_dispatch_items(dispatch_id,draft_id,position) VALUES(?,?,?)",
                            (identifier, item["draft_id"], position))
        _write_activity(self.db, "email_bulk.preparing", "email_bulk_dispatches", identifier,
                        "Versandkopien vorbereiten; noch keine Freigabe.", {"count": len(batch["items"])}, now)
        return self.snapshot(identifier)

    def prepare_next(self, dispatch_id):
        value = self.snapshot(dispatch_id)
        if value["status"] != "Preparing":
            return value
        item = next((item for item in value["items"] if not item["job"]), None)
        if item:
            try:
                self.mail.prepare_job(item["draft_id"], provider_account_id=value["provider_account_id"],
                                      scheduled_local=value["scheduled_local"], timezone_id=value["timezone_id"], dispatch_id=dispatch_id)
            except Exception as error:
                self.db.execute("UPDATE email_bulk_dispatches SET last_error=?,updated_at=? WHERE id=?",
                                (str(error), self.mail._timestamp(), dispatch_id))
                return self.snapshot(dispatch_id)
        # Each job and its association were committed together. Restarting preparation cannot duplicate it.
        remaining = self.db.execute("SELECT COUNT(*) FROM email_bulk_dispatch_items WHERE dispatch_id=? AND job_id IS NULL", (dispatch_id,)).fetchone()[0]
        self.db.execute("UPDATE email_bulk_dispatches SET status=?,last_error=NULL,updated_at=? WHERE id=?",
                        ("Preparing" if remaining else "Ready", self.mail._timestamp(), dispatch_id))
        return self.snapshot(dispatch_id)

    def _reviewed(self, dispatch_id, expected_fingerprint):
        value = self.snapshot(dispatch_id)
        if value["fingerprint"] != expected_fingerprint:
            raise MailError(_ui_tr('Gruppenaufträge wurden geändert. Neu laden und prüfen.'))
        if value["status"] not in ("Ready", "Paused") or value["counts"]["prepared"] != value["counts"]["total"]:
            raise MailError(_ui_tr('Versandkopien zuerst vollständig vorbereiten und prüfen.'))
        if value["counts"]["blocked"]:
            raise MailError(_ui_tr('Fehlgeschlagene oder unklare Einzelaufträge zuerst bearbeiten und erneut prüfen.'))
        if not value["counts"]["pending"]:
            raise MailError(_ui_tr('Keine offenen Aufträge vorhanden.'))
        addresses = set()
        for item in value["items"]:
            job = item["job"]
            if job["status"] == "Cancelled":
                continue
            targets = job["recipients"]
            if len(targets["to"]) != 1 or targets["cc"] or targets["bcc"] or (targets["to"][0].casefold() in addresses and not value['allow_duplicate_recipients']):
                raise MailError(_ui_tr('Versandkopien enthalten doppelte oder unzulässige Empfänger. Gruppe abbrechen und korrigiert neu erstellen.'))
            addresses.add(targets["to"][0].casefold())
        return value

    def approve(self, dispatch_id, expected_fingerprint, *, confirm_overdue=False):
        with _transaction(self.db):
            value = self._reviewed(dispatch_id, expected_fingerprint)
            for item in value["items"]:
                job = item["job"]
                if job["status"] in PENDING:
                    self.mail._approve(job["id"], confirm_overdue=confirm_overdue, allow_retry=True)
            self.db.execute("UPDATE email_bulk_dispatches SET status='Paused',last_error=NULL,updated_at=? WHERE id=?",
                            (self.mail._timestamp(), dispatch_id))
            _write_activity(self.db, "email_bulk.approved", "email_bulk_dispatches", dispatch_id,
                            "Offene Einzelaufträge gemeinsam geprüft und freigegeben.", {"count": value["counts"]["pending"]}, self.mail._timestamp())
        return self.snapshot(dispatch_id)

    def start(self, dispatch_id, expected_fingerprint, background=False):
        if type(background) is not bool:
            raise MailError(_ui_tr('Hintergrundausführung ausdrücklich auswählen.'))
        with _transaction(self.db):
            value = self._reviewed(dispatch_id, expected_fingerprint)
            for item in value["items"]:
                job = item["job"]
                if job["status"] in PENDING:
                    if job["approval_status"] != "approved" or job["requires_overdue_confirmation"]:
                        raise MailError(_ui_tr('Alle offenen Gruppenaufträge zuerst ausdrücklich freigeben.'))
                    self.mail._account(job["provider_account_id"])
                    self.mail._payload(job)
            self.db.execute("UPDATE email_bulk_dispatches SET status='Running',background=?,last_error=NULL,updated_at=? WHERE id=?",
                            (int(background), self.mail._timestamp(), dispatch_id))
        return self.snapshot(dispatch_id)

    def pause(self, dispatch_id, *, require_review=False):
        with _transaction(self.db):
            self.snapshot(dispatch_id)
            self.db.execute("UPDATE email_bulk_dispatches SET status='Paused',updated_at=? WHERE id=? AND status='Running'",
                            (self.mail._timestamp(), dispatch_id))
            if require_review:
                self.db.execute("UPDATE email_jobs SET approval_status='pending',requires_overdue_confirmation=1,updated_at=? "
                                "WHERE id IN (SELECT job_id FROM email_bulk_dispatch_items WHERE dispatch_id=?) "
                                "AND status IN ('Queued','Scheduled') AND (scheduled_at_utc IS NULL OR scheduled_at_utc<=?)",
                                (self.mail._timestamp(), dispatch_id, self.mail._timestamp()))
                self.db.execute("UPDATE email_bulk_dispatches SET last_error='Längere Unterbrechung: offene fällige Nachrichten neu prüfen.' WHERE id=?", (dispatch_id,))
        return self.snapshot(dispatch_id)

    def cancel(self, dispatch_id):
        with _transaction(self.db):
            value = self.snapshot(dispatch_id)
            if value["status"] in ("Completed", "Cancelled"):
                return value
            if any(item["job"] and item["job"]["status"] == "Sending" for item in value["items"]):
                raise MailError(_ui_tr('Den laufenden Einzelversand zuerst abschließen lassen.'))
            for item in value["items"]:
                job = item["job"]
                if job and job["status"] in (*PENDING, "Failed"):
                    self.db.execute("UPDATE email_jobs SET status='Cancelled',approval_status='rejected',cancelled_at_utc=?,updated_at=? WHERE id=?",
                                    (self.mail._timestamp(), self.mail._timestamp(), job["id"]))
            self.db.execute("UPDATE email_bulk_dispatches SET status='Cancelled',updated_at=? WHERE id=?",
                            (self.mail._timestamp(), dispatch_id))
            _write_activity(self.db, "email_bulk.cancelled", "email_bulk_dispatches", dispatch_id,
                            "Offene Gruppenaufträge abgebrochen; Versandbelege bleiben erhalten.", {}, self.mail._timestamp())
        return self.snapshot(dispatch_id)

    def next(self, dispatch_id):
        value = self.snapshot(dispatch_id)
        if value["status"] != "Running":
            return value
        if value["counts"]["blocked"]:
            return self._stop(dispatch_id, "Einzelauftrag prüfen oder abgleichen; Gruppe wurde pausiert.")
        pending = [item["job"] for item in value["items"] if item["job"] and item["job"]["status"] in PENDING]
        if not pending:
            self.db.execute("UPDATE email_bulk_dispatches SET status='Completed',updated_at=? WHERE id=?",
                            (self.mail._timestamp(), dispatch_id))
            return self.snapshot(dispatch_id)
        job = pending[0]
        if job["approval_status"] != "approved" or job["requires_overdue_confirmation"]:
            return self._stop(dispatch_id, "Freigabe fehlt oder Nachversand muss neu bestätigt werden.")
        earliest = max([self.mail.now(), *[parse_time(t) for t in (value["next_send_at_utc"], job["scheduled_at_utc"]) if t]])
        if earliest > self.mail.now():
            return {**value, "wait_until": utc_string(earliest)}
        policy = policy_wait(self.db, value, self.mail.now())
        if policy["wait_until"]:
            return {**value, **policy}
        try:
            result = self.mail.send_job(job["id"], dispatch_id=dispatch_id)
        except Exception as error:
            # Before POST: leave this job unsent but revoke its approval until reviewed again.
            self.db.execute("UPDATE email_jobs SET approval_status='pending',last_error_code='preflight',last_error_message=?,updated_at=? WHERE id=? AND status IN ('Queued','Scheduled')",
                            (str(error), self.mail._timestamp(), job["id"]))
            return self._stop(dispatch_id, str(error))
        self.db.execute("UPDATE email_bulk_dispatches SET next_send_at_utc=?,updated_at=? WHERE id=?",
                        (utc_string(self.mail.now() + timedelta(seconds=value["interval_seconds"])), self.mail._timestamp(), dispatch_id))
        if result["status"] != "Sent":
            return self._stop(dispatch_id, result["last_error_message"] or "Einzelauftrag prüfen.")
        remaining = self.snapshot(dispatch_id)
        if not remaining["counts"]["pending"]:
            self.db.execute("UPDATE email_bulk_dispatches SET status='Completed',updated_at=? WHERE id=?",
                            (self.mail._timestamp(), dispatch_id))
        return self.snapshot(dispatch_id)

    def _stop(self, dispatch_id, message):
        self.db.execute("UPDATE email_bulk_dispatches SET status='Paused',last_error=?,updated_at=? WHERE id=?",
                        (message, self.mail._timestamp(), dispatch_id))
        return self.snapshot(dispatch_id)

    def item_action(self, dispatch_id, job_id, action):
        value = self.snapshot(dispatch_id)
        if value["status"] == "Running" or job_id not in [item["job_id"] for item in value["items"]]:
            raise MailError(_ui_tr('Gruppe zuerst pausieren und einen zugehörigen Einzelauftrag wählen.'))
        if action == "reconcile":
            self.mail.reconcile(job_id)
        elif action == "retry" and value["status"] != "Cancelled":
            self.mail.retry_failed(job_id)
        elif action == "cancel":
            self.mail.cancel(job_id)
        else:
            raise MailError(_ui_tr('Ungültige Einzelaktion.'))
        result = self.snapshot(dispatch_id)
        if result["status"] not in ("Preparing", "Cancelled") and result["counts"]["prepared"] == result["counts"]["total"] and not result["counts"]["pending"] and not result["counts"]["blocked"]:
            self.db.execute("UPDATE email_bulk_dispatches SET status='Completed',updated_at=? WHERE id=?", (self.mail._timestamp(), dispatch_id))
            result = self.snapshot(dispatch_id)
        return result

    def background_next(self, require_review=False):
        if require_review:
            for row in self.db.execute("SELECT id FROM email_bulk_dispatches WHERE status='Running' AND background=1").fetchall():
                self.pause(row[0], require_review=True)
            return {"dispatch": None, "groups": self.groups()}
        for row in self.db.execute("SELECT id FROM email_bulk_dispatches WHERE status='Running' AND background=1 ORDER BY updated_at,id").fetchall():
            result = self.next(row[0])
            if not result.get("wait_until"):
                return {"dispatch": result, "groups": self.groups()}
        return {"dispatch": None, "groups": self.groups()}

    def groups(self):
        result = []
        for row in self.db.execute("SELECT d.*,b.name FROM email_bulk_dispatches d JOIN email_draft_batches b ON b.id=d.batch_id WHERE d.status NOT IN ('Completed','Cancelled') ORDER BY d.created_at DESC"):
            value = dict(row)
            value.update(policy_wait(self.db, value, self.mail.now()))
            result.append(value)
        return result
