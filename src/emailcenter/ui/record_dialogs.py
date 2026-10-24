"""Worker-backed editors: keep entered values until saving succeeds."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout,
    QHeaderView, QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .dialogs import FormDialog
from .pages import button, label
import json
from .structured_fields import CustomFieldsEditor


class RecordDialog(FormDialog):
    operation_requested = Signal(str, object)

    def __init__(self, data, parent=None):
        self.data = data
        entity, record, choices = data["entity"], data["record"], data["choices"]
        company_choices = [(_ui_tr('Ohne Unternehmen'), None), *[(r["name"], r["id"]) for r in choices["companies"]]]
        definitions = {
            "companies": ("Unternehmen", [("name", "Name", "required"), ("website", "Website", None), ("industry", "Branche", None), ("notes", "Notizen", "multiline")]),
            "contacts": ("Kontakt", [("display_name", "Name", "required"), ("first_name", "Vorname", None), ("last_name", "Nachname", None),
                                     ("email", "E-Mail", None), ("phone", "Telefon", None), ("position", "Position", None), ("notes", "Notizen", "multiline")]),
            "applicants": ("Bewerberprofil", [("display_name", "Name", "required"), ("email", "E-Mail", None), ("phone", "Telefon", None)]),
            "jobs": ("Stelle", [("title", "Titel", "required"), ("company_id", "Unternehmen *", company_choices),
                               ("reference_number", "Referenznummer", None), ("location", "Ort", None), ("source_url", "Quell-URL", None),
                               ("employment_type", "Beschäftigungsart", None), ("deadline", "Frist (JJJJ-MM-TT)", None), ("description", "Beschreibung", "multiline")]),
            "applications": ("Bewerbung", [("title", "Titel", "required"), ("company_id", "Unternehmen", company_choices),
                ("job_posting_id", "Stelle", [(_ui_tr('Ohne Stelle'), None), *[(f"{r['title']} · {r['company_name']}", r["id"]) for r in choices["jobs"]]]),
                ("applicant_profile_id", "Bewerberprofil", [(_ui_tr('Ohne Profil'), None), *[(r["display_name"], r["id"]) for r in choices["applicants"]]]),
                ("application_date", "Bewerbungsdatum (JJJJ-MM-TT)", None), ("next_follow_up_at", "Nachfassen (Datum + Uhrzeit + Zeitzone)", None),
                ("source", "Quelle", None), ("notes", "Notizen", "multiline")]),
        }
        name, specs = definitions[entity]
        if entity == 'jobs':
            specs.insert(-1,('start_date','Stellenbeginn (JJJJ-MM-TT)',None))
        self.address_values = json.loads(record.get('address_json','{}')) if record and entity in ('companies','contacts','applicants') else {}
        if entity in ('companies','contacts','applicants'):
            specs.extend(('address_'+key,caption,None) for key,caption in (('street','Straße / Hausnummer'),('postcode','Postleitzahl'),('city','Ort'),('country','Land')))
        if entity == "applications" and not record:
            specs.insert(1, ("status_code", "Status", [(r["label"], r["code"]) for r in data["statuses"]]))
        super().__init__(_ui_tr(name + (' bearbeiten' if record else ' anlegen')), specs, parent=parent)
        self.custom_fields = CustomFieldsEditor(self)
        self.custom_fields.populate(json.loads(record.get('custom_fields_json','{}')) if record else {})
        self.layout().insertWidget(1,self.custom_fields)
        self.resize(680, 620)
        self._busy = False
        if record:
            self.populate(record)
            for key,value in self.address_values.items():
                if 'address_'+key in self.fields:
                    self.fields['address_'+key].setText(str(value))
        elif entity == "applications":
            profile_id = data.get("defaults", {}).get("applicant_profile_id")
            self.fields["applicant_profile_id"].setCurrentIndex(max(0, self.fields["applicant_profile_id"].findData(profile_id)))
        self.baseline = self.values()
        if data.get("mail_receipts"):
            from .mail_page import STATUS
            from ..language import join_text
            self.layout().insertWidget(0, label(_ui_format('Versandstatus: {0}', join_text(' · ', (_ui_tr(STATUS.get(r['status'], r['status'])) for r in data['mail_receipts']))), 'muted'))
        if "next_follow_up_at" in self.fields:
            _ui_locale.set_placeholder(self.fields['next_follow_up_at'], _ui_tr('2026-10-20T09:00:00+02:00'))
        if entity == "jobs" and not choices["companies"]:
            self.layout().insertWidget(0, label(_ui_tr('Bitte zuerst ein Unternehmen anlegen.'), 'muted'))

    def validate(self):
        if self._busy:
            return
        if any(not self.fields[key].text().strip() for key in self.required):
            QMessageBox.warning(self, _ui_tr('Pflichtfeld'), _ui_tr('Bitte alle Pflichtfelder ausfüllen.'))
            return
        try:
            fields = self.values()
        except ValueError as error:
            QMessageBox.warning(self, _ui_tr('Zusatzfelder'), str(error))
            return
        if self.data["entity"] == "jobs" and not fields["company_id"]:
            QMessageBox.warning(self, _ui_tr('Unternehmen'), _ui_tr('Bitte ein Unternehmen für die Stelle auswählen.'))
            return
        payload = {"entity": self.data["entity"], "fields": fields}
        if self.data["record"]:
            # Preserve fields untouched in the editor, including imported whitespace.
            payload["fields"] = {key: value for key, value in fields.items() if value != self.baseline[key]}
            payload.update(record_id=self.data["record"]["id"], expected_version=self.data["version"])
        self.operation_requested.emit("update_record" if self.data["record"] else "create_record", payload)

    def values(self):
        fields = super().values()
        address = dict(self.address_values)
        for key in ('street','postcode','city','country'):
            if 'address_'+key in fields:
                value=fields.pop('address_'+key)
                if value: address[key]=value
                else: address.pop(key,None)
        if self.data['entity'] in ('companies','contacts','applicants'):
            fields['address_json']=json.dumps(address,ensure_ascii=False)
        fields['custom_fields_json']=json.dumps(self.custom_fields.values(),ensure_ascii=False)
        return fields

    def set_busy(self, busy):
        self._busy = busy
        for widget in self.fields.values():
            widget.setEnabled(not busy)
        self.custom_fields.setEnabled(not busy)
        self.buttons.setEnabled(not busy)

    def reject(self):
        if not self._busy:
            super().reject()


class ContactLinksDialog(QDialog):
    operation_requested = Signal(str, object)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Kontaktzuordnungen'))
        self.resize(700, 560)
        self._busy = False
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Kontakte zuordnen und ihre Rolle festlegen'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Zeile auswählen zum Bearbeiten. Entfernen löst die Zuordnung; der Kontakt bleibt erhalten.'), 'muted'))
        self.table = QTableWidget(0, 3)
        _ui_locale.headers(self.table, [_ui_tr('Kontakt'), _ui_tr('Rolle'), _ui_tr('Hauptkontakt')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.select_link)
        layout.addWidget(self.table, 1)
        form = QFormLayout()
        self.contact = QComboBox()
        self.contact.currentIndexChanged.connect(self.select_contact)
        self.role = QLineEdit()
        self.primary = _ui_locale.widget(QCheckBox, _ui_tr('Hauptkontakt des Unternehmens'))
        _ui_locale.add_row(form, _ui_tr('Kontakt'), self.contact)
        _ui_locale.add_row(form, _ui_tr('Rolle'), self.role)
        form.addRow(self.primary)
        layout.addLayout(form)
        self.save_button = button(_ui_tr('Zuordnung speichern'), self.save, primary=True)
        self.remove_button = button(_ui_tr('Ausgewählte Zuordnung entfernen'), self.remove)
        self.refresh_button = button(_ui_tr('Aktualisieren'), self.refresh)
        self.close_button = button(_ui_tr('Schließen'), self.reject)
        for control in (self.save_button, self.remove_button, self.refresh_button, self.close_button):
            layout.addWidget(control)
        self.populate(data)

    def populate(self, data):
        self.data = data
        self.table.blockSignals(True)
        self.contact.blockSignals(True)
        self.contact.clear()
        _ui_locale.add_item(self.contact, _ui_tr('Kontakt auswählen'), None)
        for record in data["choices"]:
            self.contact.addItem(record["display_name"], record["id"])
        self.table.setRowCount(len(data["rows"]))
        for index, record in enumerate(data["rows"]):
            name = record["display_name"] + (" (archiviert)" if record["deleted_at"] else "")
            for column, text in enumerate((name, record["relationship_type"] or "", "Ja" if record.get("is_primary") else "")):
                self.table.setItem(index, column, QTableWidgetItem(text))
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self.contact.blockSignals(False)
        self.role.clear()
        self.primary.setChecked(False)
        self.primary.setVisible(data["entity"] == "companies")
        self.set_busy(False)

    def selected(self):
        index = self.table.currentRow()
        return self.data["rows"][index] if self.table.selectedItems() and 0 <= index < len(self.data["rows"]) else None

    def select_link(self):
        record = self.selected()
        if record:
            index = self.contact.findData(record["id"])
            if index < 0:
                _ui_locale.add_item(self.contact, _ui_format('{0} (archiviert)', record['display_name']), record['id'])
                index = self.contact.count() - 1
            self.contact.setCurrentIndex(index)
            self.role.setText(record["relationship_type"] or "")
            self.primary.setChecked(bool(record.get("is_primary")))
        self.set_busy(self._busy)

    def select_contact(self):
        record = next((r for r in self.data["rows"] if r["id"] == self.contact.currentData()), None) if hasattr(self, "data") else None
        self.role.setText(record["relationship_type"] or "" if record else "")
        self.primary.setChecked(bool(record and record.get("is_primary")))
        self.set_busy(self._busy)

    def request(self, **fields):
        self.operation_requested.emit("save_record_link", {"entity": self.data["entity"], "record_id": self.data["record_id"],
                                       "expected_version": self.data["version"], **fields})

    def save(self):
        if not self._busy and self.contact.currentData():
            self.request(contact_id=self.contact.currentData(), relationship_type=self.role.text().strip() or None, is_primary=self.primary.isChecked())

    def remove(self):
        record = self.selected()
        if not self._busy and record:
            self.request(contact_id=record["id"], remove=True)

    def refresh(self):
        if not self._busy:
            self.operation_requested.emit("record_links", {"entity": self.data["entity"], "record_id": self.data["record_id"]})

    def set_busy(self, busy):
        self._busy = busy
        for control in (self.table, self.contact, self.role, self.primary, self.refresh_button, self.close_button):
            control.setEnabled(not busy)
        self.save_button.setEnabled(not busy and bool(self.contact.currentData()))
        self.remove_button.setEnabled(not busy and bool(self.selected()))

    def reject(self):
        if not self._busy:
            super().reject()
