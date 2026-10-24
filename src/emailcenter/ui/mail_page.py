"""Mail composition, approval review and delivery history without SQL in widgets."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
import re

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .dialogs import FormDialog
from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms


STATUS = {"Draft": "Freigabe offen", "Scheduled": "Geplant", "Queued": "Versandbereit",
          "Sending": "Versand läuft", "Sent": "Versendet", "Failed": "Fehlgeschlagen",
          "Cancelled": "Storniert", "Uncertain": "Ergebnis unklar", "ReconciliationRequired": "Abgleich erforderlich"}


def job_actions(job):
    """One set of availability rules for the mail page and workspace."""
    return {
        "review": bool(job),
        "send": bool(job and not job.get("batch_id") and job["status"] in ("Queued", "Scheduled") and job["approval_status"] == "approved" and not job["requires_overdue_confirmation"]),
        "reconcile": bool(job and job["status"] in ("Uncertain", "ReconciliationRequired")),
        "cancel": bool(job and job["status"] in ("Draft", "Scheduled", "Queued", "Failed")),
    }


def populate_accounts(combo, accounts, current=None):
    """Select the existing sender or the only account for an unassigned draft."""
    combo.clear()
    _ui_locale.add_item(combo, _ui_tr('Absenderkonto auswählen'), None)
    for account in accounts:
        if account["is_enabled"]:
            combo.addItem(account["account_email"], account["id"])
    index = combo.findData(current) if current else (1 if combo.count() == 2 else 0)
    combo.setCurrentIndex(max(0, index))


class ComposeDialog(QDialog):
    operation_requested = Signal(str, object)
    template_library_requested = Signal()

    def __init__(self, snapshot, draft=None, parent=None, *, context=None):
        super().__init__(parent)
        _ui_locale.set_window_title(self, _ui_tr('Entwurf bearbeiten') if draft else _ui_tr('Neuer E-Mail-Entwurf'))
        self.resize(780, 760)
        self.setMinimumSize(560, 480)
        self.context, self._context_body = None, ""
        self.project_documents = snapshot.get("documents", [])
        self.busy, self.draft_id = False, draft["id"] if draft else None
        self.attachments = [{"stored_path": item["path"], "filename": item["filename"], "hash": item["hash"], "document_id": item.get("document_id")}
                            for item in (draft["configuration"]["attachments"] if draft else [])]
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout.addWidget(label(_ui_tr('Entwürfe werden zuerst im Projekt gespeichert. Versand wird gesondert freigegeben.'), 'muted'))
        self.context_info = label("", "muted")
        self.context_info.hide()
        layout.addWidget(self.context_info)
        template_row = QHBoxLayout()
        self.template_choice = QComboBox()
        template_row.addWidget(self.template_choice, 1)
        self.preview_template = button(_ui_tr('Vorlage prüfen'), self.request_template)
        template_row.addWidget(self.preview_template)
        template_row.addWidget(button(_ui_tr('Vorlagen verwalten'), lambda: self.template_library_requested.emit()))
        layout.addLayout(template_row)
        self.template_choice.currentIndexChanged.connect(lambda _: self.preview_template.setEnabled(bool(self.template_choice.currentData())))
        self.refresh_templates(snapshot.get("mail_templates", []))
        form = QFormLayout()
        self.account, self.application, self.signature, self.format = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        _ui_locale.add_item(self.account, _ui_tr('Konto später auswählen'), None)
        for item in snapshot["accounts"]:
            if item["is_enabled"]:
                self.account.addItem(item["account_email"], item["id"])
        for widget, items, first, caption in (
            (self.application, snapshot.get("applications", []), "Ohne Bewerbung", "title"),
            (self.signature, snapshot["signatures"], "Ohne Signatur", "name"),
        ):
            _ui_locale.add_item(widget, _ui_tr(first), None)
            for item in items:
                widget.addItem(item[caption], item["id"])
        _ui_locale.add_item(self.format, _ui_tr('Text'), 'plain')
        _ui_locale.add_item(self.format, _ui_tr('HTML-Quelltext'), 'html')
        self.fields = {}
        _ui_locale.add_row(form, _ui_tr('Gmail-Konto'), self.account)
        application_controls = QHBoxLayout()
        application_controls.addWidget(self.application, 1)
        self.load_context = button(_ui_tr('Kontext übernehmen'), self.request_context)
        self.load_context.setEnabled(False)
        application_controls.addWidget(self.load_context)
        _ui_locale.add_row(form, _ui_tr('Bewerbung'), application_controls)
        self.context_contacts = QWidget()
        contacts_bar = QHBoxLayout(self.context_contacts)
        contacts_bar.setContentsMargins(0, 0, 0, 0)
        self.contact_choice = QComboBox()
        contacts_bar.addWidget(self.contact_choice, 1)
        self.use_contact = button(_ui_tr('Empfänger übernehmen'), self.choose_contact)
        contacts_bar.addWidget(self.use_contact)
        form.addRow(self.context_contacts)
        self.context_contacts.hide()
        for kind, caption in (("to", "An *"), ("cc", "Cc"), ("bcc", "Bcc"), ("subject", "Betreff *")):
            widget = QLineEdit()
            widget.setMaxLength(10000 if kind != "subject" else 998)
            if kind != "subject":
                _ui_locale.set_placeholder(widget, _ui_tr('name@example.com; weitere@example.com'))
            self.fields[kind] = widget
            _ui_locale.add_row(form, _ui_tr(caption), widget)
        _ui_locale.add_row(form, _ui_tr('Format'), self.format)
        _ui_locale.add_row(form, _ui_tr('Signatur'), self.signature)
        layout.addLayout(form)
        self.body = QPlainTextEdit()
        self.body.setMinimumHeight(140)
        _ui_locale.set_placeholder(self.body, _ui_tr('Nachrichtentext *'))
        layout.addWidget(self.body, 1)
        layout.addWidget(label(_ui_tr('Anhänge · feste Kopien beim Speichern · zusammen maximal 20 MiB'), 'muted'))
        self.attachment_list = QListWidget()
        self.attachment_list.setMaximumHeight(95)
        layout.addWidget(self.attachment_list)
        attachments_bar = ActionFlowLayout()
        attachments_bar.addWidget(button(_ui_tr('Dateien hinzufügen'), self.add_files))
        attachments_bar.addWidget(button(_ui_tr('Entfernen'), self.remove_attachment))
        self.documents = QComboBox()
        self.populate_documents(self.project_documents)
        attachments_bar.addWidget(self.documents, 1)
        attachments_bar.addWidget(button(_ui_tr('Anhängen'), self.add_document))
        layout.addLayout(attachments_bar)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Save), _ui_tr('Entwurf speichern'))
        _ui_locale.set_text(self.buttons.button(QDialogButtonBox.StandardButton.Cancel), _ui_tr('Abbrechen'))
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        if draft:
            for widget, key in ((self.account, "provider_account_id"), (self.application, "application_id"),
                                (self.signature, "signature_id"), (self.format, "body_format")):
                widget.setCurrentIndex(max(0, widget.findData(draft[key])))
            for kind in ("to", "cc", "bcc"):
                self.fields[kind].setText("; ".join(draft["recipients"].get(kind, [])))
            self.fields["subject"].setText(draft["subject"])
            _ui_locale.set_plain_text(self.body, draft['body'])
        elif self.account.count() == 2:
            self.account.setCurrentIndex(1)
        if not draft:
            settings = snapshot.get("project_settings", {})
            self.format.setCurrentIndex(max(0, self.format.findData(settings.get("defaults", {}).get("body_format", "plain"))))
            if settings.get("account_id"):
                self.account.setCurrentIndex(max(0, self.account.findData(settings["account_id"])))
            defaults = [item for item in snapshot["signatures"] if item["is_default"]]
            if len(defaults) == 1:
                self.signature.setCurrentIndex(self.signature.findData(defaults[0]["id"]))
        if not draft:
            from .mail_defaults import apply_mail_defaults
            apply_mail_defaults(self, project_account=snapshot.get("project_settings", {}).get("account_id"))
        if draft and draft["provider_account_id"] is None:
            populate_accounts(self.account, snapshot["accounts"])
        self.application.currentIndexChanged.connect(self.context_reference_changed)
        self.contact_choice.currentIndexChanged.connect(lambda _: self.use_contact.setEnabled(bool(self.contact_choice.currentData())))
        if context:
            self.apply_context(context)
        else:
            self.context_reference_changed()
        self.display_attachments()

    def refresh_templates(self, choices):
        previous = self.template_choice.currentData()
        self.template_choice.clear()
        _ui_locale.add_item(self.template_choice, _ui_tr('E-Mail-Vorlage auswählen …'), None)
        for choice in choices:
            _ui_locale.add_item(self.template_choice, _ui_format('{0} · Version {1}', f"{choice['template_name']}", f"{choice['version_number']}"), choice['id'])
        self.template_choice.setCurrentIndex(max(0, self.template_choice.findData(previous)))
        self.preview_template.setEnabled(bool(self.template_choice.currentData()))

    def request_template(self):
        if self.busy or not self.template_choice.currentData():
            return
        contact_id = None
        if self.context and self.application.currentData() == self.context["application_id"]:
            selected = next((item for item in self.context["candidates"] if item["id"] == self.context["selected_contact_id"]), None)
            if selected and self.values()["recipients_value"]["to"] == [selected["email"]]:
                contact_id = selected["id"]
        self.operation_requested.emit("mail_template_render", {"version_id": self.template_choice.currentData(),
            "application_id": self.application.currentData(), "contact_id": contact_id})

    def apply_template(self, result):
        self.fields["subject"].setText(result["subject"])
        _ui_locale.set_plain_text(self.body, result['body'])
        self.format.setCurrentIndex(self.format.findData(result["body_format"]))

    def populate_documents(self, documents, *, application=False):
        self.documents.clear()
        _ui_locale.add_item(self.documents, _ui_tr('Dokument dieser Bewerbung …') if application else _ui_tr('Dokument aus Projekt …'), None)
        for item in documents:
            self.documents.addItem(f"{item['original_filename']} · {item['format'].upper()}", item)

    def context_reference_changed(self):
        self.load_context.setEnabled(bool(self.application.currentData()))
        if self.context:
            matches = self.application.currentData() == self.context["application_id"]
            self.documents.setEnabled(matches)
            self.context_contacts.setEnabled(matches)
            selected = next((item for item in self.context["candidates"] if item["id"] == self.context["selected_contact_id"]), None)
            from ..language import join_text
            ambiguous = _ui_tr('Mehrere Ansprechpartner: gewünschten Empfänger ausdrücklich auswählen.')
            warnings = [text for text in self.context["warnings"] if not (selected and text in (ambiguous, ambiguous.message.source))]
            text = self.context["source_label"]
            if selected:
                text = _ui_format('{0}\nAnsprechpartner-Vorschlag: {1} · {2}', text, selected['display_name'], selected['email'])
            if self.context["application_id"]:
                text = _ui_format('{0}\n{1} passende Dokumente zur Auswahl; einzeln anhängen.', text, len(self.context['documents']))
            text = join_text('\n', (text, *warnings))
            if not matches:
                text = join_text('\n', (text, _ui_tr('Bewerbung geändert: Kontext übernehmen lädt neue Vorschläge. Bisherige Inhalte sind noch im Entwurf.')))
            _ui_locale.set_text(self.context_info, text)

    def request_context(self):
        if self.busy or not self.application.currentData():
            return
        if QMessageBox.question(self, _ui_tr('Bewerbungskontext übernehmen'), _ui_tr('Empfänger, Betreff, Nachrichtentext, Format und Anhangsauswahl durch Vorschläge dieser Bewerbung ersetzen?')) == QMessageBox.StandardButton.Yes:
            self.operation_requested.emit("mail_context_details", {"application_id": self.application.currentData()})

    def apply_context(self, context):
        self.context, self._context_body = context, context["body"]
        application_id = context["application_id"]
        if application_id and self.application.findData(application_id) < 0:
            self.application.addItem(context["source_label"], application_id)
        self.application.setCurrentIndex(max(0, self.application.findData(application_id)))
        self.format.setCurrentIndex(self.format.findData("plain"))
        for kind in ("to", "cc", "bcc"):
            self.fields[kind].setText("; ".join(context["recipients"][kind]))
        self.fields["subject"].setText(context["subject"])
        _ui_locale.set_plain_text(self.body, context['body'])
        self.attachments = []
        self.display_attachments()
        self.contact_choice.clear()
        _ui_locale.add_item(self.contact_choice, _ui_tr('Ansprechpartner auswählen …'), None)
        for contact in context["candidates"]:
            self.contact_choice.addItem(f"{contact['display_name']} · {contact['email']} ({contact['source']})", contact)
        for index in range(1, self.contact_choice.count()):
            if self.contact_choice.itemData(index)["id"] == context["selected_contact_id"]:
                self.contact_choice.setCurrentIndex(index)
                break
        self.use_contact.setEnabled(bool(self.contact_choice.currentData()))
        self.context_contacts.setVisible(bool(context["candidates"]))
        self.populate_documents(context["documents"] if application_id else self.project_documents, application=bool(application_id))
        self.context_info.show()
        self.context_reference_changed()

    def choose_contact(self):
        contact = self.contact_choice.currentData()
        if self.busy or not contact or not self.context_contacts.isEnabled():
            return
        self.fields["to"].setText(contact["email"])
        self.context["selected_contact_id"] = contact["id"]
        if self.body.toPlainText() == self._context_body:
            self._context_body = "Guten Tag " + contact["display_name"] + ",\n" + self._context_body.split("\n", 1)[1]
            _ui_locale.set_plain_text(self.body, self._context_body)
        self.context_reference_changed()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, _ui_tr('Anhänge auswählen'))
        self.attachments.extend({"path": path, "filename": Path(path).name} for path in paths)
        self.display_attachments()

    def add_document(self):
        if not self.documents.isEnabled():
            return
        item = self.documents.currentData()
        if item and not any(entry.get("document_id") == item["id"] for entry in self.attachments):
            self.attachments.append({"document_id": item["id"], "filename": item["original_filename"]})
            self.display_attachments()

    def remove_attachment(self):
        index = self.attachment_list.currentRow()
        if index >= 0:
            self.attachments.pop(index)
            self.display_attachments()

    def display_attachments(self):
        self.attachment_list.clear()
        self.attachment_list.addItems([item["filename"] for item in self.attachments])

    def values(self):
        targets = {kind: [value.strip() for value in re.split(r"[;,]", self.fields[kind].text()) if value.strip()] for kind in ("to", "cc", "bcc")}
        values = {"subject": self.fields["subject"].text().strip(), "body": self.body.toPlainText(),
                  "recipients_value": targets, "body_format": self.format.currentData(),
                  "provider_account_id": self.account.currentData(), "application_id": self.application.currentData(),
                  "signature_id": self.signature.currentData(), "attachments": self.attachments}
        if self.draft_id:
            values["draft_id"] = self.draft_id
        return values

    def save(self):
        from ..mail_models import MailError, header, recipients
        values = self.values()
        try:
            header(values["subject"], "Betreff")
            recipients(values["recipients_value"])
            if not values["body"].strip():
                raise MailError(_ui_tr('Bitte einen Nachrichtentext eingeben.'))
        except MailError as error:
            QMessageBox.warning(self, _ui_tr('Eingabe prüfen'), str(error))
            return
        self.operation_requested.emit("mail_save_draft", values)

    def set_busy(self, busy):
        self.busy = busy
        self.setEnabled(not busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)


class MailJobDialog(QDialog):
    operation_requested = Signal(str, object)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job, self.busy = job, False
        _ui_locale.set_window_title(self, _ui_tr('Versandauftrag prüfen'))
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for caption, value in (("Status", _ui_tr(STATUS.get(job["status"], job["status"]))), ("Von", job["sender_snapshot"]),
                               ("An", "; ".join(job["recipients"]["to"])), ("Cc", "; ".join(job["recipients"]["cc"])),
                               ("Bcc", "; ".join(job["recipients"]["bcc"])), ("Betreff", job["subject_snapshot"]),
                               ("Versandzeit", _ui_format('{0} · {1}', job['scheduled_at_utc'], job['timezone_id']) if job['scheduled_at_utc'] else _ui_tr('Manuell nach Freigabe')),
                               ("Anhänge", "; ".join(item["filename_snapshot"] for item in job["attachments"]) or _ui_tr("Keine"))):
            value_widget = label(value or "")
            value_widget.setTextFormat(Qt.TextFormat.PlainText)
            value_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            _ui_locale.add_row(form, _ui_tr(caption), value_widget)
        layout.addLayout(form)
        layout.addWidget(label(_ui_tr('Gespeicherter Nachrichtentext einschließlich Signatur'), 'muted'))
        self.body = QPlainTextEdit(job["body_snapshot"])
        self.body.setReadOnly(True)
        layout.addWidget(self.body, 1)
        if job["last_error_message"]:
            error = label(job["last_error_message"], "muted")
            error.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(error)
        if job["attempts"]:
            history = QPlainTextEdit("\n".join(f'{item["attempt_number"]}. {item["result"]} · {item["started_at_utc"]} · {item["error_message"] or item["provider_message_id"] or ""}' for item in job["attempts"]))
            history.setReadOnly(True)
            history.setMaximumHeight(85)
            layout.addWidget(history)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Empfänger, Inhalt und Anhänge geprüft; diesen Auftrag freigeben.'))
        if job["requires_overdue_confirmation"]:
            _ui_locale.set_text(self.confirm, _ui_tr('Überfälligen Auftrag geprüft; Nachversand ausdrücklich freigeben.'))
        can_approve = not job.get("bulk_dispatch_id") and job["status"] in ("Draft", "Scheduled", "Queued", "Failed")
        if job.get("bulk_dispatch_id"):
            layout.addWidget(label(_ui_tr('Dieser Auftrag gehört zum Gruppenversand. Unter Bulk → Gespeicherte Gruppen gemeinsam freigeben und versenden.'), 'muted'))
        self.confirm.setVisible(can_approve)
        layout.addWidget(self.confirm)
        actions = ActionFlowLayout()
        actions.addStretch()
        actions.addWidget(button(_ui_tr('Schließen'), self.reject))
        self.approve_button = button(_ui_tr('Erneut freigeben') if job['status'] == 'Failed' else _ui_tr('Freigeben'), self.approve, primary=True)
        self.approve_button.setVisible(can_approve)
        self.approve_button.setEnabled(False)
        self.confirm.toggled.connect(self.approve_button.setEnabled)
        actions.addWidget(self.approve_button)
        self.send_now_button = button(_ui_tr('Freigeben & jetzt senden'), self.approve_and_send, primary=True)
        self.send_now_button.setVisible(can_approve)
        self.send_now_button.setEnabled(False)
        self.confirm.toggled.connect(self.send_now_button.setEnabled)
        actions.addWidget(self.send_now_button)
        layout.addLayout(actions)

    def approve(self):
        if self.confirm.isChecked():
            action = "mail_retry" if self.job["status"] == "Failed" else "mail_approve"
            payload = {"job_id": self.job["id"]}
            if action == "mail_approve":
                payload["confirm_overdue"] = bool(self.job["requires_overdue_confirmation"])
            self.operation_requested.emit(action, payload)

    def approve_and_send(self):
        if self.busy or not self.confirm.isChecked() or self.job["status"] not in ("Draft", "Scheduled", "Queued", "Failed"):
            return
        message = _ui_format('Diesen Auftrag freigeben und jetzt über Gmail senden?\n\nVon: {0}\nAn: {1}\nBetreff: {2}', self.job['sender_snapshot'], '; '.join(self.job['recipients']['to']), self.job['subject_snapshot'])
        if self.job["scheduled_at_utc"]:
            message = _ui_format('{0}\n\nDer geplante Termin wird durch den sofortigen Versand vorgezogen.', message)
        if QMessageBox.question(self, _ui_tr('Freigeben und sofort senden'), message) == QMessageBox.StandardButton.Yes:
            self.operation_requested.emit("mail_approve_and_send", {"job_id": self.job["id"],
                "confirm_overdue": bool(self.job["requires_overdue_confirmation"])})

    def set_busy(self, busy):
        self.busy = busy
        self.setEnabled(not busy)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)


class MailPage(QWidget):
    operation_requested = Signal(str, object)
    compose_requested = Signal(object)
    review_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.data, self.draft_offset, self.job_offset = None, 0, 0
        self.focus_job_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 26)
        layout.addWidget(label(_ui_tr('E-Mail'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Entwürfe vorbereiten, Versand freigeben und Ergebnisse nachvollziehen.'), 'muted'))
        accounts = QHBoxLayout()
        self.account = QComboBox()
        accounts.addWidget(self.account, 1)
        accounts.addWidget(button(_ui_tr('Gmail verbinden'), self.connect_gmail, primary=True))
        accounts.addWidget(button(_ui_tr('Trennen'), self.disconnect))
        accounts.addWidget(button(_ui_tr('Aktualisieren'), self.request_load))
        layout.addLayout(accounts)
        self.scheduler = _ui_locale.widget(QCheckBox, _ui_tr('Freigegebene geplante Nachrichten automatisch senden, solange EmailCenter geöffnet ist.'))
        layout.addWidget(self.scheduler)
        layout.addWidget(label(_ui_tr('Nach Neustart oder Standby brauchen überfällige Aufträge eine erneute Freigabe.'), 'muted'))
        self.tabs = QTabWidget()
        self.tables, self.buttons = {}, {}
        definitions = (("drafts", "Entwürfe", ["Betreff", "Empfänger", "Gmail-Entwurf", "Geändert"],
                        [("Neu", "new"), ("Bearbeiten", "edit"), ("Signatur anlegen", "signature"), ("In Gmail speichern", "sync"), ("Senden / planen", "prepare")]),
                       ("jobs", "Versandaufträge", ["Betreff", "Empfänger", "Status", "Termin (UTC)", "Versuche"],
                        [("Prüfen / Freigeben", "review"), ("Jetzt senden", "send"), ("Gmail abgleichen", "reconcile"), ("Stornieren", "cancel")]))
        for kind, caption, headers, actions in definitions:
            tab, table = QWidget(), QTableWidget(0, len(headers))
            tab_layout = QVBoxLayout(tab)
            bar = ActionFlowLayout()
            for text, action in actions:
                control = button(text, lambda checked=False, action=action: self.action(action))
                self.buttons[action] = control
                bar.addWidget(control)
            bar.addStretch()
            tab_layout.addLayout(bar)
            table.setHorizontalHeaderLabels(headers)
            table.verticalHeader().hide()
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.itemSelectionChanged.connect(self.update_buttons)
            self.tables[kind] = table
            tab_layout.addWidget(table, 1)
            pagination = QHBoxLayout()
            pagination.addWidget(button(_ui_tr('Zurück'), lambda checked=False, kind=kind: self.change_page(kind, -1)))
            pagination.addWidget(button(_ui_tr('Weiter'), lambda checked=False, kind=kind: self.change_page(kind, 1)))
            pagination.addStretch()
            tab_layout.addLayout(pagination)
            self.tabs.addTab(tab, caption)
        layout.addWidget(self.tabs, 1)
        self.summary = label(_ui_tr('Projekt öffnen, um Entwürfe anzulegen.'), 'muted')
        layout.addWidget(self.summary)
        self.reset()

    def reset(self):
        self.data, self.draft_offset, self.job_offset = None, 0, 0
        self.focus_job_id = None
        self.scheduler.setChecked(False)
        self.account.clear()
        for table in self.tables.values():
            table.setRowCount(0)
        self.update_buttons()

    def request_load(self):
        self.operation_requested.emit("mail_snapshot", {"draft_offset": self.draft_offset, "job_offset": self.job_offset})

    def selected(self, kind):
        index = self.tables[kind].currentRow()
        items = self.data[kind] if self.data else []
        return items[index] if 0 <= index < len(items) else None

    def display(self, data):
        selected = {kind: self.selected(kind)["id"] if self.selected(kind) else None for kind in self.tables}
        if self.focus_job_id:
            selected["jobs"] = self.focus_job_id
            self.focus_job_id = None
        account_id = self.account.currentData()
        self.data = data
        self.draft_offset, self.job_offset = data["draft_offset"], data["job_offset"]
        self.account.clear()
        for item in data["accounts"]:
            _ui_locale.add_item(self.account, _ui_format("{0} · getrennt", item["account_email"]) if not item["is_enabled"] else item["account_email"], item["id"])
        self.account.setCurrentIndex(max(0, self.account.findData(account_id)))
        for kind, table in self.tables.items():
            table.setRowCount(len(data[kind]))
            for index, item in enumerate(data[kind]):
                if kind == "drafts":
                    values = (item["subject"], "; ".join(item["recipients"]["to"]), _ui_tr('Gespeichert') if item['synced_hash'] else _ui_tr('Nur lokal'), item["updated_at"])
                else:
                    status = _ui_tr(STATUS.get(item["status"], item["status"]))
                    if item["requires_overdue_confirmation"]:
                        status = _ui_format('{0} · Nachversand prüfen', status)
                    elif item["approval_status"] != "approved" and item["status"] in ("Scheduled", "Queued"):
                        status = _ui_format('{0} · Freigabe offen', status)
                    values = (item["subject_snapshot"], "; ".join(item["recipients"]["to"]), status, item['scheduled_at_utc'] or _ui_tr('Manuell'), str(item["attempt_count"]))
                for column, value in enumerate(values):
                    cell = _ui_locale.cell(value)
                    cell.setToolTip(value)
                    table.setItem(index, column, cell)
                if item["id"] == selected[kind]:
                    table.selectRow(index)
        _ui_locale.set_text(self.summary, _ui_format('{0} Entwürfe · {1} Versandaufträge · 50 Einträge pro Seite', f"{data['draft_total']}", f"{data['job_total']}"))
        self.update_buttons()

    def update_buttons(self):
        draft, job = self.selected("drafts"), self.selected("jobs")
        for action in ("edit", "sync", "prepare"):
            self.buttons[action].setEnabled(bool(draft))
        for action, enabled in job_actions(job).items():
            self.buttons[action].setEnabled(enabled)

    def change_page(self, kind, direction):
        if not self.data:
            return
        attribute = "draft_offset" if kind == "drafts" else "job_offset"
        offset = getattr(self, attribute)
        candidate = max(0, offset + direction * 50)
        if candidate == 0 or candidate < self.data["draft_total" if kind == "drafts" else "job_total"]:
            setattr(self, attribute, candidate)
            self.request_load()

    def connect_gmail(self):
        from ..resources import shared_oauth_client
        shared = shared_oauth_client()
        if shared:
            self.operation_requested.emit("mail_connect", {"client_path": str(shared)})
            return
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Google-OAuth-Clientdatei (Desktop-App)'), filter='Google-Clientdatei (*.json)')
        if path:
            self.operation_requested.emit("mail_connect", {"client_path": path})

    def disconnect(self):
        if self.account.currentData() and QMessageBox.question(self, _ui_tr('Gmail trennen'), _ui_tr('Lokale Anmeldung dieses Kontos entfernen? Geplante Aufträge brauchen danach eine neue Freigabe.')) == QMessageBox.StandardButton.Yes:
            self.operation_requested.emit("mail_disconnect", {"account_id": self.account.currentData()})

    def action(self, action):
        draft, job = self.selected("drafts"), self.selected("jobs")
        if action in ("new", "edit"):
            self.compose_requested.emit(draft if action == "edit" else None)
        elif action == "signature":
            dialog = FormDialog(_ui_tr('Signatur anlegen'), [('name', 'Name', 'required'), ('content_text', 'Text', 'multiline'), ('content_html', 'HTML (optional)', 'multiline')], parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                values = dialog.values()
                values["content_text"], values["content_html"] = values["content_text"] or "", values["content_html"] or ""
                self.operation_requested.emit("mail_save_signature", values)
        elif action == "sync" and draft:
            self.operation_requested.emit("mail_sync_draft", {"draft_id": draft["id"]})
        elif action == "prepare" and draft:
            accounts = [("Absenderkonto auswählen", None)] + [(a["account_email"], a["id"]) for a in self.data["accounts"] if a["is_enabled"]]
            dialog = FormDialog(_ui_tr('E-Mail senden / planen'), [('provider_account_id', 'Absenderkonto', accounts), ('scheduled_local', 'Termin (leer = manuell)', None), ('timezone_id', 'Zeitzone', 'required')], parent=self)
            populate_accounts(dialog.fields["provider_account_id"], self.data["accounts"], draft["provider_account_id"])
            from .mail_defaults import preferences_of, choose_named
            preferences = preferences_of(self)
            dialog.fields["timezone_id"].setText(preferences.mail_timezone_id if preferences else "Europe/Berlin")
            if preferences and not draft["provider_account_id"]:
                choose_named(dialog.fields["provider_account_id"], preferences.mail_account_email)
            _ui_locale.set_placeholder(dialog.fields['scheduled_local'], _ui_tr('2026-10-20T09:30'))
            send_button = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
            _ui_locale.set_text(send_button, _ui_tr('Senden'))
            dialog.fields["scheduled_local"].textChanged.connect(
                lambda text: _ui_locale.set_text(send_button, _ui_tr('Versand planen') if text.strip() else _ui_tr('Senden')))
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.operation_requested.emit("mail_prepare_job", {"draft_id": draft["id"], **dialog.values()})
        elif action == "review" and job:
            self.review_requested.emit(job)
        elif action == "send" and job:
            if QMessageBox.question(self, _ui_tr('Freigegebenen Auftrag senden'), _ui_format('Diese Nachricht jetzt über Gmail senden?\n\n{0}\nAn: {1}', f"{job['subject_snapshot']}", f"{'; '.join(job['recipients']['to'])}")) == QMessageBox.StandardButton.Yes:
                self.operation_requested.emit("mail_send", {"job_id": job["id"], "send_now": True})
        elif action == "reconcile" and job:
            self.operation_requested.emit("mail_reconcile", {"job_id": job["id"]})
        elif action == "cancel" and job:
            self.operation_requested.emit("mail_cancel", {"job_id": job["id"]})
