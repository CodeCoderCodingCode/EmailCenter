"""Contact selection, per-recipient values, local previews and draft groups."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QInputDialog,
    QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .mail_template_dialogs import BusyDialog
from .pages import button, label
from ..bulk_sources import SOURCE_FIELDS
from .responsive import ActionFlowLayout, ResponsiveSplitter, compact_forms


class BulkMailDialog(BusyDialog):
    cancel_requested = Signal()
    draft_requested = Signal(str)
    source_requested = Signal(str)
    delivery_requested = Signal(str)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Bulk-E-Mails · persönliche Entwürfe'))
        self.resize(1000, 760)
        self.data, self.selected, self.settings = data, set(), {}
        self.offset, self.loading, self.fresh = 0, False, False
        self.preview, self.batch, self.files = None, None, []
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Bulk-E-Mails'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Persönliche Entwürfe erstellen und anschließend gemeinsam prüfen, freigeben und versenden.'), 'muted'))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        new = QWidget()
        new_layout = QVBoxLayout(new)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        self.name = QLineEdit("Neue Entwurfsgruppe")
        _ui_locale.add_row(form, _ui_tr('Gruppenname'), self.name)
        self.template = QComboBox()
        _ui_locale.add_item(self.template, _ui_tr('E-Mail-Vorlage auswählen'), None)
        for version in data["templates"]:
            _ui_locale.add_item(self.template, _ui_format('{0} · v{1}', f"{version['name']}", f"{version['version_number']}"), version['id'])
        _ui_locale.add_row(form, _ui_tr('Vorlagenversion'), self.template)
        sources = QHBoxLayout()
        sources.addWidget(button(_ui_tr('Excel-/CSV-Importzeilen'), lambda: self.source_requested.emit('import')))
        sources.addWidget(button(_ui_tr('Manuelle Liste / DOCX-Text'), lambda: self.source_requested.emit('manual')))
        _ui_locale.add_row(form, _ui_tr('Daten ergänzen'), sources)
        self.document_choice = QComboBox()
        _ui_locale.add_item(self.document_choice, _ui_tr('Kein Anschreiben automatisch erzeugen'), None)
        for version in data.get("document_templates", []):
            _ui_locale.add_item(self.document_choice, _ui_format('{0} · v{1}', f"{version['name']}", f"{version['version_number']}"), version['id'])
        _ui_locale.add_row(form, _ui_tr('DOCX-Anschreibenvorlage'), self.document_choice)
        self.document_format = QComboBox()
        _ui_locale.add_item(self.document_format, _ui_tr('DOCX'), 'docx')
        _ui_locale.add_item(self.document_format, _ui_tr('PDF (benötigt LibreOffice)'), 'pdf')
        _ui_locale.add_row(form, _ui_tr('Anschreiben-Ausgabe'), self.document_format)
        self.document_bindings = QTableWidget(0, 2)
        _ui_locale.headers(self.document_bindings, ['DOCX-Platzhalter', _ui_tr('Datenfeld')])
        self.document_bindings.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.document_bindings.setMaximumHeight(180)
        self.document_bindings.hide()
        form.addRow(self.document_bindings)
        self.account, self.signature = QComboBox(), QComboBox()
        _ui_locale.add_item(self.account, _ui_tr('Konto später beim Senden wählen'), None)
        for value in data["accounts"]:
            self.account.addItem(value["account_email"], value["id"])
        _ui_locale.add_item(self.signature, _ui_tr('Keine Signatur'), None)
        for value in data["signatures"]:
            self.signature.addItem(value["name"], value["id"])
        _ui_locale.add_row(form, _ui_tr('Absender'), self.account)
        _ui_locale.add_row(form, _ui_tr('Signatur'), self.signature)
        common = QHBoxLayout()
        self.file_status = label(_ui_tr('Keine gemeinsamen Anhänge'), 'muted')
        common.addWidget(self.file_status, 1)
        common.addWidget(button(_ui_tr('Dateien anhängen'), self.add_files))
        common.addWidget(button(_ui_tr('Anhänge entfernen'), self.clear_files))
        _ui_locale.add_row(form, _ui_tr('Alle Empfänger'), common)
        panels = ResponsiveSplitter()
        left, right = QWidget(), QWidget()
        left.setMinimumWidth(280)
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        self.search = QLineEdit()
        _ui_locale.set_placeholder(self.search, _ui_tr('Kontakte nach Name oder E-Mail suchen …'))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.search_contacts)
        left_layout.addWidget(self.search)
        self.group_filter, self.saved_filter = QComboBox(), QComboBox()
        self.valid_only = _ui_locale.widget(QCheckBox, _ui_tr('Nur gültige Adressen anzeigen'))
        left_layout.addWidget(self.group_filter)
        left_layout.addWidget(self.saved_filter)
        left_layout.addWidget(self.valid_only)
        library_actions = QHBoxLayout()
        library_actions.addWidget(button(_ui_tr('Auswahl als Gruppe'), lambda: self.save_collection('group')))
        library_actions.addWidget(button(_ui_tr('Filter speichern'), lambda: self.save_collection('filter')))
        left_layout.addLayout(library_actions)
        left_layout.addWidget(button(_ui_tr('Gewählte Sammlung löschen …'), self.delete_collection))
        self.display_collections(data)
        self.group_filter.currentIndexChanged.connect(self.search_contacts)
        self.valid_only.toggled.connect(self.search_contacts)
        self.saved_filter.activated.connect(self.apply_filter)
        self.contacts = QListWidget()
        self.contacts.setMinimumHeight(380)
        self.contacts.itemChanged.connect(self.contact_changed)
        left_layout.addWidget(self.contacts, 1)
        selection = QHBoxLayout()
        selection.addWidget(button(_ui_tr('Sichtbare auswählen'), self.select_visible))
        selection.addWidget(button(_ui_tr('Alle abwählen'), self.clear_selection))
        left_layout.addLayout(selection)
        pages = QHBoxLayout()
        self.previous = button(_ui_tr('Zurück'), lambda: self.move_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.move_page(1))
        pages.addWidget(self.previous)
        pages.addWidget(self.next)
        left_layout.addLayout(pages)
        self.selection_status = label("", "muted")
        left_layout.addWidget(self.selection_status)
        right_layout.addWidget(label(_ui_tr('Persönliche Werte und Vorschau')))
        self.recipient = QComboBox()
        self.recipient.currentIndexChanged.connect(self.show_recipient)
        right_layout.addWidget(self.recipient)
        self.application = QComboBox()
        _ui_locale.add_item(self.application, _ui_tr('Ohne Bewerbungszuordnung'), None)
        for value in data["applications"]:
            self.application.addItem(value["title"], value["id"])
        self.application.currentIndexChanged.connect(self.application_changed)
        right_layout.addWidget(self.application)
        self.new_application = _ui_locale.widget(QCheckBox, _ui_tr('Neue Domain-Bewerbung für diese Zeile anlegen'))
        self.new_application.toggled.connect(self.personal_options_changed)
        right_layout.addWidget(self.new_application)
        self.personal_document = QComboBox()
        _ui_locale.add_item(self.personal_document, _ui_tr('Anschreiben: Gruppenvorlage'), 'inherit')
        _ui_locale.add_item(self.personal_document, _ui_tr('Anschreiben: keines'), None)
        for version in data.get("document_templates", []):
            _ui_locale.add_item(self.personal_document, _ui_format('{0} · v{1}', f"{version['name']}", f"{version['version_number']}"), version['id'])
        self.personal_document.currentIndexChanged.connect(self.personal_options_changed)
        right_layout.addWidget(self.personal_document)
        self.documents = QListWidget()
        self.documents.setMaximumHeight(100)
        self.documents.itemChanged.connect(self.documents_changed)
        right_layout.addWidget(label(_ui_tr('Dokumente dieser Bewerbung ausdrücklich anhängen'), 'muted'))
        right_layout.addWidget(self.documents)
        self.values = QTableWidget(0, 3)
        _ui_locale.headers(self.values, [_ui_tr('Platzhalter'), _ui_tr('Eigener Wert (optional)'), _ui_tr('Datenquelle / verwendeter Wert')])
        self.values.setWordWrap(False)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.values.setMinimumHeight(150)
        self.values.setMaximumHeight(210)
        self.values.itemChanged.connect(self.values_changed)
        right_layout.addWidget(self.values)
        personal_files = QHBoxLayout()
        self.personal_file_status = label(_ui_tr('Keine persönlichen Dateien'), 'muted')
        personal_files.addWidget(self.personal_file_status, 1)
        personal_files.addWidget(button(_ui_tr('Eigene Dateien'), self.add_personal_files))
        personal_files.addWidget(button(_ui_tr('Entfernen'), self.clear_personal_files))
        right_layout.addLayout(personal_files)
        right_layout.addWidget(label(_ui_tr('Leere eigene Werte verwenden die Kontaktdaten. Fehlende Pflichtwerte sperren die Gruppe.'), 'muted'))
        self.message = QPlainTextEdit()
        self.message.setReadOnly(True)
        self.message.setMinimumHeight(160)
        right_layout.addWidget(self.message, 1)
        panels.addWidget(left)
        panels.addWidget(right)
        panels.setStretchFactor(0, 1)
        panels.setStretchFactor(1, 2)
        form.addRow(panels)
        scroll.setWidget(content)
        new_layout.addWidget(scroll, 1)
        self.status = label(_ui_tr('Kontakte auswählen und Vorschau laden.'), 'muted')
        new_layout.addWidget(self.status)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Alle ausgewählten Nachrichten und Anhänge in der Vorschau geprüft'))
        new_layout.addWidget(self.confirm)
        actions = ActionFlowLayout()
        self.preview_button = button(_ui_tr('Alle Vorschauen laden'), self.request_preview)
        self.create_button = button(_ui_tr('Lokale Entwürfe erstellen'), self.create, primary=True)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.create_button)
        new_layout.addLayout(actions)
        _ui_locale.add_tab(self.tabs, new, _ui_tr('Neue Gruppe'))
        history = QWidget()
        history_layout = QVBoxLayout(history)
        self.batches = QListWidget()
        self.batches.currentRowChanged.connect(self.request_batch)
        self.batches.setMaximumHeight(150)
        history_layout.addWidget(self.batches)
        self.drafts = QListWidget()
        self.drafts.currentRowChanged.connect(self.update_buttons)
        history_layout.addWidget(self.drafts, 1)
        self.open_button = button(_ui_tr('Einzelentwurf öffnen'), self.open_draft)
        history_layout.addWidget(self.open_button)
        self.delivery_button = button(_ui_tr('Gruppenversand öffnen'), self.open_delivery, primary=True)
        history_layout.addWidget(self.delivery_button)
        _ui_locale.add_tab(self.tabs, history, _ui_tr('Gespeicherte Gruppen'))
        self.close_button = button(_ui_tr('Schließen'), self.reject)
        self.cancel_button = button(_ui_tr('Laufenden Vorgang abbrechen'), self.cancel_requested.emit)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.close_button)
        self.template.currentIndexChanged.connect(self.template_changed)
        self.document_choice.currentIndexChanged.connect(self.document_changed)
        self.document_format.currentIndexChanged.connect(self.invalidate)
        self.account.currentIndexChanged.connect(self.invalidate)
        self.signature.currentIndexChanged.connect(self.invalidate)
        self.confirm.toggled.connect(self.update_buttons)
        self.name.textChanged.connect(self.update_buttons)
        self.show_contacts()
        self.update_recipients()
        self.display_batches(data["batches"])
        self.update_buttons()
        compact_forms(self)
        defaults = data.get("project_settings", {})
        if defaults.get("account_id"):
            self.account.setCurrentIndex(max(0, self.account.findData(defaults["account_id"])))
        from .mail_defaults import apply_mail_defaults
        apply_mail_defaults(self, project_account=defaults.get("account_id"))
        preferred = defaults.get("defaults", {}).get("document_version_id")
        if preferred:
            self.document_choice.setCurrentIndex(max(0, self.document_choice.findData(preferred)))

    def display_collections(self, value):
        self.data.update(value)
        previous = self.group_filter.currentData()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        _ui_locale.add_item(self.group_filter, _ui_tr('Alle Kontakte'), None)
        for group in self.data.get("recipient_groups", []):
            self.group_filter.addItem(group["name"], group["id"])
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(previous)))
        self.group_filter.blockSignals(False)
        self.saved_filter.clear()
        _ui_locale.add_item(self.saved_filter, _ui_tr('Gespeicherten Filter wählen …'), None)
        for item in self.data.get("recipient_filters", []):
            self.saved_filter.addItem(item["name"], item["id"])

    def save_collection(self, kind):
        name, accepted = QInputDialog.getText(self, _ui_tr('Kontaktgruppe') if kind == 'group' else _ui_tr('Empfängerfilter'), _ui_tr('Name'))
        if accepted and name.strip():
            payload = {"kind": kind, "name": name.strip()}
            if kind == "group":
                payload["contact_ids"] = sorted(self.selected)
            else:
                payload["configuration"] = {"search": self.search.text(), "group_id": self.group_filter.currentData(), "valid_only": self.valid_only.isChecked()}
            self.operation_requested.emit("recipient_library_save", payload)

    def apply_filter(self):
        item = next((f for f in self.data.get("recipient_filters", []) if f["id"] == self.saved_filter.currentData()), None)
        if item:
            values = item["configuration"]
            if values["group_id"] and not any(g["id"] == values["group_id"] for g in self.data.get("recipient_groups", [])):
                QMessageBox.warning(self, _ui_tr('Filter prüfen'), _ui_tr('Die gespeicherte Kontaktgruppe wurde gelöscht. Filter neu anlegen.'))
                return
            self.search.setText(values["search"])
            self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(values["group_id"])))
            self.valid_only.setChecked(values["valid_only"])

    def delete_collection(self):
        kind, identifier = ("filter", self.saved_filter.currentData()) if self.saved_filter.currentData() else ("group", self.group_filter.currentData())
        if identifier and QMessageBox.question(self, _ui_tr('Sammlung löschen'), _ui_tr('Diese gespeicherte Sammlung löschen? Kontakte und Entwürfe bleiben erhalten.')) == QMessageBox.StandardButton.Yes:
            self.operation_requested.emit("recipient_library_delete", {"kind": kind, "identifier": identifier})

    def personal_options_changed(self):
        if self.loading or not self.recipient.currentData():
            return
        values = self.settings_for(self.recipient.currentData())
        values["create_application"] = self.new_application.isChecked()
        version = self.personal_document.currentData()
        if version == "inherit":
            values.pop("document_version_id", None)
        else:
            values["document_version_id"] = version
        self.invalidate()
        self.show_recipient()

    def settings_for(self, identifier):
        if identifier not in self.settings:
            contact = next((c for c in self.data["contacts"] if c["id"] == identifier), {})
            value = {"contact_id": identifier, "application_id": None, "values": {}, "documents": [], "attachments": []}
            if contact.get("source"):
                value["source"] = contact["source"]
            self.settings[identifier] = value
        return self.settings[identifier]

    def source_fields(self):
        version = next((v for v in self.data["templates"] if v["id"] == self.template.currentData()), None)
        doc = next((v for v in self.data.get("document_templates", []) if v["id"] == self.document_choice.currentData()), None)
        document_fields = [doc["mapping"].get(key, key) for key in doc["placeholders"]] if doc else []
        for values in self.settings.values():
            personal = next((v for v in self.data.get("document_templates", []) if v["id"] == values.get("document_version_id")), None)
            if personal:
                document_fields.extend(personal["mapping"].get(key, key) for key in personal["placeholders"])
        return list(dict.fromkeys([*SOURCE_FIELDS, *(version["placeholders"] if version else []),
                                  *document_fields]))

    def add_sources(self, value):
        for contact in value["contacts"]:
            existing = next((i for i, c in enumerate(self.data["contacts"]) if c["id"] == contact["id"]), None)
            if existing is None:
                self.data["contacts"].append(contact)
            else:
                self.data["contacts"][existing] = contact
                if contact["id"] in self.settings:
                    self.settings[contact["id"]]["source"] = contact["source"]
            self.selected.add(contact["id"])
        self.invalidate()
        self.show_contacts()
        self.update_recipients()

    def document_changed(self):
        version = next((v for v in self.data.get("document_templates", []) if v["id"] == self.document_choice.currentData()), None)
        self.document_bindings.setRowCount(0)
        self.document_bindings.setVisible(bool(version))
        if version:
            fields = self.source_fields()
            for key in version["placeholders"]:
                row = self.document_bindings.rowCount()
                self.document_bindings.insertRow(row)
                item = QTableWidgetItem(key)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.document_bindings.setItem(row, 0, item)
                combo = QComboBox()
                for field in fields:
                    _ui_locale.add_item(combo, (_ui_tr(SOURCE_FIELDS[field]) if field in SOURCE_FIELDS else field), field)
                combo.setCurrentIndex(max(0, combo.findData(version["mapping"].get(key, key))))
                combo.currentIndexChanged.connect(self.invalidate)
                self.document_bindings.setCellWidget(row, 1, combo)
        self.invalidate()
        self.show_recipient()

    def search_contacts(self):
        self.offset = 0
        self.show_contacts()

    def show_contacts(self):
        search = self.search.text().strip().casefold()
        rows = [c for c in self.data["contacts"] if search in (c["display_name"] + " " + (c["email"] or "")).casefold()]
        group = next((g for g in self.data.get("recipient_groups", []) if g["id"] == self.group_filter.currentData()), None)
        if group:
            rows = [c for c in rows if c["id"] in group["contact_ids"]]
        if self.valid_only.isChecked():
            rows = [c for c in rows if not c["error"]]
        self.contacts.blockSignals(True)
        self.contacts.clear()
        for contact in rows[self.offset:self.offset + 25]:
            flag = _ui_tr(" · Adresse ungültig/fehlt") if contact["error"] else _ui_tr(" · Adresse mehrfach vorhanden") if contact.get("duplicate") else ""
            item = _ui_locale.item(QListWidgetItem, _ui_format("{0}\n{1}{2}", contact["display_name"], contact["email"] or _ui_tr("Keine Adresse"), flag))
            item.setData(Qt.ItemDataRole.UserRole, contact["id"])
            item.setToolTip(contact.get("source_label", _ui_tr("Projektkontakt" if not contact.get("source") else "Manuelle Liste")))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if contact["id"] in self.selected else Qt.CheckState.Unchecked)
            self.contacts.addItem(item)
        self.contacts.blockSignals(False)
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(self.offset + 25 < len(rows))
        self.contact_hits = len(rows)
        self.update_selection_status()

    def update_selection_status(self):
        _ui_locale.set_text(self.selection_status, _ui_format('{0} ausgewählt (max. 100) · {1} Treffer · Seite {2}', f'{len(self.selected)}', f'{self.contact_hits}', f'{self.offset // 25 + 1}'))

    def move_page(self, direction):
        self.offset = max(0, self.offset + direction * 25)
        self.show_contacts()

    def contact_changed(self, item):
        identifier = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(identifier)
        else:
            self.selected.discard(identifier)
        self.invalidate()
        self.update_recipients()
        # Keep the emitting item alive while Qt finishes its itemChanged signal.
        # Its checkbox already displays the new state; rebuilding deletes it.
        self.update_selection_status()

    def select_visible(self):
        self.selected.update(self.contacts.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.contacts.count()))
        self.invalidate()
        self.update_recipients()
        self.show_contacts()

    def clear_selection(self):
        self.selected.clear()
        self.invalidate()
        self.update_recipients()
        self.show_contacts()

    def update_recipients(self):
        current = self.recipient.currentData()
        self.recipient.blockSignals(True)
        self.recipient.clear()
        for contact in self.data["contacts"]:
            if contact["id"] in self.selected:
                _ui_locale.add_item(self.recipient, _ui_format("{0} · {1}", contact["display_name"], contact["email"] or _ui_tr("Keine Adresse")), contact["id"])
        index = self.recipient.findData(current)
        self.recipient.setCurrentIndex(index if index >= 0 else 0)
        self.recipient.blockSignals(False)
        self.show_recipient()

    def show_recipient(self):
        identifier = self.recipient.currentData()
        self.loading = True
        self.values.setRowCount(0)
        self.documents.clear()
        self.application.setCurrentIndex(0)
        for widget in (self.application, self.values, self.documents, self.personal_document, self.new_application):
            widget.setEnabled(bool(identifier))
        if identifier:
            settings = self.settings_for(identifier)
            self.new_application.setChecked(settings.get("create_application", False))
            self.personal_document.setCurrentIndex(max(0, self.personal_document.findData(settings.get("document_version_id", "inherit"))))
            self.application.setCurrentIndex(max(0, self.application.findData(settings["application_id"])))
            for name in self.source_fields():
                row = self.values.rowCount()
                self.values.insertRow(row)
                key = QTableWidgetItem(name)
                key.setFlags(key.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.values.setItem(row, 0, key)
                self.values.setItem(row, 1, QTableWidgetItem(settings["values"].get(name, "")))
                default = QTableWidgetItem()
                default.setFlags(default.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.values.setItem(row, 2, default)
        personal = self.settings_for(identifier)["attachments"] if identifier else []
        _ui_locale.set_text(self.personal_file_status, _ui_format('{0} persönliche Dateien', f'{len(personal)}') if personal else _ui_tr('Keine persönlichen Dateien'))
        self.personal_file_status.setToolTip("\n".join(a["path"] for a in personal))
        self.loading = False
        self.show_source_values()
        self.show_message()
        if identifier and self.application.currentData():
            self.operation_requested.emit("mail_bulk_context", {"contact_id": identifier, "application_id": self.application.currentData(),
                "source": self.settings_for(identifier).get("source")})

    def template_changed(self):
        # Explicit values belong to a concrete version and cannot silently carry into another.
        for settings in self.settings.values():
            settings["values"] = {}
        self.invalidate()
        self.show_recipient()

    def show_source_values(self):
        identifier = self.recipient.currentData()
        contact = next((c for c in self.data["contacts"] if c["id"] == identifier), {})
        defaults = {"contact.display_name": contact.get("display_name", ""), "contact.email": contact.get("email", ""),
                    **contact.get("source_values", {})}
        row = next((r for r in self.preview["rows"] if r["contact_id"] == identifier), None) if self.preview and self.fresh else None
        if row:
            defaults.update(row.get("source_snapshot", {}).get("effective_values", {}))
        self.values.blockSignals(True)
        try:
            for index in range(self.values.rowCount()):
                name = self.values.item(index, 0).text()
                value = defaults.get(name, "")
                _ui_locale.set_text(self.values.item(index, 2), value)
                self.values.item(index, 2).setToolTip(value)
                _ui_locale.set_tooltip(self.values.item(index, 1), _ui_tr('Leer: Datenquelle / Projektwert verwenden.'))
        finally:
            self.values.blockSignals(False)

    def application_changed(self):
        identifier = self.recipient.currentData()
        if self.loading or not identifier:
            return
        settings = self.settings_for(identifier)
        settings["application_id"], settings["documents"] = self.application.currentData(), []
        self.documents.clear()
        self.invalidate()
        if settings["application_id"]:
            self.operation_requested.emit("mail_bulk_context", {"contact_id": identifier, "application_id": settings["application_id"], "source": settings.get("source")})

    def display_context(self, data):
        if data["selected_contact_id"] != self.recipient.currentData() or data["application_id"] != self.application.currentData():
            return
        selected = self.settings_for(self.recipient.currentData())["documents"]
        self.loading = True
        self.documents.clear()
        for document in data["documents"]:
            item = QListWidgetItem(document["original_filename"])
            item.setData(Qt.ItemDataRole.UserRole, document["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if document["id"] in selected else Qt.CheckState.Unchecked)
            self.documents.addItem(item)
        self.loading = False

    def values_changed(self):
        if not self.loading and self.recipient.currentData():
            self.settings_for(self.recipient.currentData())["values"] = {
                self.values.item(i, 0).text(): self.values.item(i, 1).text()
                for i in range(self.values.rowCount()) if self.values.item(i, 1) and self.values.item(i, 1).text().strip()}
            self.invalidate()

    def documents_changed(self):
        if not self.loading and self.recipient.currentData():
            self.settings_for(self.recipient.currentData())["documents"] = [
                self.documents.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.documents.count())
                if self.documents.item(i).checkState() == Qt.CheckState.Checked]
            self.invalidate()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, _ui_tr('Gemeinsame Anhänge auswählen'))
        self.files = list(dict.fromkeys(self.files + paths))
        self.update_files()

    def add_personal_files(self):
        identifier = self.recipient.currentData()
        if not identifier:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, _ui_tr('Anhänge für diesen Empfänger auswählen'))
        settings = self.settings_for(identifier)
        existing = [a["path"] for a in settings["attachments"]]
        settings["attachments"] = [{"path": path} for path in dict.fromkeys(existing + paths)]
        self.invalidate()
        self.show_recipient()

    def clear_personal_files(self):
        if self.recipient.currentData():
            self.settings_for(self.recipient.currentData())["attachments"] = []
            self.invalidate()
            self.show_recipient()

    def clear_files(self):
        self.files.clear()
        self.update_files()

    def update_files(self):
        _ui_locale.set_text(self.file_status, _ui_format('{0} gemeinsame Anhänge', f'{len(self.files)}') if self.files else _ui_tr('Keine gemeinsamen Anhänge'))
        self.file_status.setToolTip("\n".join(self.files))
        self.invalidate()

    def invalidate(self):
        if self.loading:
            return
        self.fresh = False
        self.confirm.setChecked(False)
        _ui_locale.set_text(self.status, _ui_tr('Auswahl oder Werte geändert: alle Vorschauen erneut laden.'))
        self.show_source_values()
        self.update_buttons()

    def update_buttons(self):
        if not hasattr(self, "create_button"):
            return
        ready = not self.busy and self.fresh and bool(self.preview and self.preview["ready"])
        self.confirm.setEnabled(ready)
        self.create_button.setEnabled(ready and self.confirm.isChecked() and bool(self.name.text().strip()))
        self.preview_button.setEnabled(not self.busy and bool(self.template.currentData()) and 1 <= len(self.selected) <= 100)
        row = self.drafts.currentRow()
        self.open_button.setEnabled(bool(self.batch and 0 <= row < len(self.batch["items"]) and not self.batch["items"][row]["deleted_at"]))
        self.delivery_button.setEnabled(bool(self.batch))

    def request_preview(self):
        if not self.busy:
            self.fresh = False
            self.confirm.setChecked(False)
            self.update_buttons()
            fields = set(self.source_fields())
            items = []
            for contact in self.data["contacts"]:
                if contact["id"] in self.selected:
                    settings = self.settings_for(contact["id"])
                    personal_fields = set(SOURCE_FIELDS) | set(next((v["placeholders"] for v in self.data["templates"] if v["id"] == self.template.currentData()), []))
                    selected_version = settings.get("document_version_id", self.document_choice.currentData())
                    selected_doc = next((v for v in self.data.get("document_templates", []) if v["id"] == selected_version), None)
                    if selected_doc:
                        personal_fields.update(selected_doc["placeholders"])
                        personal_fields.update(selected_doc["mapping"].values())
                        if selected_version == self.document_choice.currentData():
                            personal_fields.update(self.document_bindings.cellWidget(i, 1).currentData() for i in range(self.document_bindings.rowCount()))
                    items.append({**settings, "values": {k: v for k, v in settings["values"].items() if k in personal_fields}})
            self.operation_requested.emit("mail_bulk_preview", {
                "version_id": self.template.currentData(),
                "items": items,
                "provider_account_id": self.account.currentData(), "signature_id": self.signature.currentData(),
                "attachments": [{"path": path} for path in self.files],
                "document_version_id": self.document_choice.currentData(),
                "document_mapping": {self.document_bindings.item(i, 0).text(): self.document_bindings.cellWidget(i, 1).currentData()
                                     for i in range(self.document_bindings.rowCount())} if self.document_choice.currentData() else None,
                "document_format": self.document_format.currentData()})

    def display_preview(self, value):
        self.preview, self.fresh = value, True
        invalid = sum(bool(row["error"] or row["missing"]) for row in value["rows"])
        _ui_locale.set_text(self.status, _ui_format("{0} Vorschauen · {1} benötigen Korrektur. {2}", len(value["rows"]), invalid, _ui_tr("Jeden Empfänger oben zur Prüfung auswählen." if not invalid else "Ungültige/doppelte Kontakte abwählen oder persönliche Werte ergänzen.")))
        self.recipient.blockSignals(True)
        for i in range(self.recipient.count()):
            row = next(r for r in value["rows"] if r["contact_id"] == self.recipient.itemData(i))
            _ui_locale.set_item_text(self.recipient, i, _ui_format("{0} · {1} · {2}", _ui_tr("Bereit" if not row["error"] and not row["missing"] else "Prüfen"), row["name"], row["email"]))
        self.recipient.blockSignals(False)
        self.show_source_values()
        self.show_message()
        self.update_buttons()

    def show_message(self):
        row = next((r for r in self.preview["rows"] if r["contact_id"] == self.recipient.currentData()), None) if self.preview else None
        if not row:
            _ui_locale.set_plain_text(self.message, _ui_tr('Vorschau laden. HTML wird als Quelltext angezeigt.'))
            return
        missing = _ui_format('Fehlende Werte: {0}', ', '.join(row['missing'])) if row['missing'] else ''
        files = "\n".join(f"• {a['filename']} ({a['size']} Bytes)" for a in row["attachments"])
        generated = row.get("generated_document")
        if generated:
            files = _ui_format('{0}\n• {1} (wird persönlich erzeugt)\n\nAnschreiben – Textvorschau:\n{2}', files, generated['filename'], generated['text'])
        source = row.get("source_snapshot", {})
        origin = _ui_format('{0} · Zeile {1}', source.get('filename' if source.get('kind') == 'import' else 'list_name', ''), source.get('row_number', '')) if source.get('kind') in ('import', 'list') else _ui_tr('Manuelle Liste' if source.get('kind') == 'manual' else 'Projektkontakt')
        _ui_locale.set_plain_text(self.message, _ui_format('Datenquelle: {0}\nAn: {1}\n{2} {3}\nBetreff: {4}\n\n{5}\n\nAnhänge:\n{6}', origin, row['email'], row['error'], missing, row.get('subject', ''), row.get('preview_body', row.get('body', '')), files or _ui_tr('Keine Anhänge')))

    def create(self):
        if self.busy or not self.create_button.isEnabled():
            return
        if QMessageBox.question(self, _ui_tr('Lokale Entwurfsgruppe erstellen'), _ui_format('{0} persönliche Entwürfe lokal speichern? Anschließend den Gruppenversand öffnen und prüfen.', f"{len(self.preview['rows'])}")) != QMessageBox.StandardButton.Yes:
            return
        self.operation_requested.emit("mail_bulk_create", {"name": self.name.text(), "preview_id": self.preview["preview_id"]})

    def display_batches(self, batches, selected=None):
        self.data["batches"] = batches
        self.batches.blockSignals(True)
        self.batches.clear()
        for batch in batches:
            _ui_locale.add_item(self.batches, _ui_format('{0} · {1} Entwürfe · {2}', f"{batch['name']}", f"{batch['count']}", f"{batch['created_at'][:10]}"))
        self.batches.setCurrentRow(next((i for i, b in enumerate(batches) if b["id"] == selected), -1))
        self.batches.blockSignals(False)

    def request_batch(self):
        row = self.batches.currentRow()
        if 0 <= row < len(self.data["batches"]) and not self.busy:
            self.operation_requested.emit("mail_bulk_batch", {"batch_id": self.data["batches"][row]["id"]})

    def display_batch(self, value):
        self.batch = value
        self.drafts.clear()
        for row in value["items"]:
            state = "archiviert" if row["deleted_at"] else "lokaler Entwurf"
            _ui_locale.add_item(self.drafts, _ui_format('{0} · An: {1}\n{2} · {3}', f"{row['name_snapshot']}", f"{'; '.join(row['recipients']['to'])}", f"{row['subject']}", f'{state}'))
            source = row.get("source_snapshot", {})
            _ui_locale.set_tooltip(self.drafts.item(self.drafts.count() - 1), _ui_format('{0} · Zeile {1}', f"{source['filename']}", f"{source['row_number']}") if source.get('kind') == 'import' else _ui_format('{0} · Zeile {1}', f"{source['list_name']}", f"{source['row_number']}") if source.get('kind') == 'list' else _ui_tr('Manuelle Liste') if source.get('kind') == 'manual' else _ui_tr('Projektkontakt'))
        self.update_buttons()

    def created(self, value):
        self.invalidate()
        self.display_batches(value["batches"], value["batch"]["id"])
        self.display_batch(value["batch"])
        self.tabs.setCurrentIndex(1)
        _ui_locale.set_text(self.status, _ui_tr('Entwurfsgruppe gespeichert. Einzelentwürfe unter Gespeicherte Gruppen öffnen.'))

    def open_draft(self):
        if self.open_button.isEnabled() and not self.busy:
            identifier = self.batch["items"][self.drafts.currentRow()]["draft_id"]
            self.reject()
            self.draft_requested.emit(identifier)

    def set_busy(self, busy):
        self.busy = busy
        self.tabs.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.update_buttons()

    def open_delivery(self):
        if not self.busy and self.batch:
            self.delivery_requested.emit(self.batch["id"])
