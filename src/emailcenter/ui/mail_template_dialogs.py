"""Mail template library, immutable versions and an explicit preview."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from ..mail_templates import FIELDS
from .pages import button, label
from .responsive import ActionFlowLayout
from .builder_preview import MailRenderer


class BusyDialog(QDialog):
    operation_requested = Signal(str, object)
    operation_cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.setModal(True)
        self.setMinimumSize(540, 460)
        self._busy_widgets = []
        self.operation_cancel_button = button(_ui_tr('Laufenden Vorgang abbrechen'), self.operation_cancel_requested.emit)
        self.operation_cancel_button.setParent(self)
        self.operation_cancel_button.hide()

    def set_busy(self, busy):
        self.busy = busy
        if busy and not self._busy_widgets:
            if self.layout() and self.layout().indexOf(self.operation_cancel_button) < 0:
                self.layout().addWidget(self.operation_cancel_button)
            # A parent dialog may already be busy. Preserve each child's own flag,
            # otherwise inherited disabled state would become permanent on restore.
            self._busy_widgets = [(widget, not widget.testAttribute(Qt.WidgetAttribute.WA_ForceDisabled)) for widget in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly) if widget is not self.operation_cancel_button]
            for widget, _ in self._busy_widgets:
                widget.setEnabled(False)
        elif not busy:
            for widget, enabled in self._busy_widgets:
                widget.setEnabled(enabled)
            self._busy_widgets = []
        self.operation_cancel_button.setVisible(busy)
        self.operation_cancel_button.setEnabled(busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)


class MailTemplateLibrary(BusyDialog):
    action_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('E-Mail-Vorlagen'))
        self.resize(660, 560)
        self.offset, self.limit, self.data = 0, 25, None
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('E-Mail-Vorlagen'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Betreff und Text wiederverwenden; Änderungen werden als neue Version gespeichert.'), 'muted'))
        search = QHBoxLayout()
        self.search = QLineEdit()
        _ui_locale.set_placeholder(self.search, _ui_tr('Vorlagenname suchen … (Enter)'))
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.search_records)
        self.search.textChanged.connect(lambda text: self.search_records() if not text else None)
        search.addWidget(self.search, 1)
        search.addWidget(button(_ui_tr('Suchen'), self.search_records))
        layout.addLayout(search)
        self.records = QListWidget()
        self.records.currentRowChanged.connect(self.update_selection)
        self.records.itemDoubleClicked.connect(lambda _: self.edit())
        layout.addWidget(self.records, 1)
        actions = ActionFlowLayout()
        self.new_button = button(_ui_tr('Neue Vorlage'), lambda: self.action_requested.emit('new', None), primary=True)
        self.edit_button = button(_ui_tr('Versionen / Bearbeiten'), self.edit)
        actions.addWidget(self.new_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(button(_ui_tr('Aktualisieren'), self.request_load))
        layout.addLayout(actions)
        footer = ActionFlowLayout()
        self.summary = label(_ui_tr('Noch keine Vorlagen geladen.'), 'muted')
        self.previous = button(_ui_tr('Zurück'), lambda: self.move_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.move_page(1))
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.previous)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        layout.addWidget(button(_ui_tr('Schließen'), self.reject))
        self.update_selection()

    def selected(self):
        row = self.records.currentRow()
        return self.data["rows"][row] if self.data and 0 <= row < len(self.data["rows"]) else None

    def update_selection(self):
        self.edit_button.setEnabled(bool(self.selected()))

    def edit(self):
        if self.selected():
            self.action_requested.emit("edit", self.selected())

    def request_load(self):
        self.operation_requested.emit("mail_template_list", {"search": self.search.text(), "offset": self.offset, "limit": self.limit})

    def search_records(self):
        self.offset = 0
        self.request_load()

    def move_page(self, direction):
        if self.data:
            self.offset = max(0, self.offset + direction * self.limit)
            self.request_load()

    def display(self, data):
        previous = self.selected()
        self.data, self.offset = data, data["offset"]
        self.records.clear()
        for index, row in enumerate(data["rows"]):
            _ui_locale.add_item(self.records, _ui_format('{0} · Version {1}', f"{row['name']}", f"{row['version_number']}"))
            if previous and row["id"] == previous["id"]:
                self.records.setCurrentRow(index)
        _ui_locale.set_text(self.summary, _ui_format('{0}–{1} von {2}', f"{(self.offset + 1 if data['rows'] else 0)}", f"{self.offset + len(data['rows'])}", f"{data['total']}"))
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(self.offset + len(data["rows"]) < data["total"])
        self.update_selection()


class MailTemplateEditor(BusyDialog):
    def __init__(self, details=None, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('E-Mail-Vorlage bearbeiten') if details else _ui_tr('Neue E-Mail-Vorlage'))
        self.resize(700, 640)
        self.details, self._loading, self._selected_index = None, False, 0
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout.addWidget(label(_ui_tr('Jedes Speichern legt eine neue Version an. Vorhandene Entwürfe und Aufträge behalten ihren Inhalt.'), 'muted'))
        self.versions = QComboBox()
        layout.addWidget(self.versions)
        self.reload_button = button(_ui_tr('Versionen neu laden'), self.reload)
        layout.addWidget(self.reload_button)
        form = QFormLayout()
        self.name, self.subject, self.format = QLineEdit(), QLineEdit(), QComboBox()
        self.name.setMaxLength(200)
        self.subject.setMaxLength(998)
        _ui_locale.add_item(self.format, _ui_tr('Text'), 'plain')
        _ui_locale.add_item(self.format, _ui_tr('HTML-Quelltext'), 'html')
        _ui_locale.add_row(form, _ui_tr('Vorlagenname *'), self.name)
        _ui_locale.add_row(form, _ui_tr('Betreff *'), self.subject)
        _ui_locale.add_row(form, _ui_tr('Format'), self.format)
        layout.addLayout(form)
        self.body = QPlainTextEdit()
        self.body.setMinimumHeight(180)
        _ui_locale.set_placeholder(self.body, _ui_tr('Nachricht * · beispielsweise Guten Tag {{contact.display_name}}, …'))
        layout.addWidget(self.body, 1)
        self.rendered = MailRenderer()
        self.rendered.setMinimumHeight(180)
        layout.addWidget(label(_ui_tr('Gerenderte Vorschau · Platzhalter werden hier noch nicht ersetzt'), 'muted'))
        layout.addWidget(self.rendered)
        for control, signal in ((self.subject, "textChanged"), (self.body, "textChanged"), (self.format, "currentIndexChanged")):
            getattr(control, signal).connect(self.render_preview)
        insertion = QHBoxLayout()
        self.placeholder = QComboBox()
        self.placeholder.addItems(FIELDS)
        self.target = QComboBox()
        _ui_locale.add_item(self.target, _ui_tr('In Nachricht'), 'body')
        _ui_locale.add_item(self.target, _ui_tr('In Betreff'), 'subject')
        insertion.addWidget(self.placeholder, 1)
        insertion.addWidget(self.target)
        insertion.addWidget(button(_ui_tr('Einfügen'), self.insert_placeholder))
        layout.addLayout(insertion)
        layout.addWidget(label(_ui_tr('Eigene Werte als {{NAME}} eintragen. Alle verwendeten Platzhalter müssen in der Vorschau ausgefüllt sein; HTML-Werte werden maskiert.'), 'muted'))
        self.duplicate_button = button(_ui_tr('Gewählte Version duplizieren'), self.duplicate)
        layout.addWidget(self.duplicate_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Neue Version speichern') if details else _ui_tr('Vorlage speichern'))
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.versions.currentIndexChanged.connect(self.change_version)
        self.populate(details)
        self.render_preview()

    def render_preview(self):
        self.rendered.display({"email": "", "subject": self.subject.text(), "preview_body": self.body.toPlainText(),
                               "body_format": self.format.currentData(), "attachments": [], "live": True})
        _ui_locale.set_text(self.rendered.notice, _ui_tr('Ungeprüfte Vorlagenansicht · Platzhalter in der Vorschau mit Projektwerten ausfüllen.'))

    def values(self):
        return {"name": self.name.text().strip(), "subject": self.subject.text(),
                "body": self.body.toPlainText(), "body_format": self.format.currentData()}

    def populate(self, details):
        self.details, self._loading = details, True
        self.versions.clear()
        if details:
            for version in details["versions"]:
                _ui_locale.add_item(self.versions, _ui_format('Version {0}', f"{version['version_number']}"), version)
        for widget in (self.versions, self.reload_button, self.duplicate_button):
            widget.setVisible(bool(details))
        self._loading = False
        self.load_version()

    def load_version(self):
        version = self.versions.currentData()
        if version:
            _ui_locale.set_text(self.name, version['name'])
            self.subject.setText(version["subject"])
            _ui_locale.set_plain_text(self.body, version['body'])
            self.format.setCurrentIndex(self.format.findData(version["body_format"]))
        self._selected_index = self.versions.currentIndex()
        self._loaded_values = self.values()

    def change_version(self):
        if self._loading:
            return
        if self.values() != self._loaded_values and QMessageBox.question(self, _ui_tr('Version wechseln'), _ui_tr('Ungespeicherte Eingaben durch die gewählte Version ersetzen?')) != QMessageBox.StandardButton.Yes:
            self.versions.blockSignals(True)
            self.versions.setCurrentIndex(self._selected_index)
            self.versions.blockSignals(False)
            return
        self.load_version()

    def insert_placeholder(self):
        text = "{{" + self.placeholder.currentText() + "}}"
        self.subject.insert(text) if self.target.currentData() == "subject" else self.body.insertPlainText(text)

    def reload(self):
        if self.details and not self.busy and QMessageBox.question(self, _ui_tr('Versionen neu laden'), _ui_tr('Aktuelle Eingaben durch die neueste gespeicherte Version ersetzen?')) == QMessageBox.StandardButton.Yes:
            self.operation_requested.emit("mail_template_details", {"template_id": self.details["versions"][0]["template_id"]})

    def save(self):
        if not self.busy:
            values = self.values()
            if self.details:
                values.update(template_id=self.details["versions"][0]["template_id"], base_version_id=self.details["latest_version_id"])
            self.operation_requested.emit("mail_template_save", values)

    def duplicate(self):
        version = self.versions.currentData()
        if version and not self.busy:
            if self.values() != self._loaded_values and QMessageBox.question(self, _ui_tr('Version duplizieren'), _ui_tr('Die gewählte gespeicherte Version duplizieren und ungespeicherte Eingaben verwerfen?')) != QMessageBox.StandardButton.Yes:
                return
            self.operation_requested.emit("mail_template_duplicate", {"version_id": version["id"]})


class MailTemplatePreview(BusyDialog):
    apply_requested = Signal(object)

    def __init__(self, result, payload, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('E-Mail-Vorlage prüfen'))
        self.resize(700, 680)
        self.payload, self.result, self.fresh = payload, None, False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        self.title = label("", "pageTitle")
        self.missing = label("", "muted")
        layout.addWidget(self.title)
        layout.addWidget(self.missing)
        form = QFormLayout()
        self.fields = {}
        for name in result["placeholders"]:
            field = QPlainTextEdit()
            field.setMaximumHeight(65)
            field.setPlainText(result["values"].get(name, ""))
            self.fields[name] = field
            form.addRow(name, field)
            field.textChanged.connect(self.invalidate)
        layout.addLayout(form)
        self.refresh_button = button(_ui_tr('Vorschau aktualisieren'), self.render)
        layout.addWidget(self.refresh_button)
        self.subject = QLineEdit()
        self.subject.setReadOnly(True)
        layout.addWidget(self.subject)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setMinimumHeight(180)
        self.rendered = MailRenderer()
        self.preview_tabs = QTabWidget()
        _ui_locale.add_tab(self.preview_tabs, self.rendered, _ui_tr('Nachricht'))
        _ui_locale.add_tab(self.preview_tabs, self.body, _ui_tr('Quelltext'))
        layout.addWidget(self.preview_tabs, 1)
        self.format_label = label("", "muted")
        layout.addWidget(self.format_label)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Betreff, Nachricht und Format im Entwurf ersetzen'))
        outer.addWidget(self.confirm)
        self.confirm.toggled.connect(self.update_apply)
        actions = ActionFlowLayout()
        self.apply_button = button(_ui_tr('In Entwurf übernehmen'), self.apply, primary=True)
        actions.addWidget(self.apply_button)
        actions.addWidget(button(_ui_tr('Abbrechen'), self.reject))
        outer.addLayout(actions)
        self.display(result)

    def display(self, result):
        self.result, self.fresh = result, True
        _ui_locale.set_text(self.title, _ui_format('{0} · Version {1}', f"{result['name']}", f"{result['version_number']}"))
        _ui_locale.set_text(self.missing, _ui_format('Fehlende Pflichtwerte: {0}', ', '.join(result['missing'])) if result['missing'] else _ui_tr('Alle Platzhalter sind ausgefüllt. Empfänger und Anhänge bleiben erhalten.'))
        self.subject.setText(result["subject"])
        _ui_locale.set_plain_text(self.body, result['body'])
        self.rendered.display({"email": "", "subject": result["subject"], "preview_body": result["body"],
                               "body_format": result["body_format"], "attachments": []})
        _ui_locale.set_text(self.format_label, _ui_tr('HTML-Quelltext') if result['body_format'] == 'html' else _ui_tr('Textnachricht'))
        self.update_apply()

    def invalidate(self):
        self.fresh = False
        _ui_locale.set_text(self.missing, _ui_tr('Werte geändert. Vorschau aktualisieren, bevor du die Inhalte übernimmst.'))
        _ui_locale.set_text(self.rendered.notice, _ui_tr('Vorschau veraltet · Werte geändert, erneut laden.'))
        self.rendered.notice.show()
        self.update_apply()

    def update_apply(self):
        self.apply_button.setEnabled(bool(self.fresh and self.result and not self.result["missing"] and self.confirm.isChecked() and not self.busy))

    def render(self):
        if not self.busy:
            self.fresh = False
            self.update_apply()
            self.operation_requested.emit("mail_template_render", {**self.payload,
                "values": {name: field.toPlainText() for name, field in self.fields.items()}})

    def apply(self):
        if self.apply_button.isEnabled():
            self.apply_requested.emit(self.result)

    def set_busy(self, busy):
        super().set_busy(busy)
        self.update_apply()
