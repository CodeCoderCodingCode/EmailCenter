"""Own document workspace with shared sources, literal rules and reviewed output."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QAbstractButton, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QProgressBar

from ..bulk_sources import SOURCE_FIELDS
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


class WordReplacePage(QWidget):
    operation_requested = Signal(str, object)
    source_requested = Signal(str)
    cancel_requested = Signal()
    settings_requested = Signal()
    path_requested = Signal(str)

    def __init__(self, preferences):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)
        self.data, self.sources, self.preview, self.busy, self.project_path = {}, [], None, False, None
        self.run, self.auto_run = None, False
        self.source_fields = list(SOURCE_FIELDS)
        self.preferences = preferences
        self._settings_applied = False
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label(_ui_tr('Word Replace'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Wörter und Platzhalter in DOCX-Kopien ersetzen. Werte direkt eingeben oder dieselben Excel-/Listendaten wie für Bulk verwenden.'), 'muted'))
        form = QFormLayout()
        self.source_path = QLineEdit()
        _ui_locale.set_placeholder(self.source_path, _ui_tr('DOCX-Original auswählen'))
        path_row = QHBoxLayout()
        path_row.addWidget(self.source_path, 1)
        path_row.addWidget(button(_ui_tr('DOCX wählen'), self.choose_source))
        self.analyze_button = button(_ui_tr('Platzhalter erkennen'), self.analyze)
        path_row.addWidget(self.analyze_button)
        _ui_locale.add_row(form, _ui_tr('Eingabe'), path_row)
        layout.addLayout(form)
        self.source_buttons = [button(_ui_tr('Excel-/CSV-Zeilen'), lambda: self.source_requested.emit('import')),
            button(_ui_tr('Datenliste / manuelle Liste'), lambda: self.source_requested.emit('manual')),
            button(_ui_tr('Datenquelle entfernen'), self.clear_sources), button(_ui_tr('Word-Replace-Einstellungen'), self.settings_requested.emit)]
        self.source_actions = QGridLayout()
        layout.addLayout(self.source_actions)
        self.source_status = label(_ui_tr('Einzeldatei: direkte Ersatzwerte verwenden.'), 'muted')
        layout.addWidget(self.source_status)
        self.rules = QTableWidget(0, 3)
        _ui_locale.headers(self.rules, [_ui_tr('Suchen'), _ui_tr('Ersatztext'), _ui_tr('Datenfeld')])
        for column, description in enumerate(("Wort oder {{Platzhalter}} suchen", "Direkter Ersatzwert; leer entfernt den Suchtext", "Datenfeld verwenden statt direktem Ersatzwert")):
            self.rules.horizontalHeaderItem(column).setToolTip(description)
        self.rules.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules.setMinimumHeight(180)
        self.rules.setMaximumHeight(300)
        self.rules.itemChanged.connect(self.invalidate)
        layout.addWidget(self.rules)
        row_actions = ActionFlowLayout()
        row_actions.addWidget(button(_ui_tr('Regel hinzufügen'), lambda: self.add_rule()))
        row_actions.addWidget(button(_ui_tr('Gewählte Regel entfernen'), self.remove_rule))
        layout.addLayout(row_actions)
        self.options_layout = QGridLayout()
        self.case_sensitive = _ui_locale.widget(QCheckBox, _ui_tr('Groß-/Kleinschreibung beachten'))
        self.whole_words = _ui_locale.widget(QCheckBox, _ui_tr('Nur ganze Wörter'))
        self.missing = QComboBox()
        _ui_locale.add_item(self.missing, _ui_tr('Fehlende Daten sperren Ausgabe'), 'error')
        _ui_locale.add_item(self.missing, _ui_tr('Fehlende Daten: Originaltext behalten'), 'keep')
        layout.addLayout(self.options_layout)
        self.recipient = QComboBox()
        self.recipient.currentIndexChanged.connect(self.show_row)
        layout.addWidget(self.recipient)
        splitter = self.comparison = QSplitter()
        before, after = QWidget(), QWidget()
        before_layout, after_layout = QVBoxLayout(before), QVBoxLayout(after)
        before_layout.addWidget(label(_ui_tr('Original · Textvorschau')))
        self.before = QPlainTextEdit()
        self.before.setReadOnly(True)
        before_layout.addWidget(self.before)
        after_layout.addWidget(label(_ui_tr('Ergebnis · Textvorschau')))
        self.after = QPlainTextEdit()
        self.after.setReadOnly(True)
        after_layout.addWidget(self.after)
        splitter.addWidget(before)
        splitter.addWidget(after)
        splitter.setMinimumHeight(240)
        layout.addWidget(splitter)
        self.hits = QListWidget()
        self.hits.setMaximumHeight(100)
        layout.addWidget(self.hits)
        layout.addWidget(label(_ui_tr('Textvorschau zeigt bis zu 50000 Zeichen; Fundstellen bis zu 1000. Ersetzungen bleiben innerhalb eines Absatzes. Ersatzformatierung unten wählen; Layout im Ergebnis prüfen. Dauerhafte Läufe behalten fertige Ausgaben nach Pause oder Abbruch.'), 'muted'))
        output = QFormLayout()
        output.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.output_directory = QLineEdit()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.output_directory, 1)
        folder_row.addWidget(button(_ui_tr('Ausgabeordner wählen'), self.choose_directory))
        _ui_locale.add_row(output, _ui_tr('Zielordner'), folder_row)
        self.prefix = QLineEdit("Dokument")
        _ui_locale.add_row(output, _ui_tr('Dateinamen-Präfix'), self.prefix)
        self.filename_pattern = QLineEdit()
        self.filename_pattern.setMaxLength(200)
        _ui_locale.set_placeholder(self.filename_pattern, _ui_tr('Leer = bisherige Namen; z. B. {prefix}-{number:03d}-{name}'))
        _ui_locale.add_row(output, _ui_tr('Dateinamensmuster'), self.filename_pattern)
        self.replacement_style = QComboBox()
        for title, value in (("Ersten Text-Run übernehmen", "first"), ("Absatzstandard", "plain"), ("Fett", "bold"), ("Kursiv", "italic")):
            _ui_locale.add_item(self.replacement_style, _ui_tr(title), value)
        _ui_locale.add_row(output, _ui_tr('Ersatzformatierung'), self.replacement_style)
        self.replacement_style.currentIndexChanged.connect(self.invalidate)
        self.run_history = QComboBox()
        _ui_locale.add_row(output, _ui_tr('Gespeicherte Läufe'), self.run_history)
        history = ActionFlowLayout()
        history.addWidget(button(_ui_tr('Lauf laden'), self.load_run))
        self.resume_button = button(_ui_tr('Offene Zeilen fortsetzen'), self.resume_run)
        history.addWidget(self.resume_button)
        output.addRow(history)
        self.file_format = QComboBox()
        _ui_locale.add_item(self.file_format, _ui_tr('DOCX'), 'docx')
        _ui_locale.add_item(self.file_format, _ui_tr('PDF (LibreOffice)'), 'pdf')
        _ui_locale.add_row(output, _ui_tr('Ausgabeformat'), self.file_format)
        layout.addLayout(output)
        self.footer = QWidget()
        footer = QVBoxLayout(self.footer)
        footer.setContentsMargins(24, 8, 24, 16)
        outer.addWidget(self.footer)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Alle Regeln und Zeilenergebnisse geprüft; Ausgabe bestätigen'))
        footer.addWidget(self.confirm)
        self.status = label(_ui_tr('DOCX wählen und Regeln anlegen. Eine Vorschau erzeugt keine dauerhafte Ausgabedatei.'), 'muted')
        footer.addWidget(self.status)
        self.run_progress = QProgressBar()
        self.run_progress.hide()
        footer.addWidget(self.run_progress)
        self.footer_actions = QGridLayout()
        self.preview_button = button(_ui_tr('Vorschau aller Zeilen'), self.request_preview)
        self.create_button = button(_ui_tr('Ausgabekopien erstellen'), self.create, primary=True)
        self.cancel_button = button(_ui_tr('Lauf pausieren / Vorgang abbrechen'), self.pause_run)
        self.open_button = button(_ui_tr('Ausgabeordner öffnen'), lambda: self.path_requested.emit(self.output_directory.text()))
        self.output_buttons = (self.preview_button, self.create_button, self.cancel_button, self.open_button)
        footer.addLayout(self.footer_actions)
        self.confirm.toggled.connect(self.update_buttons)
        self.source_path.textChanged.connect(self.invalidate)
        self.case_sensitive.toggled.connect(self.invalidate)
        self.whole_words.toggled.connect(self.invalidate)
        self.missing.currentIndexChanged.connect(self.invalidate)
        self.file_format.currentIndexChanged.connect(self.invalidate)
        self.apply_settings(preferences)
        compact_forms(self)
        self.reflow()
        self.update_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        if not hasattr(self, "output_buttons"):
            return
        wide = self.width() >= 900
        for grid, controls in ((self.source_actions, self.source_buttons), (self.footer_actions, self.output_buttons)):
            columns = 4 if wide else 2
            for index, control in enumerate(controls):
                grid.removeWidget(control)
                grid.addWidget(control, index // columns, index % columns)
        for index, control in enumerate((self.case_sensitive, self.whole_words, self.missing)):
            self.options_layout.removeWidget(control)
            self.options_layout.addWidget(control, 0 if wide else index, index if wide else 0)
        self.comparison.setOrientation(Qt.Orientation.Horizontal if wide else Qt.Orientation.Vertical)

    def apply_settings(self, preferences):
        previous, initial = self.preferences, not self._settings_applied
        self.preferences = preferences
        changed = initial
        for key, widget in (("word_replace_case_sensitive", self.case_sensitive), ("word_replace_whole_words", self.whole_words),
                            ("word_replace_missing", self.missing), ("word_replace_format", self.file_format), ("word_replace_style", self.replacement_style)):
            if initial or getattr(previous, key) != getattr(preferences, key):
                changed = True
                value = getattr(preferences, key)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(value)
                else:
                    widget.setCurrentIndex(max(0, widget.findData(value)))
        if initial or previous.word_replace_directory != preferences.word_replace_directory:
            self.output_directory.setText(preferences.word_replace_directory or (str(self.project_path / "exports/word_replace") if self.project_path else ""))
        if initial or previous.word_replace_filename_pattern != preferences.word_replace_filename_pattern:
            self.filename_pattern.setText(preferences.word_replace_filename_pattern)
        changed = changed or previous.libreoffice_path != preferences.libreoffice_path or previous.conversion_timeout != preferences.conversion_timeout
        self._settings_applied = True
        if changed:
            self.invalidate()

    def reset(self, project_path=None):
        self.project_path = Path(project_path) if project_path else None
        self.sources, self.data = [], {}
        self.run, self.auto_run = None, False
        self.run_history.clear()
        self.run_progress.hide()
        self.source_fields = list(SOURCE_FIELDS)
        self.source_path.clear()
        self.rules.setRowCount(0)
        _ui_locale.clear_text(self.before)
        _ui_locale.clear_text(self.after)
        self.hits.clear()
        self.recipient.clear()
        self.output_directory.setText(getattr(self.preferences, "word_replace_directory", "") or str(self.project_path / "exports/word_replace") if self.project_path else "")
        self.setEnabled(bool(project_path))
        self.clear_sources()

    def request_load(self):
        self.operation_requested.emit("word_replace_details", {})

    def display_details(self, data):
        self.data = data
        previous = self.run_history.currentData()
        self.run_history.clear()
        for run in data.get("replacement_runs", []):
            self.run_history.addItem(f"{run['name']} · {run['completed']}/{run['total']} · {run['status']}", run["id"])
        self.run_history.setCurrentIndex(max(0, self.run_history.findData(previous)))

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Word-Replace-Original wählen'), filter='Word-Dokument (*.docx)')
        if path:
            self.source_path.setText(path)
            self.analyze()

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, _ui_tr('Word-Replace-Ausgabeordner'), self.output_directory.text())
        if path:
            self.output_directory.setText(path)

    def analyze(self):
        if not self.busy and self.source_path.text().strip():
            self.operation_requested.emit("word_replace_analyze", {"source_path": self.source_path.text()})

    def display_analysis(self, value):
        _ui_locale.set_plain_text(self.before, value['text'])
        existing = {self.rules.item(row, 0).text() for row in range(self.rules.rowCount()) if self.rules.item(row, 0)}
        for placeholder in value["placeholders"]:
            find = "{{" + placeholder + "}}"
            if find not in existing:
                self.add_rule(find=find)
        _ui_locale.set_text(self.status, _ui_format('{0} Platzhalter erkannt. Ersatzwert oder Datenfeld je Regel wählen.', f"{len(value['placeholders'])}"))

    def fields(self):
        return list(dict.fromkeys([*SOURCE_FIELDS, *self.source_fields, *[rule["field"] for rule in self.rule_values() if rule["field"]]]))

    def add_sources(self, value):
        self.sources = [contact["source"] for contact in value["contacts"]]
        self.source_fields = list(dict.fromkeys([*SOURCE_FIELDS, *(key for contact in value["contacts"] for key in contact["source_values"])]))
        _ui_locale.set_text(self.source_status, _ui_format('{0} Datenzeilen gewählt · eine eigene Ausgabekopie je Zeile', f'{len(self.sources)}'))
        for row in range(self.rules.rowCount()):
            combo = self.rules.cellWidget(row, 2)
            selected = self.field_value(combo)
            self.populate_field(combo, selected)
        self.invalidate()

    def clear_sources(self):
        self.sources = []
        _ui_locale.set_text(self.source_status, _ui_tr('Einzeldatei: direkte Ersatzwerte verwenden.'))
        self.invalidate()

    @staticmethod
    def field_value(combo):
        if combo.currentText() != combo.itemText(combo.currentIndex()):
            return combo.currentText().strip()
        return "" if combo.currentIndex() == 0 else combo.currentData() or combo.currentText().strip()

    def populate_field(self, combo, field=""):
        combo.blockSignals(True)
        combo.clear()
        _ui_locale.add_item(combo, _ui_tr('Direkter Ersatzwert'), None)
        for key in self.source_fields:
            _ui_locale.add_item(combo, (_ui_tr(SOURCE_FIELDS[key]) if key in SOURCE_FIELDS else key), key)
        if field and combo.findData(field) < 0:
            combo.addItem(field, field)
        combo.setCurrentIndex(max(0, combo.findData(field)))
        combo.blockSignals(False)

    def add_rule(self, find="", replacement="", field=""):
        row = self.rules.rowCount()
        self.rules.insertRow(row)
        self.rules.setItem(row, 0, QTableWidgetItem(find))
        self.rules.setItem(row, 1, QTableWidgetItem(replacement))
        combo = QComboBox()
        combo.setEditable(True)
        self.populate_field(combo, field)
        combo.currentTextChanged.connect(self.invalidate)
        self.rules.setCellWidget(row, 2, combo)
        self.invalidate()

    def remove_rule(self):
        if self.rules.currentRow() >= 0:
            self.rules.removeRow(self.rules.currentRow())
            self.invalidate()

    def rule_values(self):
        return [{"find": self.rules.item(row, 0).text() if self.rules.item(row, 0) else "",
                 "replacement": self.rules.item(row, 1).text() if self.rules.item(row, 1) else "",
                 "field": self.field_value(self.rules.cellWidget(row, 2)) if self.rules.cellWidget(row, 2) else ""} for row in range(self.rules.rowCount())]

    def invalidate(self):
        self.preview = None
        self.confirm.setChecked(False)
        self.update_buttons()

    def update_buttons(self):
        if not hasattr(self, "preview_button"):
            return
        ready = bool(self.preview and self.preview["ready"])
        self.preview_button.setEnabled(not self.busy and bool(self.source_path.text().strip()) and self.rules.rowCount() > 0)
        self.confirm.setEnabled(not self.busy and ready)
        self.create_button.setEnabled(not self.busy and not self.auto_run and ready and self.confirm.isChecked())
        self.cancel_button.setVisible(self.busy or self.auto_run)
        self.cancel_button.setEnabled(self.busy or self.auto_run)
        self.resume_button.setEnabled(not self.busy and not self.auto_run and bool(self.run and self.run["completed"] < self.run["total"]))
        self.open_button.setEnabled(not self.busy and bool(self.output_directory.text()))

    def request_preview(self):
        if self.busy:
            return
        self.invalidate()
        self.operation_requested.emit("word_replace_preview", {"source_path": self.source_path.text(), "rules": self.rule_values(),
            "sources": self.sources or None, "case_sensitive": self.case_sensitive.isChecked(), "whole_words": self.whole_words.isChecked(),
            "missing_policy": self.missing.currentData(), "file_format": self.file_format.currentData(),
            "replacement_style": self.replacement_style.currentData(),
            "libreoffice_path": getattr(self.preferences, "libreoffice_path", ""), "conversion_timeout": getattr(self.preferences, "conversion_timeout", 120)})

    def display_preview(self, value):
        self.preview = value
        _ui_locale.set_plain_text(self.before, value['before'])
        self.recipient.blockSignals(True)
        self.recipient.clear()
        for row in value["rows"]:
            _ui_locale.add_item(self.recipient, _ui_format('{0} · {1} · {2}', row['number'], row['name'] or _ui_tr('Einzeldatei'), _ui_tr('Prüfen') if row['error'] else _ui_tr('Bereit')), row['number'])
        self.recipient.blockSignals(False)
        self.recipient.setCurrentIndex(0)
        self.show_row()
        _ui_locale.set_text(self.status, _ui_format('{0} Ergebnisse · {1}', len(value['rows']), _ui_tr('Vorschau prüfen und Ausgabekopien bestätigen.') if value['ready'] else _ui_tr('Fehler oder fehlende Daten korrigieren.')))
        self.update_buttons()

    def show_row(self):
        if not self.preview or self.recipient.currentIndex() < 0:
            return
        row = self.preview["rows"][self.recipient.currentIndex()]
        _ui_locale.set_plain_text(self.after, row['error'] or row['text'])
        self.hits.clear()
        if row["missing"]:
            _ui_locale.add_item(self.hits, _ui_format('Fehlende Daten, Originaltext bleibt: {0}', ', '.join(row['missing'])))
        if row.get("unresolved"):
            _ui_locale.add_item(self.hits, _ui_format('Verbleibende Platzhalter im Ergebnis: {0}', ', '.join(row['unresolved'])))
        for hit in row["occurrences"]:
            _ui_locale.add_item(self.hits, _ui_format('{0} · Absatz {1} · {2} → {3} · {4}', _ui_tr(hit['part']), f"{hit['paragraph']}", f"{hit['find']}", f"{hit['replacement']}", f"{hit['context']}"))

    def create(self):
        if self.busy or not self.create_button.isEnabled():
            return
        overwrite = QMessageBox.question(self, _ui_tr('Word-Replace-Ausgabe'), _ui_tr('Ausgabekopien erstellen? Vorhandene Dateien mit denselben Namen ersetzen? Ja = Ersetzen erlauben, Nein = nur neue Dateien, Abbrechen = zurück.'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if overwrite == QMessageBox.StandardButton.Cancel:
            return
        self.operation_requested.emit("word_replace_create", {"preview_id": self.preview["preview_id"], "output_directory": self.output_directory.text(),
            "prefix": self.prefix.text(), "overwrite": overwrite == QMessageBox.StandardButton.Yes, "filename_pattern": self.filename_pattern.text(), "durable": True})

    def created(self, value):
        if value.get("run"):
            self.auto_run = True
            self.display_run(value["run"])
            return
        self.invalidate()
        _ui_locale.set_text(self.status, _ui_format("{0} {1}-Kopien erstellt: {2}", value["count"], value["format"].upper(), "; ".join(value["paths"])))

    def load_run(self):
        if not self.busy and self.run_history.currentData():
            self.auto_run = False
            self.operation_requested.emit("word_replace_run_load", {"run_id": self.run_history.currentData()})

    def resume_run(self):
        if self.run and not self.busy and QMessageBox.question(self, _ui_tr('Gespeicherten Lauf fortsetzen'), _ui_tr('Offene Zeilen mit den gespeicherten Originalen, Regeln und Werten erzeugen? Bereits fertige Dateien werden geprüft und erhalten.')) == QMessageBox.StandardButton.Yes:
            self.auto_run = True
            self.advance_run()

    def advance_run(self):
        if self.auto_run and self.run and not self.busy:
            self.operation_requested.emit("word_replace_run_next", {"run_id": self.run["id"]})

    def pause_run(self):
        self.auto_run = False
        if self.busy:
            self.cancel_requested.emit()
        elif self.run:
            self.operation_requested.emit("word_replace_run_pause", {"run_id": self.run["id"]})

    def display_run(self, value):
        self.run = value
        self.run_progress.show()
        self.run_progress.setRange(0, value["total"])
        self.run_progress.setValue(value["completed"])
        errors = [item["last_error"] for item in value["items"] if item["status"] == "Failed"]
        _ui_locale.set_text(self.status, _ui_format("Lauf {0}: {1}/{2} fertig · {3}", value["name"], value["completed"], value["total"], " · ".join(errors) if errors else _ui_tr("Feste Regeln und Zeilenwerte gespeichert.")))
        self.status.setToolTip("\n".join(item["output_path"] for item in value["items"]))
        if errors or value["completed"] == value["total"]:
            self.auto_run = False
        self.update_buttons()
        if self.auto_run:
            QTimer.singleShot(0, self.advance_run)

    def set_busy(self, busy):
        self.busy = busy
        # Disable inputs individually so cancellation remains reachable inside this page.
        for widget in self.content.findChildren(QWidget):
            if isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QTableWidget)) and widget is not self.cancel_button:
                widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy or self.auto_run)
        self.update_buttons()
