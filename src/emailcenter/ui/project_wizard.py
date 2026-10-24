"""Project setup with optional initial records and a review before creation."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
import json
import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
    QWizard, QWizardPage,
)

from ..project_setup import initial_records
from .pages import button, label
from .responsive import compact_forms


class ProjectWizard(QWizard):
    operation_requested = Signal(str, object)

    def __init__(self, parent=None, *, choices=None):
        super().__init__(parent)
        self.busy = False
        _ui_locale.set_window_title(self, _ui_tr('Neues Projekt'))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        _ui_locale.set_wizard_button_text(self, QWizard.WizardButton.BackButton, _ui_tr('Zurück'))
        _ui_locale.set_wizard_button_text(self, QWizard.WizardButton.NextButton, _ui_tr('Weiter'))
        _ui_locale.set_wizard_button_text(self, QWizard.WizardButton.FinishButton, _ui_tr('Projekt erstellen'))
        _ui_locale.set_wizard_button_text(self, QWizard.WizardButton.CancelButton, _ui_tr('Abbrechen'))
        self.resize(700, 620)
        self.setMinimumSize(540, 460)
        self.fields = {}
        self.choices = choices or {}

        basic = self.make_page("1 · Projekt und Speicherort", "Name und neuer Ordner für dieses Projekt.")
        form = QFormLayout()
        self.line(form, "name", "Projektname *", 200)
        self.line(form, "folder", "Neuer Ordnername *", 120)
        location = QHBoxLayout()
        self.parent_path = QLineEdit()
        self.parent_path.setReadOnly(True)
        _ui_locale.set_placeholder(self.parent_path, _ui_tr('Übergeordneten Ordner wählen …'))
        location.addWidget(self.parent_path, 1)
        location.addWidget(button(_ui_tr('Durchsuchen …'), self.choose_parent))
        _ui_locale.add_row(form, _ui_tr('Speicherort *'), location)
        basic.addLayout(form)
        basic.addWidget(label(_ui_tr('Ein eigenes Projekt enthält seine Daten, Dokumente, Vorlagen und Kontoverbindungen.'), 'muted'))
        basic.addStretch()

        setup = self.make_page("2 · Arbeitsweise und Vorgaben", "Optionale Angaben helfen bei späteren Eingaben.")
        form = QFormLayout()
        self.fields["workspace_mode"] = QComboBox()
        _ui_locale.add_item(self.fields['workspace_mode'], _ui_tr('Bewerbungen'), 'applications')
        _ui_locale.add_item(self.fields['workspace_mode'], _ui_tr('E-Mail-Aufträge'), 'mail')
        _ui_locale.add_row(form, _ui_tr('Arbeitsmodus'), self.fields['workspace_mode'])
        self.fields["goal"] = QPlainTextEdit()
        self.fields["goal"].setMaximumHeight(85)
        _ui_locale.set_placeholder(self.fields['goal'], _ui_tr('Projektziel / Hinweise (optional, maximal 4000 Zeichen)'))
        _ui_locale.add_row(form, _ui_tr('Projektziel'), self.fields['goal'])
        setup.addLayout(form)
        self.profile_group = _ui_locale.widget(QGroupBox, _ui_tr('Bewerberprofil'))
        profile_layout = QVBoxLayout(self.profile_group)
        self.add_profile = _ui_locale.widget(QCheckBox, _ui_tr('Profil jetzt anlegen'))
        profile_layout.addWidget(self.add_profile)
        self.profile_content = QWidget()
        profile_form = QFormLayout(self.profile_content)
        self.line(profile_form, "display_name", "Name *", 200)
        self.line(profile_form, "email", "E-Mail (optional)", 254)
        self.line(profile_form, "phone", "Telefon (optional)", 80)
        self.profile_choice = QComboBox()
        _ui_locale.add_item(self.profile_choice, _ui_tr('Neu eingeben'), None)
        for item in self.choices.get("profiles", []):
            self.profile_choice.addItem(item["display_name"], item)
        _ui_locale.insert_row(profile_form, 0, _ui_tr('Vorhandenes Profil übernehmen'), self.profile_choice)
        self.profile_choice.currentIndexChanged.connect(self.copy_profile)
        profile_layout.addWidget(self.profile_content)
        self.profile_content.setEnabled(False)
        self.add_profile.toggled.connect(self.profile_content.setEnabled)
        setup.addWidget(self.profile_group)
        signature_group = _ui_locale.widget(QGroupBox, _ui_tr('Standardsignatur für neue E-Mail-Entwürfe'))
        signature_layout = QVBoxLayout(signature_group)
        self.add_signature = _ui_locale.widget(QCheckBox, _ui_tr('Signatur jetzt anlegen'))
        signature_layout.addWidget(self.add_signature)
        self.signature_content = QWidget()
        signature_form = QFormLayout(self.signature_content)
        self.line(signature_form, "signature_name", "Bezeichnung *", 200)
        self.fields["signature_text"] = QPlainTextEdit()
        self.fields["signature_text"].setMaximumHeight(100)
        _ui_locale.set_placeholder(self.fields['signature_text'], _ui_tr('Mit freundlichen Grüßen\nName / Kontaktdaten'))
        _ui_locale.add_row(signature_form, _ui_tr('Signaturtext *'), self.fields['signature_text'])
        signature_layout.addWidget(self.signature_content)
        self.signature_content.setEnabled(False)
        self.add_signature.toggled.connect(self.signature_content.setEnabled)
        setup.addWidget(signature_group)
        defaults_form = QFormLayout()
        defaults_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.document_choice = QComboBox()
        _ui_locale.add_item(self.document_choice, _ui_tr('Später wählen'), None)
        for item in self.choices.get("templates", []):
            _ui_locale.add_item(self.document_choice, _ui_format('{0} · v{1}', f"{item['name']}", f"{item['version_number']}"), item)
        document_row = QHBoxLayout()
        document_row.addWidget(self.document_choice, 1)
        document_row.addWidget(button(_ui_tr('DOCX wählen …'), self.choose_document))
        _ui_locale.add_row(defaults_form, _ui_tr('Bevorzugte Dokumentvorlage'), document_row)
        self.account_email = QComboBox()
        self.account_email.setEditable(True)
        self.account_email.addItem("")
        for item in self.choices.get("accounts", []):
            self.account_email.addItem(item["account_email"])
        _ui_locale.add_row(defaults_form, _ui_tr('Standardkonto (E-Mail)'), self.account_email)
        self.source_choice = QComboBox()
        _ui_locale.add_item(self.source_choice, _ui_tr('Später wählen'), None)
        for item in self.choices.get("lists", []):
            _ui_locale.add_item(self.source_choice, _ui_format('{0} · {1} Zeilen', f"{item['name']}", f"{len(item['rows'])}"), item)
        _ui_locale.add_row(defaults_form, _ui_tr('Empfängerliste übernehmen'), self.source_choice)
        self.body_format = QComboBox()
        _ui_locale.add_item(self.body_format, _ui_tr('Text'), 'plain')
        _ui_locale.add_item(self.body_format, _ui_tr('HTML'), 'html')
        _ui_locale.add_row(defaults_form, _ui_tr('Neue Nachrichten'), self.body_format)
        setup.addLayout(defaults_form)
        setup.addWidget(label(_ui_tr('Gmail nach der Projektanlage im Arbeitsbereich verbinden. Weitere Angaben können später in der App ergänzt werden.'), 'muted'))
        setup.addStretch()
        self.fields["workspace_mode"].currentIndexChanged.connect(self.update_mode)

        review = self.make_page("3 · Zusammenfassung", "Prüfe die Angaben. Mit Zurück kannst du sie ändern.")
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        review.addWidget(self.summary, 1)
        review.addWidget(label(_ui_tr('Beim Abbrechen wird kein Projekt angelegt. Das Erstellen versendet keine E-Mail.'), 'muted'))
        self.currentIdChanged.connect(self.refresh_summary)
        compact_forms(self)

    def make_page(self, title, subtitle):
        page = QWizardPage()
        _ui_locale.set_title(page, _ui_tr(title))
        _ui_locale.set_subtitle(page, _ui_tr(subtitle))
        layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.addPage(page)
        return body

    def line(self, form, key, caption, maximum):
        field = QLineEdit()
        field.setMaxLength(maximum)
        self.fields[key] = field
        _ui_locale.add_row(form, _ui_tr(caption), field)

    def choose_parent(self):
        path = QFileDialog.getExistingDirectory(self, _ui_tr('Übergeordneten Ordner wählen'), self.parent_path.text())
        if path:
            self.parent_path.setText(path)

    def copy_profile(self):
        value = self.profile_choice.currentData()
        if value:
            for key in ("display_name", "email", "phone"):
                self.fields[key].setText(value.get(key) or "")

    def choose_document(self):
        path = QFileDialog.getOpenFileName(self, _ui_tr('Bevorzugte DOCX-Vorlage'), '', _ui_tr('Word (*.docx)'))[0]
        if path:
            self.document_choice.addItem(Path(path).stem, {"source_path": path, "name": Path(path).stem})
            self.document_choice.setCurrentIndex(self.document_choice.count() - 1)

    def update_mode(self):
        self.profile_group.setVisible(self.fields["workspace_mode"].currentData() == "applications")

    def values(self):
        profile = None
        if self.add_profile.isChecked() and self.fields["workspace_mode"].currentData() == "applications":
            profile = {key: self.fields[key].text().strip() for key in ("display_name", "email", "phone")}
            existing = self.profile_choice.currentData()
            if existing:
                profile.update({key: existing[key] for key in ("address_json", "custom_fields_json")})
        signature = None
        if self.add_signature.isChecked():
            signature = {"name": self.fields["signature_name"].text().strip(),
                         "content_text": self.fields["signature_text"].toPlainText().strip()}
        document = self.document_choice.currentData()
        initial_document = None
        if document:
            configuration = json.loads(document.get("configuration_json", "{}"))
            initial_document = {"source_path": document["source_path"], "name": document["name"],
                                "mapping": configuration.get("mapping", {}),
                                "required_placeholders": configuration.get("required_placeholders", [])}
            if document.get("content_hash"):
                initial_document["expected_hash"] = document["content_hash"]
        return {
            "path": str(Path(self.parent_path.text()) / self.fields["folder"].text().strip()),
            "name": self.fields["name"].text().strip(),
            "workspace_mode": self.fields["workspace_mode"].currentData(),
            "goal": self.fields["goal"].toPlainText().strip(),
            "initial_profile": profile, "initial_signature": signature,
            "defaults": {"account_email": self.account_email.currentText().strip(), "body_format": self.body_format.currentData()},
            "initial_document": initial_document, "initial_source": self.source_choice.currentData(),
        }

    def check(self, page):
        if page == 0:
            name = self.fields["name"].text().strip()
            folder = self.fields["folder"].text().strip()
            reserved = re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", folder, re.I)
            if not name:
                raise ValueError(_ui_tr('Bitte einen Projektnamen eingeben.'))
            if (not folder or folder in (".", "..") or folder.endswith(".") or reserved
                    or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in folder)):
                raise ValueError(_ui_tr('Bitte einen gültigen einfachen neuen Ordnernamen eingeben.'))
            if not self.parent_path.text() or not Path(self.parent_path.text()).is_dir():
                raise ValueError(_ui_tr('Bitte einen vorhandenen übergeordneten Ordner wählen.'))
            if Path(self.values()["path"]).exists():
                raise ValueError(_ui_tr('Dieser Projektordner existiert bereits. Bitte einen neuen Namen wählen.'))
        elif page == 1:
            values = self.values()
            if len(values["goal"]) > 4000:
                raise ValueError(_ui_tr('Das Projektziel darf höchstens 4000 Zeichen enthalten.'))
            initial_records(values["initial_profile"], values["initial_signature"])
            from ..project_defaults import validate_defaults
            validate_defaults(values["defaults"])

    def validateCurrentPage(self):
        try:
            self.check(self.currentId())
        except ValueError as error:
            QMessageBox.warning(self, _ui_tr('Angaben prüfen'), str(error))
            return False
        return True

    def refresh_summary(self, page):
        if page != 2:
            return
        values = self.values()
        profile, signature = values["initial_profile"], values["initial_signature"]
        from ..language import join_text, translate
        from .localization import SOURCE_ROLE
        def choice(control):
            source = control.itemData(control.currentIndex(), SOURCE_ROLE)
            return translate(source) if source is not None else control.currentText()
        lines = [values["name"], _ui_format('Ordner: {0}', values['path']),
                 _ui_format('Arbeitsmodus: {0}', choice(self.fields['workspace_mode'])),
                 _ui_format('Projektziel: {0}', values['goal'] or _ui_tr('Keine Angabe')), '']
        if values["workspace_mode"] == "applications":
            lines.extend([_ui_format('Bewerberprofil: {0}', profile['display_name'] if profile else _ui_tr('Später anlegen')),
                          _ui_format('E-Mail: {0}', profile['email'] if profile else '—'),
                          _ui_format('Telefon: {0}', profile['phone'] if profile else '—'), ''])
        lines.extend([_ui_format('Standardsignatur: {0}', signature['name'] if signature else _ui_tr('Keine')),
                      signature["content_text"] if signature else "",
                      '', _ui_tr('Gmail: Im Arbeitsbereich verbinden')])
        lines.extend([_ui_format('Dokumentvorlage: {0}', choice(self.document_choice)),
                      _ui_format('Empfängerquelle: {0}', choice(self.source_choice)),
                      _ui_format('Standardkonto: {0}', self.account_email.currentText() or _ui_tr('Später wählen')),
                      _ui_format('Nachrichtenformat: {0}', choice(self.body_format))])
        _ui_locale.set_plain_text(self.summary, join_text('\n', lines))

    def accept(self):
        if self.busy or self.currentId() != 2:
            return
        try:
            self.check(0)
            self.check(1)
        except ValueError as error:
            QMessageBox.warning(self, _ui_tr('Angaben prüfen'), str(error))
            return
        self.operation_requested.emit("create_project", self.values())

    def creation_completed(self):
        super().accept()

    def set_busy(self, busy):
        self.busy = busy
        self.setEnabled(not busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)
