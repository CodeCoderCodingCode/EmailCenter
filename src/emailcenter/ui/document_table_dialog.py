"""Review detected cells and deliberately map selected rows into a shared list."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                              QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from ..bulk_sources import FIELD_NAME, SOURCE_FIELDS
from .mail_template_dialogs import BusyDialog
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


class DocumentTableDialog(BusyDialog):
    rows_ready = Signal(object)

    def __init__(self, value, fields, parent=None, *, capacity=100):
        super().__init__(parent)
        self.value, self.fields, self.mapping = value, list(fields), []
        self.capacity = max(0, min(100, capacity))
        _ui_locale.set_window_title(self, _ui_tr('Dokumenttabelle prüfen und zuordnen'))
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_format('{0} · erkannte Tabellen', value['filename']), 'pageTitle'))
        self.choice = QComboBox()
        for index, table in enumerate(value["tables"]):
            self.choice.addItem(table["title"], index)
        layout.addWidget(self.choice)
        self.header = _ui_locale.widget(QCheckBox, _ui_tr('Erste Zeile ist eine Kopfzeile'))
        self.header.setChecked(True)
        layout.addWidget(self.header)
        self.notice = label("", "muted")
        layout.addWidget(self.notice)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table, 2)
        self.mapping_scroll = QScrollArea()
        self.mapping_scroll.setWidgetResizable(True)
        self.mapping_scroll.setMaximumHeight(190)
        layout.addWidget(self.mapping_scroll, 1)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Zellen, Kopfzeile und Spaltenzuordnung geprüft; gewählte Zeilen übernehmen'))
        layout.addWidget(self.confirm)
        self.status = label("", "muted")
        layout.addWidget(self.status)
        actions = ActionFlowLayout()
        self.apply_button = button(_ui_tr('In manuelle Liste übernehmen'), self.apply, primary=True)
        actions.addWidget(self.apply_button)
        actions.addWidget(button(_ui_tr('Abbrechen'), self.reject))
        layout.addLayout(actions)
        self.choice.currentIndexChanged.connect(self.display)
        self.header.toggled.connect(self.display)
        self.confirm.toggled.connect(self.update_apply)
        self.table.itemSelectionChanged.connect(self.invalidate)
        self.display()

    def display(self):
        value = self.value["tables"][self.choice.currentData()]
        raw = value["rows"]
        headers = raw[0] if self.header.isChecked() else [f"Spalte {i+1}" for i in range(len(raw[0]))]
        self.data = raw[1:] if self.header.isChecked() else raw
        self.headers = headers
        self.table.setRowCount(0)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.data))
        for index, row in enumerate(self.data):
            for column, text in enumerate(row):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, min(320, max(100, self.table.columnWidth(column))))
        self.table.horizontalHeader().setStretchLastSection(True)
        body, self.mapping = QWidget(), []
        form = QFormLayout(body)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for index, header in enumerate(headers):
            choice = QComboBox()
            choice.setEditable(True)
            _ui_locale.add_item(choice, _ui_tr('Nur als Quellspalte behalten'), '')
            for field in self.fields:
                _ui_locale.add_item(choice, _ui_format('{0} · {1}', _ui_tr(SOURCE_FIELDS[field]) if field in SOURCE_FIELDS else field, field), field)
            choice.currentTextChanged.connect(self.invalidate)
            self.mapping.append(choice)
            form.addRow(f"{index + 1}. {header or '(leer)'}", choice)
        self.mapping_scroll.setWidget(body)
        _ui_locale.set_text(self.notice, ' · '.join(value['warnings']) or _ui_tr('DOCX-Zellstruktur erkannt; Inhalte und verbundene Zellen vor Übernahme prüfen.'))
        if len(self.data) <= 100:
            self.table.selectAll()
        self.invalidate()

    def invalidate(self):
        self.confirm.setChecked(False)
        self.update_apply()

    def update_apply(self):
        count = len(self.table.selectionModel().selectedRows())
        _ui_locale.set_text(self.status, _ui_format('{0} Zeilen gewählt · noch {1} freie Listenzeilen. Alle Quellspalten und Dateiherkunft bleiben erhalten. Zuordnung kann anschließend korrigiert werden.', f'{count}', f'{self.capacity}'))
        self.apply_button.setEnabled(bool(0 < count <= self.capacity and self.confirm.isChecked() and not self.busy))

    def mapped_rows(self):
        fields = [choice.currentData() if choice.currentIndex() >= 0 and choice.currentText() == choice.itemText(choice.currentIndex()) else choice.currentText().strip() for choice in self.mapping]
        used = [field for field in fields if field]
        if any(not FIELD_NAME.fullmatch(field) or field.startswith(("source.", "document.")) for field in used) or len(set(used)) != len(used):
            raise ValueError(_ui_tr('Jede Zielspalte nur einmal zuordnen; eigene Feldnamen wie cover_letter oder company.name verwenden.'))
        table = self.value["tables"][self.choice.currentData()]
        result = []
        for selection in sorted(self.table.selectionModel().selectedRows(), key=lambda item: item.row()):
            index = selection.row()
            values = {f"document.column_{column+1}": text for column, text in enumerate(self.data[index])}
            values.update({f"document.header_{column+1}": text for column, text in enumerate(self.headers)})
            values.update({field: self.data[index][column] for column, field in enumerate(fields) if field})
            values.update({"source.filename": self.value["filename"], "source.sha256": self.value["sha256"],
                           "source.table": table["title"], "source.page": str(table["page"] or ""),
                           "source.row": str(index + (2 if self.header.isChecked() else 1))})
            result.append(values)
        return result

    def apply(self):
        if not self.apply_button.isEnabled():
            return
        try:
            rows = self.mapped_rows()
        except ValueError as error:
            QMessageBox.warning(self, _ui_tr('Zuordnung prüfen'), str(error))
            return
        self.rows_ready.emit(rows)
        self.accept()
