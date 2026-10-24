"""Follow-up overview and a calendar-based reminder editor."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate, QTime, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit, QMessageBox, QPlainTextEdit, QTimeEdit, QVBoxLayout,
)

from ..mail_models import parse_time, AmbiguousTimeError
from ..reminder_service import local_reminder_time, reminder_zone
from .pages import RecordPage, label


class FollowUpPage(RecordPage):
    def __init__(self):
        self.timezone_id = "Europe/Berlin"
        super().__init__("followups", "Nachfassen & Erinnerungen",
                         "Bewerbungstermine und eigene Erinnerungen. Erledigte Nachfasstermine werden aus der Bewerbung entfernt.",
                         [("Titel", "title"), ("Art", "kind_label"), ("Termin", "due_label"), ("Bewerbung", "application_title"), ("Status", "status_label")],
                         [("Erinnerung anlegen", "new_reminder", False), ("Termin bearbeiten", "edit_reminder", True),
                          ("Erledigt", "finish_reminder", True), ("Verwerfen", "dismiss_reminder", True), ("Bewerbung öffnen", "followup_application", True)])
        filters = QHBoxLayout()
        self.view = QComboBox()
        for text, value in (("Fällig / überfällig", "due"), ("Heute", "today"), ("Zukünftig", "upcoming"),
                            ("Alle offenen", "pending"), ("Abgeschlossene", "history")):
            self.view.addItem(text, value)
        self.view.currentIndexChanged.connect(self.search_records)
        filters.addWidget(self.view)
        self.summary_label = label("", "muted")
        filters.addWidget(self.summary_label, 1)
        self.layout().insertLayout(2, filters)

    def request_load(self):
        self.load_requested.emit("followup_list", {"view": self.view.currentData(), "search": self.search.text(), "offset": self.offset, "limit": self.limit, "timezone_id": self.timezone_id})

    def display(self, result):
        selected = self.selected_record()
        super().display(result)
        if "summary" in result:
            _ui_locale.set_text(self.summary_label, _ui_format('{0} fällig · {1} offen', f"{result['summary']['due']}", f"{result['summary']['pending']}"))
        if selected:
            for index, record in enumerate(self.rows):
                if (record["source"], record["record_id"]) == (selected["source"], selected["record_id"]):
                    self.table.selectRow(index)
                    break

    def update_selection(self):
        super().update_selection()
        record = self.selected_record()
        for action in ("edit_reminder", "finish_reminder", "dismiss_reminder"):
            self.action_buttons[action][0].setEnabled(bool(record and record["status"] == "Pending"))
        self.action_buttons["followup_application"][0].setEnabled(bool(record and record["application_id"]))

    def reset(self):
        self.offset = 0
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.view.blockSignals(True)
        self.view.setCurrentIndex(0)
        self.view.blockSignals(False)
        self.summary_label.clear()
        self.display({"rows": [], "offset": 0, "total": 0})


class ReminderDialog(QDialog):
    operation_requested = Signal(str, object)

    def __init__(self, data, parent=None, *, default_timezone="Europe/Berlin"):
        super().__init__(parent)
        self.data, self._busy = data, False
        record = data["record"]
        if record and data["source"] == "application":
            record = {**record, "timezone_id": default_timezone}
        _ui_locale.set_window_title(self, _ui_tr('Nachfasstermin bearbeiten') if data['source'] == 'application' else _ui_tr('Erinnerung bearbeiten') if record else _ui_tr('Erinnerung anlegen'))
        self.resize(620, 540)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.setMaxLength(max(32768, len(record["title"]) if record else 0))
        self.title.setText(record["title"] if record else "")
        self.title.setReadOnly(data["source"] == "application")
        _ui_locale.add_row(form, _ui_tr('Titel *'), self.title)
        self.application = QComboBox()
        _ui_locale.add_item(self.application, _ui_tr('Ohne Bewerbungszuordnung'), None)
        for application in data["applications"]:
            self.application.addItem(application["title"], application["id"])
        if record:
            identifier = record["id"] if data["source"] == "application" else record["application_id"]
            index = self.application.findData(identifier)
            if index < 0:
                _ui_locale.add_item(self.application, _ui_tr('Bestehende archivierte Bewerbung'), identifier)
                index = self.application.count() - 1
            self.application.setCurrentIndex(index)
        self.application.setEnabled(data["source"] == "reminder")
        _ui_locale.add_row(form, _ui_tr('Bewerbung'), self.application)
        self.zone = QComboBox()
        self.zone.setEditable(True)
        _ui_locale.add_items(self.zone, [_ui_tr('Europe/Berlin'), _ui_tr('UTC')])
        self.zone.setCurrentText(record["timezone_id"] if record else default_timezone)
        _ui_locale.add_row(form, _ui_tr('Zeitzone'), self.zone)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm:ss")
        local = (datetime.now(timezone.utc) + timedelta(days=1)).astimezone(reminder_zone(default_timezone)).replace(hour=9, minute=0, second=0, microsecond=0)
        warning = None
        if record:
            try:
                local = parse_time(record["due_at_utc"]).astimezone(reminder_zone(record["timezone_id"]))
            except ValueError:
                warning = _ui_tr('Gespeicherter Termin oder Zeitzone ist ungültig. Bitte neu festlegen.')
        self.date.setDate(QDate(local.year, local.month, local.day))
        self.time.setTime(QTime(local.hour, local.minute, local.second))
        _ui_locale.add_row(form, _ui_tr('Datum *'), self.date)
        _ui_locale.add_row(form, _ui_tr('Uhrzeit *'), self.time)
        self.occurrence = QComboBox()
        _ui_locale.add_item(self.occurrence, _ui_tr('Bitte auswählen'), None)
        _ui_locale.add_item(self.occurrence, _ui_tr('Erstes Vorkommen (früher)'), 0)
        _ui_locale.add_item(self.occurrence, _ui_tr('Zweites Vorkommen (später)'), 1)
        self.occurrence_label = label(_ui_tr('Zeitumstellung'))
        form.addRow(self.occurrence_label, self.occurrence)
        self.description = QPlainTextEdit(record["description"] or "" if record else "")
        self.description.setReadOnly(data["source"] == "application")
        self.description.setMaximumHeight(140)
        _ui_locale.add_row(form, _ui_tr('Beschreibung'), self.description)
        layout.addLayout(form)
        if warning:
            layout.addWidget(label(warning, "muted"))
        layout.addWidget(label(_ui_tr('Bei der Rückstellung der Uhr muss für doppelte Uhrzeiten das erste oder zweite Vorkommen gewählt werden.'), 'muted'))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Speichern'))
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.date.dateChanged.connect(self.update_occurrence)
        self.time.timeChanged.connect(self.update_occurrence)
        self.zone.currentTextChanged.connect(self.update_occurrence)
        self.update_occurrence()
        if record and self.occurrence.isVisibleTo(self):
            self.occurrence.setCurrentIndex(self.occurrence.findData(local.fold))

    def local_value(self):
        return self.date.date().toString("yyyy-MM-dd") + "T" + self.time.time().toString("HH:mm:ss")

    def update_occurrence(self):
        ambiguous = False
        try:
            local_reminder_time(self.local_value(), self.zone.currentText().strip())
        except ValueError as error:
            ambiguous = isinstance(error, AmbiguousTimeError)
        self.occurrence.setVisible(ambiguous)
        self.occurrence_label.setVisible(ambiguous)
        self.occurrence.setCurrentIndex(0)

    def save(self):
        if self._busy:
            return
        try:
            if not self.title.text().strip():
                raise ValueError(_ui_tr('Bitte einen Titel eingeben.'))
            zone = self.zone.currentText().strip()
            due = local_reminder_time(self.local_value(), zone, self.occurrence.currentData())
        except ValueError as error:
            QMessageBox.warning(self, _ui_tr('Termin prüfen'), str(error))
            return
        payload = {"source": self.data["source"], "title": self.title.text().strip(), "due_at_utc": due,
                   "timezone_id": zone, "application_id": self.application.currentData(), "description": self.description.toPlainText() or None}
        if self.data["record"]:
            payload.update(record_id=self.data["record"]["id"], expected_version=self.data["version"])
        self.operation_requested.emit("reminder_save", payload)

    def set_busy(self, busy):
        self._busy = busy
        for widget in (self.title, self.zone, self.date, self.time, self.occurrence, self.description, self.buttons):
            widget.setEnabled(not busy)
        self.application.setEnabled(not busy and self.data["source"] == "reminder")

    def reject(self):
        if not self._busy:
            super().reject()
