"""Mail work orders embedded in the project work area, with explicit approval."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, QDateTime, QTime, QTimeZone, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QListWidget, QVBoxLayout,
)

from .mail_page import STATUS, job_actions, populate_accounts
from .pages import button, label


class PrepareMailDialog(QDialog):
    operation_requested = Signal(str, object)

    def __init__(self, draft, timezone_id, parent=None, *, accounts=()):
        super().__init__(parent)
        self.draft, self.busy = draft, False
        _ui_locale.set_window_title(self, _ui_tr('E-Mail senden'))
        self.resize(560, 350)
        layout = QVBoxLayout(self)
        layout.addWidget(label(draft["subject"]))
        layout.addWidget(label(_ui_tr('Konto, Empfänger, Inhalt und Anhänge werden geprüft. Danach den festen Auftrag prüfen und freigeben.'), 'muted'))
        self.scheduled = _ui_locale.widget(QCheckBox, _ui_tr('Zu einem späteren Zeitpunkt senden'))
        layout.addWidget(self.scheduled)
        form = QFormLayout()
        self.account = QComboBox()
        populate_accounts(self.account, accounts, draft["provider_account_id"])
        _ui_locale.add_row(form, _ui_tr('Absenderkonto'), self.account)
        self.zone = QComboBox()
        self.zone.setEditable(True)
        self.zone.addItems(list(dict.fromkeys((timezone_id, "Europe/Berlin", "UTC"))))
        self.when = QDateTimeEdit()
        # Store the selected wall-clock fields without the OS timezone normalizing
        # DST gaps. The backend interprets and validates them in the chosen zone.
        clock_fields = QTimeZone(b"UTC")
        self.when.setTimeZone(clock_fields)
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd.MM.yyyy HH:mm")
        local = datetime.now(ZoneInfo(timezone_id)) + timedelta(hours=1)
        self.when.setDateTime(QDateTime(QDate(local.year, local.month, local.day), QTime(local.hour, local.minute), clock_fields))
        self.when.setEnabled(False)
        self.scheduled.toggled.connect(self.when.setEnabled)
        _ui_locale.add_row(form, _ui_tr('Datum / Uhrzeit in gewählter Zeitzone'), self.when)
        _ui_locale.add_row(form, _ui_tr('Zeitzone'), self.zone)
        layout.addLayout(form)
        layout.addWidget(label(_ui_tr('Ohne Termin: manueller Versand nach Freigabe. Bei Termin: automatische Ausführung nur mit eingeschaltetem Scheduler.'), 'muted'))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.scheduled.toggled.connect(self.update_send_caption)
        self.update_send_caption()
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        self.buttons.accepted.connect(self.prepare)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        from .mail_defaults import preferences_of, apply_mail_defaults
        preferences = preferences_of(self)
        if preferences:
            self.scheduled.setChecked(preferences.mail_delivery_mode == "scheduled")
            apply_mail_defaults(self, project_account=draft.get("provider_account_id"))

    def update_send_caption(self):
        caption = "Versand planen" if self.scheduled.isChecked() else "Senden"
        _ui_locale.set_window_title(self, _ui_tr(caption))
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr(caption))

    def prepare(self):
        if not self.busy:
            self.operation_requested.emit("mail_prepare_job", {
                "draft_id": self.draft["id"], "timezone_id": self.zone.currentText().strip(),
                "provider_account_id": self.account.currentData(),
                "scheduled_local": self.when.dateTime().toString("yyyy-MM-dd'T'HH:mm:ss") if self.scheduled.isChecked() else None,
            })

    def set_busy(self, busy):
        self.busy = busy
        self.setEnabled(not busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)


class MailWorkflow(QFrame):
    action_requested = Signal(str, object)
    load_requested = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.data = None
        self.offsets = {"drafts": 0, "jobs": 0}
        self.selection = {"drafts": None, "jobs": None}
        self.limit = 25
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(label(_ui_tr('E-Mail-Aufträge'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Entwurf → Senden / planen → prüfen und freigeben → Versandstatus ansehen'), 'muted'))
        header = QHBoxLayout()
        self.view = QComboBox()
        _ui_locale.add_item(self.view, _ui_tr('Entwürfe'), 'drafts')
        _ui_locale.add_item(self.view, _ui_tr('Versandaufträge'), 'jobs')
        self.view.currentIndexChanged.connect(self.change_view)
        header.addWidget(self.view, 1)
        self.new_button = button(_ui_tr('Neuer Entwurf'), lambda: self.action_requested.emit('new', None), primary=True)
        header.addWidget(self.new_button)
        header.addWidget(button(_ui_tr('Aktualisieren'), self.request_load))
        layout.addLayout(header)
        layout.addWidget(button(_ui_tr('E-Mail-Vorlagen verwalten'), lambda: self.action_requested.emit('templates', None)))
        self.bulk_button = button(_ui_tr('Bulk-E-Mails · Empfänger und Vorschau'), lambda: self.action_requested.emit('bulk', None))
        layout.addWidget(self.bulk_button)
        self.account_status = label(_ui_tr('Noch keine Kontodaten geladen.'), 'muted')
        layout.addWidget(self.account_status)
        self.connect_button = button(_ui_tr('Gmail verbinden'), lambda: self.action_requested.emit('connect', None))
        layout.addWidget(self.connect_button)
        self.scheduler = _ui_locale.widget(QCheckBox, _ui_tr('Freigegebene geplante Nachrichten automatisch senden, solange EmailCenter geöffnet ist.'))
        layout.addWidget(self.scheduler)
        self.records = QListWidget()
        self.records.setMinimumHeight(145)
        self.records.setMaximumHeight(210)
        self.records.currentRowChanged.connect(self.update_selection)
        self.records.itemDoubleClicked.connect(lambda _: self.invoke("edit" if self.kind == "drafts" else "review"))
        layout.addWidget(self.records)
        self.details = label("", "muted")
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        self.actions_layout = QGridLayout()
        self.buttons = {}
        for action, caption in (("edit", "Entwurf bearbeiten"), ("prepare", "Senden / planen"),
                                ("review", "Prüfen / Freigeben"), ("send", "Jetzt senden"),
                                ("reconcile", "Gmail abgleichen"), ("cancel", "Auftrag stornieren")):
            self.buttons[action] = button(caption, lambda checked=False, action=action: self.invoke(action), primary=action in ("prepare", "send"))
            self.actions_layout.addWidget(self.buttons[action], len(self.buttons) - 1, 0)
        layout.addLayout(self.actions_layout)
        footer = QHBoxLayout()
        self.previous = button(_ui_tr('Zurück'), lambda: self.move_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.move_page(1))
        self.summary = label(_ui_tr('Noch keine Entwürfe geladen.'), 'muted')
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.previous)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self.update_selection()

    @property
    def kind(self):
        return self.view.currentData()

    def reset(self):
        self.data = None
        self.scheduler.setChecked(False)
        self.offsets = {"drafts": 0, "jobs": 0}
        self.selection = {"drafts": None, "jobs": None}
        self.view.blockSignals(True)
        self.view.setCurrentIndex(0)
        self.view.blockSignals(False)
        self.records.clear()
        self.update_selection()

    def request_load(self):
        self.load_requested.emit("workspace_mail_snapshot", {
            "draft_offset": self.offsets["drafts"], "job_offset": self.offsets["jobs"], "limit": self.limit})

    def change_view(self):
        self.render()
        self.request_load()

    def display(self, data):
        self.data = data
        self.offsets = {"drafts": data["draft_offset"], "jobs": data["job_offset"]}
        self.render()

    def focus_job(self, identifier):
        self.selection["jobs"] = identifier
        self.offsets["jobs"] = 0
        self.view.blockSignals(True)
        self.view.setCurrentIndex(1)
        self.view.blockSignals(False)

    def render(self):
        self.records.blockSignals(True)
        self.records.clear()
        rows = self.data[self.kind] if self.data else []
        selected = -1
        for index, row in enumerate(rows):
            status = "Entwurf" if self.kind == "drafts" else STATUS.get(row["status"], row["status"])
            title = row["subject"] if self.kind == "drafts" else row["subject_snapshot"]
            _ui_locale.add_item(self.records, _ui_format('{0} · {1}', title, _ui_tr(status)))
            if row["id"] == self.selection[self.kind]:
                selected = index
        self.records.setCurrentRow(selected if selected >= 0 else (0 if rows else -1))
        self.records.blockSignals(False)
        self.update_selection()

    def selected(self):
        index = self.records.currentRow()
        rows = self.data[self.kind] if self.data else []
        return rows[index] if 0 <= index < len(rows) else None

    def update_selection(self):
        accounts = [a for a in self.data["accounts"] if a["is_enabled"]] if self.data else []
        _ui_locale.set_text(self.account_status, _ui_format('Verbunden: {0}', ', '.join(a['account_email'] for a in accounts)) if accounts else _ui_tr('Kein Gmail-Konto in diesem Projekt verbunden. Über Gmail verbinden anmelden.'))
        row = self.selected()
        self.selection[self.kind] = row["id"] if row else None
        draft = self.kind == "drafts"
        for action in ("edit", "prepare"):
            self.buttons[action].setVisible(draft)
            self.buttons[action].setEnabled(bool(row))
        for action, enabled in job_actions(row if not draft else None).items():
            self.buttons[action].setVisible(not draft)
            self.buttons[action].setEnabled(enabled)
        self.reflow()
        if not row:
            _ui_locale.set_text(self.details, _ui_tr('Noch keine Entwürfe. Über Einzelne E-Mail vorbereiten beginnen.') if draft else _ui_tr('Noch keine Versandaufträge. Einen Entwurf auswählen und vorbereiten.'))
        else:
            targets = "; ".join(row["recipients"]["to"])
            if draft:
                account = next((a for a in self.data["accounts"] if a["id"] == row["provider_account_id"] and a["is_enabled"]), None)
                step = "Nächster Schritt: Senden / planen wählen." if account else "Nächster Schritt: Senden / planen wählen und Absenderkonto auswählen." if accounts else "Nächster Schritt: Gmail verbinden, danach Senden / planen wählen."
                info = _ui_format('Von: {0}', account['account_email'] if account else _ui_tr('Konto fehlt'))
            else:
                step = self.next_step(row)
                info = _ui_format('Status: {0} · {1}', _ui_tr(STATUS.get(row['status'], row['status'])), row['scheduled_at_utc'] or _ui_tr('Manuell'))
            _ui_locale.set_text(self.details, _ui_format('An: {0}\n{1}\n{2}', f'{targets}', info, _ui_tr(step)))
        total = self.data["draft_total" if draft else "job_total"] if self.data else 0
        offset = self.offsets[self.kind]
        count = len(self.data[self.kind]) if self.data else 0
        _ui_locale.set_text(self.summary, _ui_format('{0}–{1} von {2}', f'{(offset + 1 if count else 0)}', f'{offset + count}', f'{total}'))
        self.previous.setEnabled(offset > 0)
        self.next.setEnabled(offset + count < total)

    @staticmethod
    def next_step(job):
        status = job["status"]
        if status in ("Uncertain", "ReconciliationRequired"):
            return _ui_tr("Ergebnis unklar: Gmail abgleichen.")
        if status == "Failed":
            return _ui_tr("Fehler prüfen und bei Bedarf erneut freigeben.")
        if status in ("Sent", "Cancelled", "Sending"):
            return {"Sent": "Versand bestätigt. Verlauf über Prüfen ansehen.", "Cancelled": "Auftrag storniert.", "Sending": "Versand läuft."}[status]
        if job["requires_overdue_confirmation"]:
            return _ui_tr("Überfälligen Auftrag und Nachversand erneut prüfen / freigeben.")
        if job["approval_status"] != "approved":
            return _ui_tr("Nächster Schritt: Inhalt, Empfänger und Anhänge prüfen / freigeben.")
        if job["scheduled_at_utc"]:
            return _ui_tr("Freigegeben und geplant. Scheduler aktivieren oder ausdrücklich Jetzt senden wählen.")
        return _ui_tr("Freigegeben. Nächster Schritt: Jetzt senden.")

    def invoke(self, action):
        if self.buttons[action].isEnabled() and not self.buttons[action].isHidden():
            row = self.selected()
            if row:
                self.action_requested.emit(action, row)

    def move_page(self, direction):
        if not self.data:
            return
        total = self.data["draft_total" if self.kind == "drafts" else "job_total"]
        candidate = max(0, self.offsets[self.kind] + direction * self.limit)
        if candidate != self.offsets[self.kind] and (candidate == 0 or candidate < total):
            self.offsets[self.kind] = candidate
            self.selection[self.kind] = None
            self.request_load()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        columns = 2 if self.width() >= 620 else 1
        visible = [control for control in self.buttons.values() if not control.isHidden()]
        for control in self.buttons.values():
            self.actions_layout.removeWidget(control)
        for index, control in enumerate(visible):
            self.actions_layout.addWidget(control, index // columns, index % columns)
        self.actions_layout.setColumnStretch(0, 1)
        self.actions_layout.setColumnStretch(1, 1 if columns == 2 else 0)
