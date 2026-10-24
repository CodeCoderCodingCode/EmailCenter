"""Review and control a durable group without blocking the GUI during network calls."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from datetime import datetime, timedelta, timezone
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFormLayout, QHBoxLayout,
    QListWidget, QMessageBox, QPlainTextEdit, QProgressBar, QSpinBox, QVBoxLayout, QWidget, QTimeEdit, QScrollArea,
)

from ..mail_models import parse_time
from .mail_page import STATUS
from .mail_template_dialogs import BusyDialog
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


STATES = {"Preparing": "Versandkopien vorbereiten", "Ready": "Zur Prüfung bereit", "Running": "Versand aktiv",
          "Paused": "Pausiert", "Completed": "Abgeschlossen", "Cancelled": "Abgebrochen"}


class BulkDeliveryDialog(BusyDialog):
    export_requested = Signal(str)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_format('Gruppenversand · {0}', data['batch']['name']))
        self.resize(950, 790)
        self.data, self.dispatch = data, None
        self.auto, self.pending, self.close_after_pause = False, None, False
        self.require_review = False
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        layout = QVBoxLayout(self)
        title = label(data["batch"]["name"], "pageTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        if data.get('allow_duplicate_recipients'):
            layout.addWidget(label(_ui_tr('Mehrere Nachrichten an dieselbe Adresse sind für diese Builder-Gruppe ausdrücklich zugelassen. Jede Datenzeile bleibt ein eigener Auftrag.'), 'muted'))
        layout.addWidget(label(_ui_tr('Eine Nachricht je Datenzeile. Erst Versandkopien prüfen und freigeben, dann den Gruppenversand starten.'), 'muted'))
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        self.configuration = QWidget()
        form = QFormLayout(self.configuration)
        self.account = QComboBox()
        _ui_locale.add_item(self.account, _ui_tr('Verbundenes Gmail-Konto auswählen'), None)
        for account in data["accounts"]:
            self.account.addItem(account["account_email"], account["id"])
        accounts = {item.get("provider_account_id") for item in self._drafts(data)} - {None}
        if len(accounts) == 1:
            self.account.setCurrentIndex(max(0, self.account.findData(next(iter(accounts)))))
        elif self.account.count() == 2:
            self.account.setCurrentIndex(1)
        _ui_locale.add_row(form, _ui_tr('Absender für die Gruppe'), self.account)
        self.interval = QSpinBox()
        self.interval.setRange(1, 3600)
        self.interval.setValue(2)
        _ui_locale.set_suffix(self.interval, _ui_tr(' Sekunden'))
        _ui_locale.add_row(form, _ui_tr('Abstand zwischen Nachrichten'), self.interval)
        self.scheduled = _ui_locale.widget(QCheckBox, _ui_tr('Gruppe zu einem zukünftigen Zeitpunkt starten'))
        form.addRow(self.scheduled)
        self.schedule = QDateTimeEdit(datetime.now() + timedelta(hours=1))
        self.schedule.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.schedule.setCalendarPopup(True)
        self.schedule.setEnabled(False)
        self.scheduled.toggled.connect(self.schedule.setEnabled)
        _ui_locale.add_row(form, _ui_tr('Geplanter Start'), self.schedule)
        self.timezone = QComboBox()
        _ui_locale.add_items(self.timezone, [_ui_tr('Europe/Berlin'), _ui_tr('UTC')])
        _ui_locale.add_row(form, _ui_tr('Zeitzone des gewählten Zeitpunkts'), self.timezone)
        self.daily_budget = QSpinBox()
        self.daily_budget.setRange(1, 10000)
        self.daily_budget.setValue(100)
        _ui_locale.add_row(form, _ui_tr('Versandversuche / Konto / Tag'), self.daily_budget)
        self.window_start, self.window_end = QTimeEdit(), QTimeEdit()
        for control in (self.window_start, self.window_end):
            control.setDisplayFormat("HH:mm")
        window = QHBoxLayout()
        window.addWidget(self.window_start)
        window.addWidget(label(_ui_tr('bis')))
        window.addWidget(self.window_end)
        _ui_locale.add_row(form, _ui_tr('Versandfenster (gleich = ganztägig)'), window)
        body.addWidget(self.configuration)
        self.jobs = QListWidget()
        self.jobs.currentRowChanged.connect(self.show_job)
        body.addWidget(self.jobs, 1)
        self.review = QPlainTextEdit()
        self.review.setReadOnly(True)
        self.review.setMinimumHeight(180)
        body.addWidget(self.review, 1)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Alle offenen Nachrichten, Empfänger und Anhänge geprüft; gemeinsam freigeben'))
        self.confirm.toggled.connect(self.update_buttons)
        body.addWidget(self.confirm)
        self.background = _ui_locale.widget(QCheckBox, _ui_tr('Nach Start auch bei geschlossenem Gruppenfenster weiterarbeiten'))
        body.addWidget(self.background)
        self.overdue = _ui_locale.widget(QCheckBox, _ui_tr('Überfälligen Nachversand ausdrücklich bestätigen'))
        body.addWidget(self.overdue)
        self.overdue.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.content)
        layout.addWidget(scroll, 1)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = label(_ui_tr('Versandkopien sind feste Kopien der aktuellen Einzelentwürfe.'), 'muted')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = ActionFlowLayout()
        self.prepare_button = button(_ui_tr('Versandkopien vorbereiten'), self.prepare)
        self.approve_button = button(_ui_tr('Gruppe freigeben'), self.approve)
        self.start_button = button(_ui_tr('Gruppe senden'), self.start, primary=True)
        self.pause_button = button(_ui_tr('Pause'), lambda: self.request_stop('pause'))
        self.cancel_button = button(_ui_tr('Offene abbrechen'), self.cancel)
        for widget in (self.prepare_button, self.approve_button, self.start_button, self.pause_button, self.cancel_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        individual = ActionFlowLayout()
        self.reload_button = button(_ui_tr('Status neu laden'), lambda: self.emit('snapshot'))
        self.reconcile_button = button(_ui_tr('Unklaren Versand abgleichen'), lambda: self.item_action('reconcile'))
        self.retry_button = button(_ui_tr('Fehlgeschlagenen erneut freigeben'), lambda: self.item_action('retry'))
        self.skip_button = button(_ui_tr('Einzelauftrag stornieren'), lambda: self.item_action('cancel'))
        self.close_button = button(_ui_tr('Schließen'), self.reject)
        for widget in (self.reload_button, self.reconcile_button, self.retry_button, self.skip_button, self.close_button):
            individual.addWidget(widget)
        layout.addLayout(individual)
        self.export_button = button(_ui_tr('Versandbericht dieser Gruppe exportieren'), lambda: self.export_requested.emit(self.data['batch']['id']))
        layout.addWidget(self.export_button)
        layout.addWidget(label(_ui_tr('Hintergrundversand benötigt die geöffnete App. Steuerung im Arbeitsbereich. Pause/Abbruch greifen nach dem laufenden Einzelauftrag; nach Neustart erneut prüfen. Das lokale Tagesbudget zählt alle Versandversuche dieses Kontos im Projekt und ist keine Garantie für Gmail-Limits.'), 'muted'))
        from .mail_defaults import apply_mail_defaults, apply_plan_defaults
        apply_mail_defaults(self, project_account=next(iter(accounts)) if len(accounts) == 1 else None)
        apply_plan_defaults(self)
        if data["dispatch"]:
            self.display(data["dispatch"])
        self.account.currentIndexChanged.connect(self.update_buttons)
        self.update_buttons()
        compact_forms(self)

    @staticmethod
    def _drafts(data):
        return data.get("drafts", [])

    def emit(self, suffix, payload=None):
        if self.busy:
            return
        value = payload or {"dispatch_id": self.dispatch["id"]}
        self.operation_requested.emit("mail_bulk_delivery_" + suffix, value)

    def prepare(self):
        if self.busy or not self.prepare_button.isEnabled():
            return
        self.auto, self.pending = True, None
        if self.dispatch:
            self.emit("prepare_next")
        else:
            self.emit("begin", {"batch_id": self.data["batch"]["id"], "provider_account_id": self.account.currentData(),
                               "interval_seconds": self.interval.value(), "timezone_id": self.timezone.currentText(),
                               "daily_budget": self.daily_budget.value(), "window_start": self.window_start.time().toString("HH:mm"), "window_end": self.window_end.time().toString("HH:mm"),
                               "scheduled_local": self.schedule.dateTime().toString("yyyy-MM-ddTHH:mm:ss") if self.scheduled.isChecked() else None})

    def approve(self):
        if self.busy or not self.approve_button.isEnabled():
            return
        if self.overdue.isVisible() and not self.overdue.isChecked():
            QMessageBox.warning(self, _ui_tr('Nachversand bestätigen'), _ui_tr('Überfällige Aufträge zuerst ausdrücklich bestätigen.'))
            return
        if QMessageBox.question(self, _ui_tr('Gemeinsame Freigabe'), _ui_format('{0} offene Nachrichten mit den angezeigten Versandkopien freigeben?', f"{self.dispatch['counts']['pending']}")) == QMessageBox.StandardButton.Yes:
            self.emit("approve", {"dispatch_id": self.dispatch["id"], "expected_fingerprint": self.dispatch["fingerprint"],
                                  "confirm_overdue": self.overdue.isChecked()})

    def start(self):
        if self.busy or not self.start_button.isEnabled():
            return
        text = _ui_format('{0} freigegebene Nachrichten einzeln versenden? Geplante Zeitpunkte und der Abstand werden eingehalten.', self.dispatch['counts']['pending'])
        if QMessageBox.question(self, _ui_tr('Gruppenversand starten'), text) != QMessageBox.StandardButton.Yes:
            return
        self.auto, self.pending, self.last_tick = True, None, time.monotonic()
        self.emit("start", {"dispatch_id": self.dispatch["id"], "expected_fingerprint": self.dispatch["fingerprint"], "background": self.background.isChecked()})

    def display(self, value):
        selected = self.selected_job()
        selected_id = selected["id"] if selected else None
        self.dispatch = value
        if value.get("background") and value["status"] == "Running":
            self.auto = False
            self.timer.stop()
        self.confirm.setChecked(False)
        self.overdue.setChecked(False)
        self.configuration.hide()
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for item in value["items"]:
            job = item["job"]
            details = _ui_format('{0}\n{1} · {2}', '; '.join(job['recipients']['to']), job['subject_snapshot'],
                                 _ui_tr(STATUS.get(job['status'], job['status']))) if job else _ui_tr('noch nicht vorbereitet')
            _ui_locale.add_item(self.jobs, _ui_format('{0} · {1}', item['name_snapshot'], details))
        index = next((i for i, item in enumerate(value["items"]) if item["job_id"] == selected_id and selected_id), 0)
        self.jobs.setCurrentRow(index if value["items"] else -1)
        self.jobs.blockSignals(False)
        self.show_job()
        counts = value["counts"]
        self.progress.setRange(0, counts["total"])
        completed = counts["prepared"] if value["status"] == "Preparing" else counts["sent"] + counts["cancelled"]
        self.progress.setValue(completed)
        _ui_locale.set_format(self.progress, _ui_format('{0}/{1} vorbereitet · {2} gesendet · {3} storniert · {4} zu prüfen',
                             counts['prepared'], counts['total'], counts['sent'], counts['cancelled'], counts['blocked']))
        policy = _ui_format(' · Budget {0}/Tag · {1}–{2} {3}', value.get('daily_budget', 100),
                            value.get('window_start', '00:00'), value.get('window_end', '00:00'), value['timezone_id'])
        _ui_locale.set_text(self.status, _ui_format('{0}{1}{2}{3}', _ui_tr(STATES[value['status']]),
                            ' · ' + value['last_error'] if value['last_error'] else '', policy,
                            ' · ' + value['wait_reason'] if value.get('wait_reason') else ''))
        self.overdue.setVisible(any(item["job"] and item["job"]["requires_overdue_confirmation"] and item["job"]["status"] in ("Queued", "Scheduled") for item in value["items"]))
        self.update_buttons()
        if self.auto and value["status"] == "Running" and time.monotonic() - self.last_tick > 90 and not self.pending:
            self.auto = False
            self.timer.stop()
            self.require_review, self.pending = True, "pause"
        if self.pending == "hold":
            return
        if self.pending:
            intent, self.pending = self.pending, None
            if intent == "cancel":
                self.emit("cancel")
                return
            if value["status"] == "Running":
                self.emit("pause", {"dispatch_id": value["id"], "require_review": self.require_review})
                self.require_review = False
                return
        if self.close_after_pause and value["status"] != "Running":
            self.close_after_pause = False
            super().reject()
            return
        if self.auto and not value["last_error"]:
            if value["status"] == "Preparing":
                QTimer.singleShot(0, self.advance)
            elif value["status"] == "Running":
                if value.get("wait_until"):
                    self.last_tick = time.monotonic()
                    self.timer.start()
                else:
                    QTimer.singleShot(0, self.advance)
            else:
                self.auto = False
                self.timer.stop()
        else:
            self.auto = False
            self.timer.stop()
        self.update_buttons()

    def advance(self):
        if self.auto and not self.busy and not self.pending and self.dispatch:
            if self.dispatch["status"] == "Running" and time.monotonic() - self.last_tick > 90:
                self.require_review = True
                self.request_stop("pause")
                return
            self.last_tick = time.monotonic()
            self.emit("prepare_next" if self.dispatch["status"] == "Preparing" else "next")

    def tick(self):
        now = time.monotonic()
        gap, self.last_tick = now - self.last_tick, now
        if gap > 90:
            _ui_locale.set_text(self.status, _ui_tr('Längere Unterbrechung erkannt: Gruppe pausieren und prüfen.'))
            self.require_review = True
            self.request_stop("pause")
            return
        if not self.auto or not self.dispatch or self.dispatch["status"] != "Running":
            self.timer.stop()
            return
        until = self.dispatch.get("wait_until")
        seconds = max(0, int((parse_time(until) - datetime.now(timezone.utc)).total_seconds()) + 1) if until else 0
        _ui_locale.set_text(self.status, _ui_format('Versand aktiv · Nächste Nachricht in {0} Sekunden · Pause jederzeit möglich', f'{seconds}'))
        if seconds == 0 and not self.busy:
            self.timer.stop()
            self.advance()

    def request_stop(self, intent):
        self.auto = False
        self.timer.stop()
        if not self.dispatch:
            return
        if self.busy:
            self.pending = intent
            _ui_locale.set_text(self.status, _ui_tr('Abbruch vorgemerkt; laufenden Einzelauftrag abschließen.') if intent == 'cancel' else _ui_tr('Pause vorgemerkt; laufenden Einzelauftrag abschließen.'))
        elif intent == "cancel":
            self.pending = None
            self.emit("cancel")
        elif self.dispatch["status"] == "Running":
            self.pending = None
            self.emit("pause", {"dispatch_id": self.dispatch["id"], "require_review": self.require_review})
            self.require_review = False
        else:
            self.pending = None
            _ui_locale.set_text(self.status, _ui_tr('Vorbereitung pausiert. Bereits erstellte Versandkopien bleiben gespeichert.'))
        self.update_buttons()

    def cancel(self):
        if not self.cancel_button.isEnabled():
            return
        self.auto = False
        self.timer.stop()
        self.pending = "hold"  # A nested confirmation loop must not dispatch another message.
        answer = QMessageBox.question(self, _ui_tr('Offene Aufträge abbrechen'), _ui_tr('Alle noch nicht versendeten Aufträge dieser Gruppe stornieren? Versandbelege und unklare Ergebnisse bleiben erhalten.'))
        self.request_stop("cancel" if answer == QMessageBox.StandardButton.Yes else "pause")

    def selected_job(self):
        row = self.jobs.currentRow()
        return self.dispatch["items"][row]["job"] if self.dispatch and 0 <= row < len(self.dispatch["items"]) else None

    def show_job(self):
        job = self.selected_job()
        if not job:
            _ui_locale.set_plain_text(self.review, _ui_tr('Noch keine Versandkopie. Die persönlichen Inhalte und Anhänge werden beim Vorbereiten fest gespeichert.'))
        else:
            files = "\n".join(f"{a['filename_snapshot']} · {a['file_hash_snapshot'][:12]}" for a in job["attachments"]) or _ui_tr("Keine Anhänge")
            attempts = "\n".join(f"{a['attempt_number']}. {a['result']} · {a['error_message'] or a['provider_message_id'] or ''}" for a in job["attempts"])
            _ui_locale.set_plain_text(self.review, _ui_format('Von: {0}\nAn: {1}\nBetreff: {2}\nZeit: {3} · {4}\n\n{5}\n\nAnhänge:\n{6}\n\n{7}\n{8}\n\nDiese Versandkopie bleibt bei späteren Entwurfsänderungen unverändert.', job['sender_snapshot'], '; '.join(job['recipients']['to']), job['subject_snapshot'], job['scheduled_at_utc'] or _ui_tr('Direkt nach Gruppenstart'), job['timezone_id'], job['body_snapshot'], files, job['last_error_message'] or '', attempts))
        self.update_buttons()

    def item_action(self, action):
        job = self.selected_job()
        if self.busy or not job:
            return
        if action != "reconcile" and QMessageBox.question(self, _ui_tr('Einzelauftrag'), _ui_tr('Diesen eindeutig fehlgeschlagenen Auftrag erneut freigeben?') if action == 'retry' else _ui_tr('Diesen offenen Einzelauftrag stornieren?')) != QMessageBox.StandardButton.Yes:
            return
        self.emit("item", {"dispatch_id": self.dispatch["id"], "job_id": job["id"], "action": action})

    def update_buttons(self):
        if not hasattr(self, "close_button"):
            return
        value = self.dispatch
        state = value["status"] if value else None
        idle = not self.busy and not self.auto and not self.pending
        reviewable = idle and state in ("Ready", "Paused") and value["counts"]["pending"] > 0 and not value["counts"]["blocked"]
        self.prepare_button.setVisible(state is None or state == "Preparing")
        _ui_locale.set_text(self.prepare_button, _ui_tr('Vorbereitung fortsetzen') if state else _ui_tr('Versandkopien vorbereiten'))
        self.prepare_button.setEnabled(idle and (bool(self.account.currentData()) if state is None else state == "Preparing"))
        self.confirm.setEnabled(bool(reviewable))
        self.approve_button.setEnabled(bool(reviewable and self.confirm.isChecked()))
        approved = bool(value and all(item["job"] and (item["job"]["status"] not in ("Draft", "Queued", "Scheduled") or
                        (item["job"]["approval_status"] == "approved" and not item["job"]["requires_overdue_confirmation"])) for item in value["items"]))
        self.start_button.setEnabled(bool(reviewable and approved))
        _ui_locale.set_text(self.start_button, _ui_tr('Versand fortsetzen') if value and value['counts']['sent'] else _ui_tr('Geplant starten') if value and value['scheduled_local'] else _ui_tr('Gruppe senden'))
        self.pause_button.setEnabled(bool(value and (self.auto or state == "Running") and not self.pending))
        self.cancel_button.setEnabled(bool(value and state not in ("Completed", "Cancelled") and self.pending != "cancel"))
        self.reload_button.setEnabled(bool(value and idle and state != "Running"))
        job = self.selected_job()
        item_idle = bool(value and idle and state != "Running")
        self.reconcile_button.setEnabled(bool(item_idle and job and job["status"] in ("Uncertain", "ReconciliationRequired")))
        self.retry_button.setEnabled(bool(item_idle and state != "Cancelled" and job and job["status"] == "Failed"))
        self.skip_button.setEnabled(bool(item_idle and job and job["status"] in ("Draft", "Queued", "Scheduled", "Failed")))
        self.close_button.setEnabled(not self.busy)
        self.export_button.setEnabled(idle and state != "Running")

    def set_busy(self, busy):
        # Keep pause/cancel usable while the worker owns the current network call.
        self.busy = busy
        self.content.setEnabled(not busy)
        self.update_buttons()

    def failed(self):
        self.auto = False
        self.timer.stop()
        self.confirm.setChecked(False)
        self.overdue.setChecked(False)
        self.pending = None
        _ui_locale.set_text(self.status, _ui_tr('Aktion fehlgeschlagen. Status neu laden und erneut prüfen.'))
        self.update_buttons()
        if self.dispatch and self.dispatch["status"] == "Running" and not self.busy:
            self.emit("pause")

    def reject(self):
        if self.busy:
            return
        self.auto = False
        self.timer.stop()
        if self.dispatch and self.dispatch["status"] == "Running" and not self.dispatch.get("background"):
            self.close_after_pause = True
            self.request_stop("pause")
        else:
            super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def force_close(self):
        """Project shutdown already persisted the pause on the worker thread."""
        self.auto = False
        self.timer.stop()
        self.busy = False
        QDialog.reject(self)
