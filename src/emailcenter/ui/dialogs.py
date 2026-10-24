"""Small reusable entry forms and document inspection dialogs."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
import json

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter,
    QTableWidget, QTabWidget, QVBoxLayout, QWidget,
)

from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


class FormDialog(QDialog):
    def __init__(self, title, specifications, *, parent=None, owned_captions=True):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr(title))
        self.resize(500, 380)
        layout = QVBoxLayout(self)
        content = QWidget()
        form = QFormLayout(content)
        self.fields, self.required = {}, []
        for key, caption, options in specifications:
            if isinstance(options, list):
                widget = QComboBox()
                for name, value in options:
                    _ui_locale.add_item(widget, name, value)
            elif options == "multiline":
                widget = QPlainTextEdit()
                widget.setMaximumHeight(120)
            else:
                widget = QLineEdit()
                widget.setMaxLength(32768)
                if options == "required":
                    self.required.append(key)
                    caption = _ui_format('{0} *', _ui_tr(caption, context='field') if owned_captions else caption)
            widget.setObjectName(key)
            self.fields[key] = widget
            _ui_locale.add_row(form, _ui_tr(caption, context='field') if owned_captions else caption, widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(label(_ui_tr('* Pflichtfeld'), 'muted'))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Speichern'))
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        self.buttons.accepted.connect(self.validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        compact_forms(self)

    def validate(self):
        for key in self.required:
            if not self.fields[key].text().strip():
                self.fields[key].setFocus()
                QMessageBox.warning(self, _ui_tr('Pflichtfeld'), _ui_tr('Bitte alle Pflichtfelder ausfüllen.'))
                return
        self.accept()

    def values(self):
        result = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                result[key] = widget.currentData()
            elif isinstance(widget, QPlainTextEdit):
                result[key] = widget.toPlainText().strip() or None
            else:
                result[key] = widget.text().strip() or None
        return result

    def populate(self, values):
        for key, widget in self.fields.items():
            value = values.get(key)
            if isinstance(widget, QComboBox):
                index = widget.findData(value)
                if index < 0:
                    _ui_locale.add_item(widget, _ui_tr('Nicht verfügbar (bestehende Zuordnung)'), value)
                    index = widget.count() - 1
                widget.setCurrentIndex(index)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value or "")
            else:
                widget.setMaxLength(max(32768, len(value or "")))
                widget.setText(value or "")


FIELD_PATHS = (
    ("Manuell beim Erzeugen", ""), ("Profil: Name", "applicant.display_name"),
    ("Profil: E-Mail", "applicant.email"), ("Profil: Telefon", "applicant.phone"),
    ("Unternehmen: Name", "company.name"), ("Unternehmen: Website", "company.website"),
    ("Bewerbung: Titel", "application.title"), ("Bewerbung: Datum", "application.application_date"),
    ("Kontakt: Name", "contact.display_name"), ("Kontakt: E-Mail", "contact.email"),
)


class TemplateDialog(QDialog):
    def __init__(self, source_path, placeholders, *, record=None, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Neue Vorlagenversion') if record else _ui_tr('Vorlage importieren'))
        self.resize(700, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(label(Path(source_path).name, "muted"))
        form = QFormLayout()
        self.name = QLineEdit(record["template_name"] if record else Path(source_path).stem)
        self.name.setReadOnly(bool(record))
        _ui_locale.add_row(form, _ui_tr('Vorlagenname *'), self.name)
        layout.addLayout(form)
        layout.addWidget(label(_ui_tr('Ordne erkannte Platzhalter Feldern zu. Pflichtwerte müssen vor dem Erzeugen ausgefüllt sein.'), 'muted'))
        self.table = QTableWidget(len(placeholders), 3)
        _ui_locale.headers(self.table, [_ui_tr('Platzhalter'), _ui_tr('Feldzuordnung'), _ui_tr('Pflichtwert')])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mapping_widgets, self.required_widgets = {}, {}
        previous = json.loads(record["configuration_json"]) if record else {}
        for index, placeholder in enumerate(placeholders):
            self.table.setCellWidget(index, 0, label(placeholder))
            mapping = QComboBox()
            for name, field_path in FIELD_PATHS:
                _ui_locale.add_item(mapping, _ui_tr(name), field_path)
            existing = previous.get("mapping", {}).get(placeholder, "")
            if existing and mapping.findData(existing) == -1:
                mapping.addItem(existing, existing)
            mapping.setCurrentIndex(max(0, mapping.findData(existing)))
            required = _ui_locale.widget(QCheckBox, _ui_tr('Pflicht'))
            required.setChecked(placeholder in previous.get("required_placeholders", []))
            self.mapping_widgets[placeholder] = mapping
            self.required_widgets[placeholder] = required
            self.table.setCellWidget(index, 1, mapping)
            self.table.setCellWidget(index, 2, required)
        layout.addWidget(self.table, 1)
        if not placeholders:
            layout.addWidget(label(_ui_tr('Keine Platzhalter erkannt. Die Vorlage wird als unveränderte Dokumentkopie verwendbar.'), 'muted'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Importieren'))
        _ui_locale.set_text(buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, _ui_tr('Vorlagenname'), _ui_tr('Bitte einen Vorlagennamen eingeben.'))
            return
        self.accept()

    def values(self):
        return {"name": self.name.text().strip(),
                "mapping": {name: widget.currentData() for name, widget in self.mapping_widgets.items() if widget.currentData()},
                "required_placeholders": [name for name, widget in self.required_widgets.items() if widget.isChecked()]}


class GenerateDialog(QDialog):
    operation_requested = Signal(str, object)
    operation_cancel_requested = Signal()

    def __init__(self, record, snapshot, parent=None):
        super().__init__(parent)
        self.record = record
        _ui_locale.set_window_title(self, _ui_tr('Dokument aus Vorlage erzeugen'))
        self.resize(650, 640)
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_format('{0} · Version {1}', f"{record['template_name']}", f"{record['version_number']}"), 'pageTitle'))
        form = QFormLayout()
        self.application = QComboBox()
        _ui_locale.add_item(self.application, _ui_tr('Ohne Bewerbungszuordnung'), None)
        for application in snapshot["choices"]["applications"]:
            self.application.addItem(application["title"], application["id"])
        _ui_locale.add_row(form, _ui_tr('Bewerbung'), self.application)
        layout.addLayout(form)
        self.fill_button = button(_ui_tr('Werte aus Bewerbung übernehmen'), self.fill_from_application)
        layout.addWidget(self.fill_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        fields_form = QFormLayout(content)
        configuration = json.loads(record["configuration_json"])
        self.required = set(configuration.get("required_placeholders", []))
        self.fields = {}
        for name in json.loads(record["placeholders_json"]):
            field = QPlainTextEdit()
            field.setFixedHeight(64)
            field.setObjectName(name)
            self.fields[name] = field
            fields_form.addRow(name + (" *" if name in self.required else ""), field)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(label(_ui_tr('* Pflichtwert. Leere optionale Felder bleiben als Platzhalter sichtbar.'), 'muted'))
        file_form = QFormLayout()
        self.filename = QLineEdit("Bewerbung.docx")
        _ui_locale.add_row(file_form, _ui_tr('Dateiname'), self.filename)
        layout.addLayout(file_form)
        self.with_pdf = _ui_locale.widget(QCheckBox, _ui_tr('PDF in Vorschau erzeugen'))
        self.with_pdf.setEnabled(bool(snapshot["libreoffice"]))
        layout.addWidget(self.with_pdf)
        if not snapshot["libreoffice"]:
            layout.addWidget(label(_ui_tr('Für PDF-Ausgaben wird eine LibreOffice-Installation benötigt. Die Textvorschau ist verfügbar.'), 'muted'))
        self.busy_label = label("", "muted")
        layout.addWidget(self.busy_label)
        buttons = ActionFlowLayout()
        self.preview_button = button(_ui_tr('Vorschau'), lambda: self.request_operation('preview_document'))
        self.generate_button = button(_ui_tr('DOCX speichern'), lambda: self.request_operation('generate_document'), primary=True)
        self.cancel_button = button(_ui_tr('Schließen'), self.reject)
        buttons.addWidget(self.preview_button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.generate_button)
        self.operation_cancel_button = button(_ui_tr('Vorgang abbrechen'), self.operation_cancel_requested.emit)
        self.operation_cancel_button.hide()
        buttons.addWidget(self.operation_cancel_button)
        layout.addLayout(buttons)
        compact_forms(self)

    def set_busy(self, busy):
        self.fill_button.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.generate_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.operation_cancel_button.setVisible(busy)
        for widget in (self.application, self.filename, self.with_pdf, *self.fields.values()):
            widget.setEnabled(not busy)
        _ui_locale.set_text(self.busy_label, _ui_tr('Bitte warten …') if busy else '')

    def fill_from_application(self):
        self.operation_requested.emit("document_values", {"template_version_id": self.record["id"], "application_id": self.application.currentData()})

    def populate(self, values):
        for name, value in values.items():
            if name in self.fields and value is not None:
                self.fields[name].setPlainText(str(value))

    def request_operation(self, action):
        missing = [name for name in self.required if not self.fields[name].toPlainText().strip()]
        if missing:
            QMessageBox.warning(self, _ui_tr('Pflichtwerte'), _ui_format('Bitte ergänzen: {0}', ', '.join(sorted(missing))))
            return
        values = {name: widget.toPlainText() for name, widget in self.fields.items() if widget.toPlainText()}
        options = {"template_version_id": self.record["id"], "values": values}
        if action == "preview_document":
            options["with_pdf"] = self.with_pdf.isChecked()
        else:
            filename = self.filename.text().strip()
            if not filename.lower().endswith(".docx") or Path(filename).name != filename:
                QMessageBox.warning(self, _ui_tr('Dateiname'), _ui_tr('Bitte einen einfachen Dateinamen mit der Endung .docx eingeben.'))
                return
            options.update(output_filename=filename, application_id=self.application.currentData())
        self.operation_requested.emit(action, options)

    def reject(self):
        if self.cancel_button.isEnabled():
            super().reject()

    def closeEvent(self, event):
        if not self.cancel_button.isEnabled():
            event.ignore()
        else:
            super().closeEvent(event)


class PdfWidget(QWidget):
    def __init__(self, content, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.document = QPdfDocument(self)
        view = QPdfView(self)
        view.setDocument(self.document)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(view)
        # The viewer must not keep Windows file handles on temporary previews.
        self.buffer = QBuffer(self)
        pdf_bytes = content if isinstance(content, bytes) else Path(content).read_bytes()
        self.buffer.setData(QByteArray(pdf_bytes))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.document.load(self.buffer)
        if self.document.status() == QPdfDocument.Status.Error:
            layout.addWidget(label(_ui_tr('Die PDF-Datei konnte nicht geladen werden.'), 'muted'))

    def dispose(self):
        self.document.close()
        self.buffer.close()


class PreviewDialog(QDialog):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Dokument prüfen'))
        self.resize(1100, 760)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.pdf_widget = None
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        if "before" in preview:
            splitter = QSplitter()
            for caption, key in (("Vorlage", "before"), ("Erzeugtes Dokument", "after")):
                panel = QWidget()
                panel_layout = QVBoxLayout(panel)
                panel_layout.addWidget(label(_ui_tr(caption)))
                editor = QPlainTextEdit()
                editor.setObjectName(key)
                editor.setReadOnly(True)
                _ui_locale.set_plain_text(editor, preview[key])
                panel_layout.addWidget(editor)
                splitter.addWidget(panel)
            _ui_locale.add_tab(tabs, splitter, _ui_tr('Textvergleich'))
            layout.addWidget(label(_ui_tr('Der Textvergleich zeigt Inhalte ohne Seitenlayout. Prüfe das Layout im PDF oder in Word/LibreOffice.'), 'muted'))
        if preview.get("pdf_path"):
            self.pdf_widget = PdfWidget(preview.get("pdf_bytes", preview["pdf_path"]))
            _ui_locale.add_tab(tabs, self.pdf_widget, _ui_tr('PDF'))
        layout.addWidget(tabs, 1)
        if preview.get("unresolved"):
            layout.addWidget(label(_ui_format('Noch offen: {0}', ', '.join(preview['unresolved'])), 'muted'))
        layout.addWidget(button(_ui_tr('Schließen'), self.accept))
        self.finished.connect(self.dispose)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def dispose(self, result=None):
        if self.pdf_widget is not None:
            self.pdf_widget.dispose()
