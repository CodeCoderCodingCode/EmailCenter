"""Import mapping, persisted row review and resumable batches."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .dialogs import FormDialog
from .pages import button, label
from .responsive import ActionFlowLayout


TARGETS = {"contacts": "Kontakte", "companies": "Unternehmen", "applications": "Bewerbungen", "data_rows": "Datenquelle (Builder / Word Replace)"}
ROW_LABELS = {"Pending": "Noch zu prüfen", "Valid": "Bereit", "Invalid": "Ungültig",
              "DuplicateReview": "Duplikat prüfen", "Imported": "Importiert", "Failed": "Fehlgeschlagen", "Skipped": "Übersprungen"}
RUN_LABELS = {"Pending": "Bereit / fortsetzbar", "Running": "In Bearbeitung / fortsetzbar",
              "Completed": "Abgeschlossen", "CompletedWithErrors": "Fehler / Prüfung offen", "Failed": "Fehlgeschlagen", "Cancelled": "Angehalten"}


class ImportMappingDialog(QDialog):
    operation_requested = Signal(str, object)

    def __init__(self, inspection, parent=None, *, source_only=False):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Import zuordnen und prüfen'))
        self.resize(880, 760)
        self._busy = False
        self.source_only = source_only
        self.inspection = inspection
        self.mapping_widgets = {}
        layout = QVBoxLayout(self)
        self.description = label("", "muted")
        layout.addWidget(self.description)
        form = QFormLayout()
        self.target = QComboBox()
        for key, caption in TARGETS.items():
            _ui_locale.add_item(self.target, _ui_tr(caption), key)
        _ui_locale.add_row(form, _ui_tr('Importziel'), self.target)
        self.profile = QComboBox()
        _ui_locale.add_item(self.profile, _ui_tr('Neue Zuordnung'), None)
        self.profiles = {p["id"]: p for p in inspection["profiles"] if p["file_type"] == inspection["file_type"]}
        for profile in self.profiles.values():
            self.profile.addItem(profile["name"], profile["id"])
        _ui_locale.add_row(form, _ui_tr('Gespeichertes Profil'), self.profile)
        self.sheet = QComboBox()
        self.encoding = QComboBox()
        for caption, value in (("Automatisch", "auto"), ("UTF-8", "utf-8-sig"), ("Windows-1252", "cp1252")):
            _ui_locale.add_item(self.encoding, _ui_tr(caption), value)
        self.delimiter = QComboBox()
        for caption, value in (("Automatisch", "auto"), ("Semikolon", ";"), ("Komma", ","), ("Tab", "\t"), ("Pipe", "|")):
            _ui_locale.add_item(self.delimiter, _ui_tr(caption), value)
        if inspection["file_type"] == "xlsx":
            _ui_locale.add_row(form, _ui_tr('Tabellenblatt'), self.sheet)
        else:
            _ui_locale.add_row(form, _ui_tr('Zeichensatz'), self.encoding)
            _ui_locale.add_row(form, _ui_tr('Trennzeichen'), self.delimiter)
        self.profile_name = QLineEdit()
        _ui_locale.set_placeholder(self.profile_name, _ui_tr('Optional: Name für ein neues Importprofil'))
        _ui_locale.add_row(form, _ui_tr('Als neues Profil speichern'), self.profile_name)
        layout.addLayout(form)
        layout.addWidget(label(_ui_tr('Zuordnungen sind Vorschläge. Prüfe sie vor dem Anlegen der Zeilenvorschau.'), 'muted'))
        self.mapping_table = QTableWidget(0, 2)
        _ui_locale.headers(self.mapping_table, ['Zielfeld (* Pflicht)', _ui_tr('Quellspalte')])
        self.mapping_table.verticalHeader().hide()
        self.mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.mapping_table, 1)
        layout.addWidget(label(_ui_tr('Auszug der Quelldatei (erste 20 Zeilen)'), 'muted'))
        self.sample = QTableWidget()
        self.sample.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sample, 1)
        self.busy_label = label("", "muted")
        layout.addWidget(self.busy_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Zeilenvorschau anlegen'))
        _ui_locale.set_text(buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        buttons.accepted.connect(self.prepare)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.target.currentIndexChanged.connect(self.rebuild_mapping)
        self.profile.currentIndexChanged.connect(self.apply_profile)
        self.sheet.currentIndexChanged.connect(self.reinspect)
        self.encoding.currentIndexChanged.connect(self.reinspect)
        self.delimiter.currentIndexChanged.connect(self.reinspect)
        self.update_inspection(inspection)
        if source_only:
            self.target.setCurrentIndex(self.target.findData('data_rows'))
            self.target.setEnabled(False)
            self.profile.setEnabled(False)
            self.profile_name.setEnabled(False)

    def update_inspection(self, inspection):
        self.inspection = inspection
        _ui_locale.set_text(self.description, _ui_format('{0} · {1} Datenzeilen', f"{Path(inspection['source_path']).name}", f"{inspection['total_rows']}"))
        for combo in (self.sheet, self.encoding, self.delimiter):
            combo.blockSignals(True)
        self.sheet.clear()
        self.sheet.addItems(inspection["sheets"])
        if inspection["file_type"] == "xlsx":
            self.sheet.setCurrentText(inspection["options"]["sheet"])
        else:
            self.encoding.setCurrentIndex(self.encoding.findData(inspection["options"]["encoding"]))
            self.delimiter.setCurrentIndex(self.delimiter.findData(inspection["options"]["delimiter"]))
        for combo in (self.sheet, self.encoding, self.delimiter):
            combo.blockSignals(False)
        headers = inspection["headers"]
        self.sample.setColumnCount(len(headers))
        self.sample.setHorizontalHeaderLabels(headers)
        self.sample.setRowCount(len(inspection["sample"]))
        for index, record in enumerate(inspection["sample"]):
            for column, header in enumerate(headers):
                item = QTableWidgetItem(record.get(header, ""))
                self.sample.setItem(index, column, item)
        self.rebuild_mapping()

    def rebuild_mapping(self, *args):
        entity = self.target.currentData()
        fields = self.inspection["fields"][entity]
        profile = self.profiles.get(self.profile.currentData())
        mapping = (profile["mapping"] if profile and profile["options"].get("entity") == entity
                   else self.inspection["suggestions"][entity])
        self.mapping_widgets = {}
        self.mapping_table.setRowCount(len(fields))
        for index, (field, caption, mandatory) in enumerate(fields):
            self.mapping_table.setCellWidget(index, 0, label(_ui_format('{0}{1}', _ui_tr(caption), ' *' if mandatory else '')))
            combo = QComboBox()
            _ui_locale.add_item(combo, _ui_tr('Nicht importieren'), None)
            for header in self.inspection["headers"]:
                combo.addItem(header, header)
            combo.setCurrentIndex(max(0, combo.findData(mapping.get(field))))
            self.mapping_widgets[field] = combo
            self.mapping_table.setCellWidget(index, 1, combo)

    def source_options(self):
        if self.inspection["file_type"] == "xlsx":
            return {"sheet": self.sheet.currentText()}
        return {"encoding": self.encoding.currentData(), "delimiter": self.delimiter.currentData()}

    def apply_profile(self, *args):
        profile = self.profiles.get(self.profile.currentData())
        if profile:
            entity = profile["options"].get("entity")
            if entity in TARGETS:
                self.target.setCurrentIndex(self.target.findData(entity))
            for combo, key in ((self.encoding, "encoding"), (self.delimiter, "delimiter")):
                if key in profile["options"]:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(max(0, combo.findData(profile["options"][key])))
                    combo.blockSignals(False)
            if profile["options"].get("sheet") in self.inspection["sheets"]:
                self.sheet.blockSignals(True)
                self.sheet.setCurrentText(profile["options"]["sheet"])
                self.sheet.blockSignals(False)
            self.reinspect()
        self.rebuild_mapping()

    def reinspect(self, *args):
        if not self._busy:
            self.operation_requested.emit("inspect_builder_source" if self.source_only else "inspect_import", {"source_path": self.inspection["source_path"], "options": self.source_options()})

    def prepare(self):
        entity = self.target.currentData()
        mapping = {field: combo.currentData() for field, combo in self.mapping_widgets.items() if combo.currentData()}
        missing = [caption for field, caption, mandatory in self.inspection["fields"][entity] if mandatory and field not in mapping]
        if missing or len(set(mapping.values())) != len(mapping):
            QMessageBox.warning(self, _ui_tr('Spaltenzuordnung'), _ui_tr('Pflichtfelder zuordnen und jede Quellspalte höchstens einmal verwenden.'))
            return
        self.operation_requested.emit("prepare_builder_source" if self.source_only else "prepare_import", {
            "source_path": self.inspection["source_path"], "entity": entity, "mapping": mapping,
            "options": self.source_options(), "expected_hash": self.inspection["source_hash"],
            "profile_id": self.profile.currentData(), "profile_name": self.profile_name.text().strip() or None,
        })

    def set_busy(self, busy):
        self._busy = busy
        self.setEnabled(not busy)
        _ui_locale.set_text(self.busy_label, _ui_tr('Datei wird gelesen und geprüft …') if busy else '')

    def reject(self):
        if not self._busy:
            super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
        else:
            super().closeEvent(event)


class ImportPage(QWidget):
    operation_requested = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.run, self.run_id, self.rows = None, None, []
        self.row_offset, self.history_offset, self.history_total = 0, 0, 0
        self.auto_running = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)
        layout.addWidget(label(_ui_tr('Datenimport'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('CSV oder Excel prüfen, gültige Zeilen übernehmen und unterbrochene Läufe fortsetzen.'), 'muted'))
        top = QHBoxLayout()
        top.addWidget(button(_ui_tr('CSV / Excel auswählen'), self.choose_source, primary=True))
        top.addWidget(button(_ui_tr('Läufe aktualisieren'), self.request_history))
        top.addStretch()
        layout.addLayout(top)
        history = QHBoxLayout()
        self.history = QComboBox()
        self.history.currentIndexChanged.connect(self.select_run)
        history.addWidget(self.history, 1)
        self.history_previous = button(_ui_tr('Vorherige Seite'), lambda: self.history_page(-1))
        self.history_next = button(_ui_tr('Weitere Läufe'), lambda: self.history_page(1))
        history.addWidget(self.history_previous)
        history.addWidget(self.history_next)
        layout.addLayout(history)
        self.summary = label(_ui_tr('Datei auswählen oder einen gespeicherten Lauf öffnen.'), 'muted')
        layout.addWidget(self.summary)
        controls = ActionFlowLayout()
        self.process_button = button(_ui_tr('Gültige Zeilen importieren / fortsetzen'), self.start_import, primary=True)
        self.edit_button = button(_ui_tr('Zeile korrigieren'), self.edit_selected)
        self.skip_button = button(_ui_tr('Überspringen'), lambda: self.review_selected('skip'))
        self.force_button = button(_ui_tr('Duplikat als neu freigeben'), lambda: self.review_selected('import_new'))
        for control in (self.process_button, self.edit_button, self.skip_button, self.force_button):
            controls.addWidget(control)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 4)
        _ui_locale.headers(self.table, [_ui_tr('Zeile'), _ui_tr('Status'), _ui_tr('Zugeordnete Werte'), _ui_tr('Hinweise')])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_controls)
        layout.addWidget(self.table, 1)
        footer = ActionFlowLayout()
        self.result_label = label("", "muted")
        footer.addWidget(self.result_label, 1)
        self.previous = button(_ui_tr('Zurück'), lambda: self.row_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.row_page(1))
        footer.addWidget(self.previous)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self.reset()

    def reset(self):
        self.run, self.run_id, self.rows, self.auto_running = None, None, [], False
        self.row_offset, self.history_offset, self.history_total = 0, 0, 0
        self.history.blockSignals(True)
        self.history.clear()
        self.history.blockSignals(False)
        self.table.setRowCount(0)
        _ui_locale.set_text(self.summary, _ui_tr('Datei auswählen oder einen gespeicherten Lauf öffnen.'))
        _ui_locale.set_text(self.result_label, '')
        self.history_previous.setEnabled(False)
        self.history_next.setEnabled(False)
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.update_controls()

    def choose_source(self):
        source, _ = QFileDialog.getOpenFileName(self, _ui_tr('Importdatei wählen'), '', _ui_tr('Tabellendaten (*.csv *.xlsx)'))
        if source:
            self.operation_requested.emit("inspect_import", {"source_path": source})

    def request_history(self):
        self.operation_requested.emit("import_runs", {"offset": self.history_offset, "limit": 25})

    def history_page(self, direction):
        self.history_offset = max(0, self.history_offset + direction * 25)
        self.run_id = None
        self.request_history()

    def display_history(self, result):
        self.history_total = result["total"]
        self.history.blockSignals(True)
        self.history.clear()
        for run in result["rows"]:
            _ui_locale.add_item(self.history, _ui_format("{0} · {1} · {2}", run["source_filename"], _ui_tr(RUN_LABELS.get(run["status"], run["status"])), run["created_at"][:19]), run["id"])
        selected = self.history.findData(self.run_id)
        self.history.setCurrentIndex(selected if selected >= 0 else (0 if result["rows"] else -1))
        self.history.blockSignals(False)
        self.history_previous.setEnabled(self.history_offset > 0)
        self.history_next.setEnabled(self.history_offset + len(result["rows"]) < result["total"])
        if self.history.currentData():
            self.select_run()
        else:
            self.run_id, self.run, self.rows = None, None, []
            self.table.setRowCount(0)
            _ui_locale.set_text(self.summary, _ui_tr('Datei auswählen oder einen gespeicherten Lauf öffnen.'))
            self.update_controls()

    def select_run(self, *args):
        selected = self.history.currentData()
        if selected:
            if selected != self.run_id:
                self.row_offset = 0
                self.run, self.rows = None, []
                self.table.setRowCount(0)
                _ui_locale.set_text(self.summary, _ui_tr('Importlauf wird geladen …'))
                self.update_controls()
            self.run_id = selected
            self.request_rows()

    def set_run(self, run):
        if self.run_id != run["id"]:
            self.row_offset = 0
        self.run, self.run_id = run, run["id"]
        index = self.history.findData(run["id"])
        if index >= 0:
            self.history.setItemText(index, f"{run['source_filename']} · {RUN_LABELS.get(run['status'], run['status'])} · {run['created_at'][:19].replace('T', ' ')} UTC")
        counts = run["counts"]
        _ui_locale.set_text(self.summary, _ui_format('{0} · {1}\n{2} bereit · {3} importiert · {4} fehlerhaft · {5} Duplikate prüfen · {6} übersprungen', f"{run['source_filename']}", f"{TARGETS[run['configuration']['entity']]}", f"{counts.get('Valid', 0)}", f"{counts.get('Imported', 0)}", f"{counts.get('Invalid', 0) + counts.get('Failed', 0)}", f"{counts.get('DuplicateReview', 0)}", f"{counts.get('Skipped', 0)}"))
        self.update_controls()

    def request_rows(self):
        if self.run_id:
            self.operation_requested.emit("import_rows", {"run_id": self.run_id, "offset": self.row_offset, "limit": 50})

    def display_rows(self, result):
        self.set_run(result["run"])
        self.rows = result["rows"]
        self.table.setRowCount(len(self.rows))
        fields = result["run"]["configuration"]["entity"]
        captions = dict((key, caption) for key, caption, required in import_fields(fields))
        for index, row in enumerate(self.rows):
            values = " · ".join(f"{captions.get(key, key)}: {value}" for key, value in row["mapped_data"]["fields"].items())
            contents = [str(row["row_number"]), _ui_tr(ROW_LABELS.get(row["status"], row["status"])), values, " · ".join(row["errors"])]
            for column, content in enumerate(contents):
                item = QTableWidgetItem(content)
                item.setToolTip(content)
                self.table.setItem(index, column, item)
        first = self.row_offset + 1 if self.rows else 0
        _ui_locale.set_text(self.result_label, _ui_format('{0}–{1} von {2} Zeilen', f'{first}', f'{self.row_offset + len(self.rows)}', f"{result['total']}"))
        self.previous.setEnabled(self.row_offset > 0)
        self.next.setEnabled(self.row_offset + len(self.rows) < result["total"])
        self.table.clearSelection()
        self.update_controls()

    def row_page(self, direction):
        self.row_offset = max(0, self.row_offset + direction * 50)
        self.request_rows()

    def selected(self):
        row = self.table.currentRow()
        return self.rows[row] if self.table.selectedItems() and 0 <= row < len(self.rows) else None

    def update_controls(self):
        selected = self.selected()
        editable = selected is not None and selected["status"] not in ("Imported", "Skipped")
        self.process_button.setEnabled(bool(self.run and self.run["counts"].get("Valid", 0)))
        self.edit_button.setEnabled(editable and self.run['configuration']['entity'] != 'data_rows')
        self.skip_button.setEnabled(editable)
        self.force_button.setEnabled(bool(selected and selected["status"] == "DuplicateReview"))

    def start_import(self):
        if self.run_id:
            self.auto_running = True
            self.continue_import()

    def continue_import(self):
        if self.auto_running and self.run and self.run["counts"].get("Valid", 0):
            self.operation_requested.emit("process_import", {"run_id": self.run_id, "max_rows": 100})

    def edit_selected(self):
        row = self.selected()
        if row is None or self.run is None:
            return
        specs = [(key, caption, "multiline" if key == "notes" else "required" if mandatory else None) for key, caption, mandatory in import_fields(self.run["configuration"]["entity"])]
        dialog = FormDialog(_ui_format('Importzeile {0} korrigieren', f"{row['row_number']}"), specs, parent=self)
        for key, widget in dialog.fields.items():
            value = str(row["mapped_data"]["fields"].get(key) or "")
            if isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value)
            else:
                widget.setMaxLength(32768)
                _ui_locale.set_text(widget, value)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.operation_requested.emit("edit_import_row", {"row_id": row["id"], "fields": dialog.values()})

    def review_selected(self, decision):
        row = self.selected()
        if row:
            self.operation_requested.emit("review_import_row", {"row_id": row["id"], "decision": decision})


def import_fields(entity):
    # Field descriptors contain no infrastructure or database access.
    from ..import_sources import FIELDS
    return FIELDS[entity]
