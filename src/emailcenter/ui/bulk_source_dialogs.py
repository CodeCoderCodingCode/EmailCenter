"""Explicit import-column mapping and a manual table with Excel paste support."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

import csv
import io
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLineEdit,
    QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..bulk_sources import SOURCE_FIELDS, FIELD_NAME, column_fields
from ..mail_models import MailError, address
from .mail_template_dialogs import BusyDialog
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


class ImportRowsDialog(BusyDialog):
    def __init__(self, runs, fields, parent=None, *, profiles=(), for_documents=False):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Excel-/CSV-Zeilen für E-Mails und Dokumente'))
        self.resize(900, 720)
        self.fields = list(dict.fromkeys([*SOURCE_FIELDS, *fields]))
        self.for_documents = for_documents
        self.selected, self.mapping, self.data, self.offset = set(), {}, None, 0
        self.profiles, self.defaults = list(profiles), {}
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Geladene Importdaten verwenden'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Alle Quellspalten bleiben verfügbar. Im Builder kannst du Dateien direkt mit „Excel / CSV laden“ importieren. Ungültige Zeilen in der Quelldatei korrigieren und erneut laden.'), 'muted'))
        self.run = QComboBox()
        _ui_locale.add_item(self.run, _ui_tr('Importlauf auswählen'), None)
        for value in runs:
            sheet = " · " + value["sheet"] if value.get("sheet") else ""
            _ui_locale.add_item(self.run, _ui_format('{0}{1} · {2} Zeilen · {3}', f"{value['source_filename']}", f'{sheet}', f"{value['total_rows']}", f"{value['created_at'][:10]}"), value['id'])
        self.run.currentIndexChanged.connect(self.change_run)
        layout.addWidget(self.run)
        profile_row = QHBoxLayout()
        self.profile = QComboBox()
        _ui_locale.add_item(self.profile, _ui_tr('Zuordnungsprofil auswählen'), None)
        for profile in profiles:
            self.profile.addItem(profile["name"], profile["id"])
        profile_row.addWidget(self.profile, 1)
        self.profile_apply = button(_ui_tr('Profil anwenden'), self.apply_profile)
        self.profile_save = button(_ui_tr('Zuordnung speichern'), self.save_profile)
        profile_row.addWidget(self.profile_apply)
        profile_row.addWidget(self.profile_save)
        layout.addLayout(profile_row)
        self.fallback = _ui_locale.widget(QCheckBox, _ui_tr('Leere Quellwerte mit Standardwerten füllen'))
        self.fallback.setChecked(True)
        layout.addWidget(self.fallback)
        self.profile_notice = label(_ui_tr('Persönliche Überschreibungen haben Vorrang vor Quell- und Standardwerten.'), 'muted')
        layout.addWidget(self.profile_notice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.form = QFormLayout(content)
        scroll.setWidget(content)
        scroll.setMaximumHeight(260)
        layout.addWidget(scroll)
        self.rows = QTableWidget(0, 0)
        self.rows.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.rows.itemChanged.connect(self.check_changed)
        layout.addWidget(self.rows, 1)
        footer = ActionFlowLayout()
        self.summary = label(_ui_tr('Noch kein Importlauf gewählt.'), 'muted')
        self.previous = button(_ui_tr('Zurück'), lambda: self.move_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.move_page(1))
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.previous)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        layout.addWidget(button(_ui_tr('Sichtbare gültige Zeilen wählen'), self.select_visible))
        self.apply_button = button(_ui_tr('Gewählte Zeilen übernehmen'), self.apply, primary=True)
        layout.addWidget(self.apply_button)
        layout.addWidget(button(_ui_tr('Abbrechen'), self.reject))
        self.update_buttons()

    def change_run(self):
        self.selected.clear()
        self.offset, self.data = 0, None
        self.rows.setRowCount(0)
        _ui_locale.set_text(self.summary, _ui_tr('Importlauf auswählen und Spalten prüfen.'))
        self.load()
        self.update_buttons()

    def load(self):
        if self.run.currentData():
            self.operation_requested.emit("mail_bulk_source_rows", {"run_id": self.run.currentData(), "offset": self.offset})

    def move_page(self, direction):
        self.offset = max(0, self.offset + direction * 25)
        self.load()

    def display(self, data):
        rebuild = self.data is None or self.data["headers"] != data["headers"]
        self.data, self.offset = data, data["offset"]
        if rebuild:
            while self.form.rowCount():
                self.form.removeRow(0)
            self.mapping = {}
            self.defaults = {}
            suggestions = {"contact.display_name": ("name", "ansprechpartner", "kontakt", "display_name"),
                           "contact.email": ("e-mail", "email", "mail"), "contact.salutation": ("anrede", "salutation"),
                           "company.name": ("firma", "firmenname", "unternehmen", "company"),
                           "job.title": ("stelle", "position", "job"), "application.cover_letter": ("anschreiben", "cover_letter")}
            aliases = column_fields(data['headers'])
            by_header = {header: field for field, header in aliases.items()}
            fields = list(dict.fromkeys(by_header.get(field, field) for field in self.fields))
            for field in fields:
                if not isinstance(field, str) or not FIELD_NAME.fullmatch(field):
                    continue  # Unfinished editor rules must not invalidate the source selection.
                combo = QComboBox()
                _ui_locale.add_item(combo, _ui_tr('Nicht zugeordnet'), None)
                for header in data["headers"]:
                    combo.addItem(header, header)
                match = next((h for h in data["headers"] if h.casefold() in (field.casefold(), *suggestions.get(field, ()))), None)
                if field not in SOURCE_FIELDS and field in aliases:
                    match = aliases[field]
                combo.setCurrentIndex(max(0, combo.findData(match)))
                combo.currentIndexChanged.connect(self.update_buttons)
                default = QLineEdit()
                _ui_locale.set_placeholder(default, _ui_tr('Standardwert (optional)'))
                default.setMaxLength(32768)
                row = QHBoxLayout()
                row.addWidget(combo, 1)
                row.addWidget(default, 1)
                self.mapping[field] = combo
                self.defaults[field] = default
                _ui_locale.add_row(self.form, _ui_format('{0}{1}', _ui_tr(SOURCE_FIELDS[field]) if field in SOURCE_FIELDS else field, ' *' if not self.for_documents and field in ('contact.display_name', 'contact.email') else ''), row)
        self.rows.blockSignals(True)
        self.rows.setRowCount(len(data["rows"]))
        self.rows.setColumnCount(len(data["headers"]) + 2)
        _ui_locale.headers(self.rows, [_ui_tr('Auswahl / Zeile'), _ui_tr('Importstatus'), *data['headers']])
        for index, row in enumerate(data["rows"]):
            checkbox = QTableWidgetItem(str(row["number"]))
            checkbox.setData(Qt.ItemDataRole.UserRole, row["id"])
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable if row["eligible"] else Qt.ItemFlag.NoItemFlags)
            checkbox.setCheckState(Qt.CheckState.Checked if row["id"] in self.selected else Qt.CheckState.Unchecked)
            if not row['eligible']:
                checkbox.setToolTip('\n'.join(row.get('errors', [])))
            self.rows.setItem(index, 0, checkbox)
            for column, text in enumerate([row["status"], *[row["values"].get(h, "") for h in data["headers"]]], 1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.rows.setItem(index, column, item)
        self.rows.blockSignals(False)
        self.update_buttons()

    def check_changed(self, item):
        if item.column() != 0:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(identifier)
        else:
            self.selected.discard(identifier)
        self.update_buttons()

    def select_visible(self):
        if self.data:
            self.selected.update(row["id"] for row in self.data["rows"] if row["eligible"])
            self.display(self.data)

    def update_buttons(self):
        mapped = self.for_documents or all(self.mapping.get(key) and self.mapping[key].currentData() for key in ("contact.display_name", "contact.email"))
        self.apply_button.setEnabled(bool(mapped and 1 <= len(self.selected) <= 100))
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(bool(self.data and self.offset + 25 < self.data["total"]))
        self.profile_apply.setEnabled(bool(self.data))
        self.profile_save.setEnabled(bool(self.data))
        if self.data:
            _ui_locale.set_text(self.summary, _ui_format('{0} ausgewählt (max. 100) · {1} Zeilen · Seite {2}', f'{len(self.selected)}', f"{self.data['total']}", f'{self.offset // 25 + 1}'))

    def apply(self):
        if self.apply_button.isEnabled() and not self.busy:
            self.operation_requested.emit("mail_bulk_source_select", {"row_ids": sorted(self.selected),
                "mapping": {field: combo.currentData() for field, combo in self.mapping.items() if combo.currentData()},
                "defaults": {field: edit.text() for field, edit in self.defaults.items() if edit.text()},
                "empty_policy": "fallback" if self.fallback.isChecked() else "keep", "require_mail_fields": not self.for_documents})

    def apply_profile(self):
        profile = next((p for p in self.profiles if p["id"] == self.profile.currentData()), None)
        if not profile or not self.data:
            return
        missing = []
        for field, combo in self.mapping.items():
            column = profile["mapping"].get(field)
            index = combo.findData(column)
            if column and index < 0:
                missing.append(column)
            combo.setCurrentIndex(max(0, index))
            self.defaults[field].setText(profile["defaults"].get(field, ""))
        self.fallback.setChecked(profile["empty_policy"] == "fallback")
        _ui_locale.set_text(self.profile_notice, _ui_format('Fehlende Quellspalten neu zuordnen: {0}', ', '.join(missing)) if missing else _ui_tr('Profil angewendet. Spalten und Standards vor Übernahme prüfen.'))
        self.update_buttons()

    def save_profile(self):
        if self.busy or not self.data:
            return
        selected = next((p for p in self.profiles if p["id"] == self.profile.currentData()), None)
        name, accepted = QInputDialog.getText(self, _ui_tr('Zuordnungsprofil speichern'), _ui_tr('Profilname'), text=selected['name'] if selected else 'Neue Zuordnung')
        if not accepted:
            return
        existing = selected if selected and name.casefold() == selected["name"].casefold() else None
        self.operation_requested.emit("source_profile_save", {"name": name,
            "mapping": {key: combo.currentData() for key, combo in self.mapping.items() if combo.currentData()},
            "defaults": {key: edit.text() for key, edit in self.defaults.items() if edit.text()},
            "empty_policy": "fallback" if self.fallback.isChecked() else "keep",
            "profile_id": existing["id"] if existing else None, "expected_version": existing["version"] if existing else None})

    def display_profiles(self, value):
        self.profiles = value["profiles"]
        self.profile.clear()
        _ui_locale.add_item(self.profile, _ui_tr('Zuordnungsprofil auswählen'), None)
        for profile in self.profiles:
            self.profile.addItem(profile["name"], profile["id"])
        self.profile.setCurrentIndex(self.profile.findData(value["profile"]["id"]))
        _ui_locale.set_text(self.profile_notice, _ui_tr('Profil im Projekt gespeichert.'))


class PasteTable(QTableWidget):
    def paste_text(self, text):
        if len(text) > 2_000_000:
            raise ValueError(_ui_tr('Die eingefügte Tabelle ist zu groß.'))
        values = list(csv.reader(io.StringIO(text), delimiter="\t"))
        start_row, start_column = max(0, self.currentRow()), max(0, self.currentColumn())
        if start_row + len(values) > 100 or any(start_column + len(row) > self.columnCount() for row in values):
            raise ValueError(_ui_tr('Höchstens 100 Zeilen und die vorhandenen Spalten einfügen.'))
        if any(len(value) > 32768 or "\x00" in value for row in values for value in row):
            raise ValueError(_ui_tr('Ein Feld ist zu lang oder enthält ungültige Zeichen.'))
        self.setRowCount(max(self.rowCount(), start_row + len(values)))
        for i, row in enumerate(values, start_row):
            for j, value in enumerate(row, start_column):
                self.setItem(i, j, QTableWidgetItem(value))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            try:
                self.paste_text(QApplication.clipboard().text())
            except (ValueError, csv.Error) as error:
                QMessageBox.warning(self, _ui_tr('Tabelle nicht eingefügt'), str(error))
            event.accept()
        else:
            super().keyPressEvent(event)


class ManualRowsDialog(BusyDialog):
    rows_ready = Signal(object)

    def __init__(self, fields, parent=None, *, lists=()):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Manuelle Liste · Bewerbungen und E-Mails'))
        self.resize(1000, 660)
        self.fields = list(dict.fromkeys([*SOURCE_FIELDS, *fields]))
        self.pending_cell = None
        self.saved_list = None
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Manuelle Empfängerliste'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Werte eintippen oder Excel-Zellen mit Strg+V einfügen (ohne Kopfzeile, Reihenfolge unten beachten). Maximal 100 Zeilen.'), 'muted'))
        list_row = QHBoxLayout()
        self.list_choice = QComboBox()
        _ui_locale.add_item(self.list_choice, _ui_tr('Neue manuelle Liste'), None)
        for entry in lists:
            _ui_locale.add_item(self.list_choice, _ui_format('{0} · {1} Zeilen', f"{entry['name']}", f"{entry['count']}"), entry['id'])
        self.list_choice.currentIndexChanged.connect(self.load_list)
        list_row.addWidget(self.list_choice, 1)
        list_row.addWidget(button(_ui_tr('Als neue Kopie'), self.new_copy))
        layout.addLayout(list_row)
        self.list_name = QLineEdit("Neue Datenliste")
        layout.addWidget(self.list_name)
        self.rows = PasteTable(1, len(self.fields))
        _ui_locale.headers(self.rows, [_ui_tr(SOURCE_FIELDS[f]) if f in SOURCE_FIELDS else f for f in self.fields])
        self.rows.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.rows, 1)
        actions = ActionFlowLayout()
        actions.addWidget(button(_ui_tr('Zeile hinzufügen'), self.add_row))
        actions.addWidget(button(_ui_tr('Gewählte Zeile entfernen'), self.remove_row))
        actions.addWidget(button(_ui_tr('DOCX-Text in gewählte Zelle'), self.load_docx))
        layout.addLayout(actions)
        tables = QHBoxLayout()
        self.pdf_strategy = QComboBox()
        _ui_locale.add_item(self.pdf_strategy, _ui_tr('PDF: Zelllinien'), 'lines')
        _ui_locale.add_item(self.pdf_strategy, _ui_tr('PDF: Textspalten (unsicher)'), 'text')
        tables.addWidget(self.pdf_strategy)
        tables.addWidget(button(_ui_tr('DOCX-/PDF-Tabelle laden …'), self.load_tables))
        layout.addLayout(tables)
        self.save_list_button = button(_ui_tr('Liste im Projekt speichern'), self.save_list)
        layout.addWidget(self.save_list_button)
        self.list_state = label(_ui_tr('Ohne Speichern kann die Liste direkt für diese Gruppe übernommen werden.'), 'muted')
        layout.addWidget(self.list_state)
        layout.addWidget(button(_ui_tr('Liste übernehmen'), self.apply, primary=True))
        layout.addWidget(button(_ui_tr('Abbrechen'), self.reject))

    def add_row(self):
        if self.rows.rowCount() < 100:
            self.rows.setRowCount(self.rows.rowCount() + 1)

    def remove_row(self):
        if self.rows.currentRow() >= 0:
            self.rows.removeRow(self.rows.currentRow())

    def load_docx(self):
        if self.rows.currentRow() < 0 or self.rows.currentColumn() < 0:
            QMessageBox.warning(self, _ui_tr('Zelle auswählen'), _ui_tr('Die Zielzelle für den Dokumenttext auswählen, z. B. Anschreiben.'))
            return
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Dokumenttext übernehmen'), filter='Word-Dokument (*.docx)')
        if path:
            self.pending_cell = (self.rows.currentRow(), self.rows.currentColumn())
            self.operation_requested.emit("mail_bulk_docx_text", {"path": path})

    def display_text(self, data):
        if self.pending_cell:
            self.rows.setItem(*self.pending_cell, QTableWidgetItem(data["text"]))
            self.pending_cell = None

    def load_tables(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Tabellenquelle wählen'), filter='Dokumente (*.docx *.pdf)')
        if path:
            self.operation_requested.emit("source_document_tables", {"path": path, "pdf_strategy": self.pdf_strategy.currentData()})

    def display_tables(self, value):
        from .document_table_dialog import DocumentTableDialog
        self.table_review = DocumentTableDialog(value, self.fields, self, capacity=100-len(self.capture_rows()))
        self.table_review.rows_ready.connect(self.append_document_rows)
        self.table_review.open()

    def append_document_rows(self, rows):
        entries = self.capture_rows()
        if len(entries) + len(rows) > 100:
            QMessageBox.warning(self, _ui_tr('Liste ist zu groß'), _ui_tr('Zusammen maximal 100 Zeilen. Vorhandene Zeilen entfernen oder weniger Tabellenzeilen wählen.'))
            return
        fields = list(dict.fromkeys([*self.fields, *(key for row in rows for key in row)]))
        if len(fields) > 200:
            QMessageBox.warning(self, _ui_tr('Zu viele Felder'), _ui_tr('Die gemeinsame Liste unterstützt höchstens 200 Felder. Eine neue Liste verwenden.'))
            return
        self.fields = fields
        # Rebuild from captured rows so blank starter rows and column shifts cannot lose existing values.
        self.rows.setRowCount(0)
        self.rows.setColumnCount(len(self.fields))
        _ui_locale.headers(self.rows, [_ui_tr(SOURCE_FIELDS[f]) if f in SOURCE_FIELDS else f for f in self.fields])
        for entry in [*entries, *({"id": str(uuid4()), "fields": row} for row in rows)]:
            index = self.rows.rowCount()
            self.rows.insertRow(index)
            marker = QTableWidgetItem(str(index + 1))
            marker.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.rows.setVerticalHeaderItem(index, marker)
            for column, field in enumerate(self.fields):
                self.rows.setItem(index, column, QTableWidgetItem(entry["fields"].get(field, "")))
        _ui_locale.set_text(self.list_state, _ui_format('{0} Dokumentzeilen übernommen. Werte prüfen, ergänzen und bei Bedarf als gemeinsame Liste speichern.', f'{len(rows)}'))

    def capture_rows(self):
        entries = []
        for index in range(self.rows.rowCount()):
            fields = {name: self.rows.item(index, column).text() if self.rows.item(index, column) else "" for column, name in enumerate(self.fields)}
            if not any(value.strip() for value in fields.values()):
                continue
            marker = self.rows.verticalHeaderItem(index)
            if marker is None:
                marker = QTableWidgetItem(str(index + 1))
                self.rows.setVerticalHeaderItem(index, marker)
            key = marker.data(Qt.ItemDataRole.UserRole) or str(uuid4())
            marker.setData(Qt.ItemDataRole.UserRole, key)
            entries.append({"id": key, "fields": fields})
        return entries

    def load_list(self):
        if self.busy:
            return
        if self.list_choice.currentData():
            if self.rows.rowCount() and any(self.rows.item(r, c) and self.rows.item(r, c).text().strip() for r in range(self.rows.rowCount()) for c in range(self.rows.columnCount())):
                if QMessageBox.question(self, _ui_tr('Datenliste laden'), _ui_tr('Die aktuelle Tabelle durch die gespeicherte Liste ersetzen? Ungespeicherte Eingaben gehen verloren.')) != QMessageBox.StandardButton.Yes:
                    self.list_choice.blockSignals(True)
                    self.list_choice.setCurrentIndex(max(0, self.list_choice.findData(self.saved_list["id"] if self.saved_list else None)))
                    self.list_choice.blockSignals(False)
                    return
            self.operation_requested.emit("source_list_details", {"list_id": self.list_choice.currentData()})
        else:
            if self.saved_list:
                self.new_copy()

    def new_copy(self):
        self.saved_list = None
        self.list_choice.blockSignals(True)
        self.list_choice.setCurrentIndex(0)
        self.list_choice.blockSignals(False)
        for row in range(self.rows.rowCount()):
            marker = self.rows.verticalHeaderItem(row)
            if marker:
                marker.setData(Qt.ItemDataRole.UserRole, None)
        self.list_name.setText(self.list_name.text() + " Kopie")
        _ui_locale.set_text(self.list_state, _ui_tr('Neue Kopie: eigene Zeilenkennungen; ursprüngliche Liste bleibt erhalten.'))

    def display_list(self, value):
        self.saved_list = value
        self.list_name.setText(value["name"])
        self.fields = list(dict.fromkeys([*self.fields, *(key for row in value["rows"] for key in row["fields"])]))
        self.rows.setRowCount(0)
        self.rows.setColumnCount(len(self.fields))
        _ui_locale.headers(self.rows, [_ui_tr(SOURCE_FIELDS[f]) if f in SOURCE_FIELDS else f for f in self.fields])
        for row in value["rows"]:
            index = self.rows.rowCount()
            self.rows.insertRow(index)
            marker = QTableWidgetItem(str(index + 1))
            marker.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.rows.setVerticalHeaderItem(index, marker)
            for column, field in enumerate(self.fields):
                self.rows.setItem(index, column, QTableWidgetItem(row["fields"].get(field, "")))
        _ui_locale.set_text(self.list_state, _ui_tr('Gespeicherte Liste geladen. Änderungen können gespeichert oder als manuelle Kopie übernommen werden.'))

    def save_list(self):
        if not self.busy:
            self.operation_requested.emit("source_list_save", {"name": self.list_name.text(), "rows": self.capture_rows(),
                "list_id": self.saved_list["id"] if self.saved_list else None,
                "expected_version": self.saved_list["version"] if self.saved_list else None})

    def list_saved(self, value):
        self.list_choice.blockSignals(True)
        self.list_choice.clear()
        _ui_locale.add_item(self.list_choice, _ui_tr('Neue manuelle Liste'), None)
        for entry in value["lists"]:
            _ui_locale.add_item(self.list_choice, _ui_format('{0} · {1} Zeilen', f"{entry['name']}", f"{entry['count']}"), entry['id'])
        self.list_choice.setCurrentIndex(self.list_choice.findData(value["list"]["id"]))
        self.list_choice.blockSignals(False)
        self.display_list(value["list"])
        _ui_locale.set_text(self.list_state, _ui_tr('Liste im Projekt gespeichert; in Bulk und Word Replace wiederverwendbar.'))

    def apply(self):
        if self.busy:
            return
        entries = self.capture_rows()
        if self.saved_list and len(entries) == len(self.saved_list["rows"]) and all(
                entry["id"] == saved["id"] and entry["fields"] == {field: saved["fields"].get(field, "") for field in self.fields}
                for entry, saved in zip(entries, self.saved_list["rows"])):
            self.operation_requested.emit("source_list_select", {"list_id": self.saved_list["id"], "row_ids": [entry["id"] for entry in entries]})
            return
        result = []
        for index in range(self.rows.rowCount()):
            fields = {name: self.rows.item(index, column).text() if self.rows.item(index, column) else ""
                      for column, name in enumerate(self.fields)}
            if not any(value.strip() for value in fields.values()):
                continue
            try:
                address(fields["contact.email"])
                error = ""
            except MailError as failure:
                error = str(failure)
            result.append({"id": "manual:" + str(uuid4()), "display_name": fields["contact.display_name"],
                           "email": fields["contact.email"], "error": error, "duplicate": False,
                           "source": {"kind": "manual", "fields": fields}, "source_values": fields})
        if not result:
            QMessageBox.warning(self, _ui_tr('Liste ist leer'), _ui_tr('Mindestens eine Zeile mit Daten eingeben.'))
            return
        self.rows_ready.emit({"contacts": result})
        self.accept()
