"""Explicit filtered or selected export with column choice and a local preview."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..export_service import EXPORTS
from .mail_template_dialogs import BusyDialog
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


class ExportDialog(BusyDialog):
    cancel_requested = Signal()
    bundle_requested = Signal()

    def __init__(self, project_path, parent=None, *, entity="contacts", search="", selected_ids=None, defaults=None, batch_id=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Daten exportieren'))
        self.resize(900, 720)
        self.project_path, self.preview, self.loading = Path(project_path), None, False
        self.initial_entity, self.selected_ids, self.batch_id = entity, selected_ids or [], batch_id
        self.initial_columns, self.defaults = None, defaults or {}
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('CSV / Excel exportieren'), 'pageTitle'))
        self.content = QWidget()
        content = QVBoxLayout(self.content)
        form = QFormLayout()
        self.entity = QComboBox()
        for key, (caption, *_) in EXPORTS.items():
            _ui_locale.add_item(self.entity, _ui_tr(caption), key)
        self.entity.setCurrentIndex(max(0, self.entity.findData(entity)))
        self.entity.setEnabled(batch_id is None)
        _ui_locale.add_row(form, _ui_tr('Daten'), self.entity)
        self.scope = QComboBox()
        _ui_locale.add_item(self.scope, _ui_tr('Aktueller Filter / alle Treffer'), 'filtered')
        _ui_locale.add_item(self.scope, _ui_format('Ausgewählte Datensätze ({0})', f'{len(self.selected_ids)}'), 'selected')
        _ui_locale.add_row(form, _ui_tr('Umfang'), self.scope)
        self.search = QLineEdit(search)
        _ui_locale.set_placeholder(self.search, _ui_tr('Name / Firma / Status suchen; leer = alle'))
        _ui_locale.add_row(form, _ui_tr('Suchfilter'), self.search)
        self.format = QComboBox()
        _ui_locale.add_item(self.format, _ui_tr('CSV'), 'csv')
        _ui_locale.add_item(self.format, _ui_tr('Excel (.xlsx)'), 'xlsx')
        self.format.setCurrentIndex(max(0, self.format.findData(self.defaults.get("export_format", "csv"))))
        _ui_locale.add_row(form, _ui_tr('Dateiformat'), self.format)
        self.delimiter = QComboBox()
        for caption, value in (("Semikolon ;", ";"), ("Komma ,", ","), ("Tabulator", "\t")):
            _ui_locale.add_item(self.delimiter, _ui_tr(caption), value)
        self.delimiter.setCurrentIndex(max(0, self.delimiter.findData(self.defaults.get("csv_delimiter", ";"))))
        _ui_locale.add_row(form, _ui_tr('CSV-Trennzeichen'), self.delimiter)
        self.encoding = QComboBox()
        for caption, value in (("UTF-8 mit BOM (Excel)", "utf-8-sig"), ("UTF-8", "utf-8"), ("Windows-1252", "cp1252"), ("UTF-16", "utf-16")):
            _ui_locale.add_item(self.encoding, _ui_tr(caption), value)
        self.encoding.setCurrentIndex(max(0, self.encoding.findData(self.defaults.get("csv_encoding", "utf-8-sig"))))
        _ui_locale.add_row(form, _ui_tr('CSV-Zeichensatz'), self.encoding)
        content.addLayout(form)
        self.columns = QListWidget()
        self.columns.setMaximumHeight(150)
        self.columns.itemChanged.connect(self.show_preview)
        content.addWidget(self.columns)
        self.table = QTableWidget()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        content.addWidget(self.table, 1)
        layout.addWidget(self.content, 1)
        self.status = label(_ui_tr('Vorschau laden; bis zu 10000 Zeilen. Formelzeichen werden als Text exportiert.'), 'muted')
        layout.addWidget(self.status)
        layout.addWidget(button(_ui_tr('DOCX / PDF als Dokumentpaket exportieren …'), self.bundle_requested.emit))
        actions = ActionFlowLayout()
        self.preview_button = button(_ui_tr('Vorschau laden'), self.request_preview)
        self.export_button = button(_ui_tr('Datei exportieren'), self.export, primary=True)
        self.cancel_button = button(_ui_tr('Laufenden Export abbrechen'), self.cancel_requested.emit)
        self.close_button = button(_ui_tr('Schließen'), self.reject)
        for control in (self.preview_button, self.export_button, self.cancel_button, self.close_button):
            actions.addWidget(control)
        layout.addLayout(actions)
        for widget in (self.entity, self.scope):
            widget.currentIndexChanged.connect(self.invalidate)
        self.search.textChanged.connect(self.invalidate)
        self.format.currentIndexChanged.connect(self.update_buttons)
        self.invalidate()

    def invalidate(self):
        self.preview = None
        _ui_locale.set_text(self.status, _ui_tr('Auswahl geändert: Exportvorschau erneut laden.'))
        self.update_buttons()

    def update_buttons(self):
        valid_selection = self.entity.currentData() == self.initial_entity and bool(self.selected_ids)
        self.scope.model().item(1).setEnabled(valid_selection)
        if not valid_selection and self.scope.currentData() == "selected":
            self.scope.setCurrentIndex(0)
        self.search.setEnabled(self.scope.currentData() != "selected" and not self.busy)
        self.delimiter.setEnabled(self.format.currentData() == "csv")
        self.encoding.setEnabled(self.format.currentData() == "csv")
        self.preview_button.setEnabled(not self.busy)
        self.export_button.setEnabled(bool(not self.busy and self.preview and self.preview["total"] and self.selected_columns()))
        self.cancel_button.setVisible(self.busy)
        self.close_button.setEnabled(not self.busy)

    def selected_columns(self):
        return [self.columns.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.columns.count()) if self.columns.item(i).checkState() == Qt.CheckState.Checked]

    def request_preview(self):
        if not self.busy:
            self.preview = None
            self.update_buttons()
            selected = self.scope.currentData() == "selected"
            self.operation_requested.emit("export_preview", {"entity": self.entity.currentData(), "search": "" if selected else self.search.text(),
                "selected_ids": self.selected_ids if selected else None, "batch_id": self.batch_id})

    def display(self, value):
        previous = set(self.selected_columns()) if self.initial_columns == value["entity"] else None
        self.preview, self.initial_columns, self.loading = value, value["entity"], True
        self.columns.clear()
        for column in value["columns"]:
            item = QListWidgetItem(column["caption"])
            item.setData(Qt.ItemDataRole.UserRole, column["key"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if previous is None or column["key"] in previous else Qt.CheckState.Unchecked)
            self.columns.addItem(item)
        self.loading = False
        self.show_preview()

    def show_preview(self):
        if self.loading or not self.preview:
            return
        keys = self.selected_columns()
        captions = {column["key"]: column["caption"] for column in self.preview["columns"]}
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels([captions[key] for key in keys])
        self.table.setRowCount(min(20, self.preview["total"]))
        for index, row in enumerate(self.preview["rows"][:20]):
            for column, key in enumerate(keys):
                item = QTableWidgetItem("" if row[key] is None else str(row[key]))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(index, column, item)
        _ui_locale.set_text(self.status, _ui_format('{0} Zeilen · {1} Spalten · Vorschau zeigt die ersten 20 Zeilen. Ausgabe verändert keine Projektdaten.', f"{self.preview['total']}", f'{len(keys)}'))
        self.update_buttons()

    def export(self):
        if self.busy or not self.export_button.isEnabled():
            return
        file_format = self.format.currentData()
        folder = Path(self.defaults.get("export_directory") or self.project_path / "exports")
        path, _ = QFileDialog.getSaveFileName(self, _ui_tr('Export speichern'), str(folder / (self.preview['entity'] + '.' + file_format)), _ui_tr('Excel (*.xlsx)') if file_format == 'xlsx' else _ui_tr('CSV (*.csv)'), options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix("." + file_format)
        overwrite = target.exists()
        if overwrite and QMessageBox.question(self, _ui_tr('Exportdatei ersetzen'), _ui_format('Die vorhandene Datei {0} ersetzen?', f'{target.name}')) != QMessageBox.StandardButton.Yes:
            return
        self.operation_requested.emit("export_write", {"preview_id": self.preview["preview_id"], "columns": self.selected_columns(),
            "target_path": str(target), "file_format": file_format, "delimiter": self.delimiter.currentData(),
            "encoding": self.encoding.currentData(), "overwrite": overwrite})

    def written(self, value):
        self.preview = None
        _ui_locale.set_text(self.status, _ui_format('{0} Zeilen exportiert: {1}', f"{value['count']}", f"{value['path']}"))
        self.update_buttons()

    def set_busy(self, busy):
        self.busy = busy
        self.content.setEnabled(not busy)
        self.update_buttons()
