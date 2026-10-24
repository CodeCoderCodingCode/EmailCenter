"""Project work area with mode-specific actions and direct editors."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QListWidget, QScrollArea, QVBoxLayout, QWidget

from .pages import button, label
from .responsive import ActionFlowLayout, compact_forms
from .mail_page import STATUS
from .mail_workflow import MailWorkflow


class WorkspacePage(QScrollArea):
    action_requested = Signal(str, object)
    mode_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.snapshot = None
        content = QWidget()
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label(_ui_tr('Arbeitsbereich'), 'pageTitle'))
        self.project_title = label(_ui_tr('Bitte zuerst ein Projekt öffnen.'), 'muted')
        layout.addWidget(self.project_title)
        self.goal = label("", "muted")
        layout.addWidget(self.goal)
        self.mode = QComboBox()
        _ui_locale.add_item(self.mode, _ui_tr('Bewerbungen'), 'applications')
        _ui_locale.add_item(self.mode, _ui_tr('E-Mail-Aufträge'), 'mail')
        self.mode.activated.connect(lambda _: self.mode_requested.emit(self.mode.currentData()))
        layout.addWidget(self.mode)
        self.summary = label("", "muted")
        layout.addWidget(self.summary)
        self.guided_panel = QFrame()
        self.guided_panel.setObjectName('card')
        guide = QVBoxLayout(self.guided_panel)
        guide.addWidget(label(_ui_tr('Geführter Projektablauf')))
        self.guided_steps = label('', 'muted')
        self.guided_steps.setWordWrap(True)
        guide.addWidget(self.guided_steps)
        self.guided_next = button(_ui_tr('Nächsten Schritt öffnen'), lambda: self.action_requested.emit(self._guided_action, None))
        guide.addWidget(self.guided_next)
        layout.addWidget(self.guided_panel)
        self.mail_workflow = MailWorkflow()
        layout.addWidget(self.mail_workflow)
        self.bulk_panel = QWidget()
        bulk_layout = QVBoxLayout(self.bulk_panel)
        bulk_layout.addWidget(label(_ui_tr('Gruppenversand · Hintergrund und pausierte Aufträge')))
        self.bulk_groups = QComboBox()
        bulk_layout.addWidget(self.bulk_groups)
        bulk_actions = ActionFlowLayout()
        for action, caption in (("bulk_open", "Prüfen / Fortsetzen"), ("bulk_pause", "Pause"), ("bulk_cancel", "Offene abbrechen")):
            bulk_actions.addWidget(button(caption, lambda checked=False, key=action: self.bulk_action(key)))
        bulk_layout.addLayout(bulk_actions)
        layout.addWidget(self.bulk_panel)
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        layout.addLayout(self.grid)
        self.cards = []
        self.buttons = {}
        actions_card, actions = self.card("Nächste Schritte")
        self.hint = label("", "muted")
        actions.addWidget(self.hint)
        for key, caption in (("profile", "Bewerberprofil anlegen"), ("company", "Unternehmen anlegen"),
                             ("application", "Neue Bewerbung"), ("compose", "E-Mail schreiben"),
                             ("bulk", "Bulk-Bewerbungen vorbereiten"),
                             ("contact", "Kontakt anlegen"), ("reminder", "Erinnerung anlegen"),
                             ("followups", "Nachfassen prüfen"), ("mail", "Alle Entwürfe und Aufträge"), ("export", "CSV / Excel exportieren"),
                             ("word_replace", "Word Replace · Dokumentkopien"), ("project_settings", "Projektziel / Vorgaben bearbeiten")):
            control = button(caption, lambda checked=False, key=key: self.action_requested.emit(key, None),
                             primary=key in ("application", "compose"))
            self.buttons[key] = control
            actions.addWidget(control)
        actions.addStretch()
        recent_card, recent = self.card("Aktuelle Vorgänge · doppelklicken zum Bearbeiten / Prüfen")
        self.recent = QListWidget()
        self.recent.setMinimumHeight(170)
        self.recent.itemDoubleClicked.connect(self.open_recent)
        recent.addWidget(self.recent)
        self.empty = label(_ui_tr('Noch keine Vorgänge. Starte über die nächsten Schritte.'), 'muted')
        recent.addWidget(self.empty)
        templates_card, templates = self.card("Dokumentvorlagen")
        self.templates = QComboBox()
        templates.addWidget(self.templates)
        self.use_template = button(_ui_tr('Ausgewählte Vorlage verwenden'), self.generate)
        templates.addWidget(self.use_template)
        templates.addWidget(button(_ui_tr('DOCX-Vorlage importieren'), lambda: self.action_requested.emit('import_template', None)))
        templates.addWidget(button(_ui_tr('Alle Vorlagen verwalten'), lambda: self.action_requested.emit('templates', None)))
        templates.addWidget(button(_ui_tr('E-Mail-Vorlagen verwalten'), lambda: self.action_requested.emit('mail_templates', None)))
        templates.addWidget(button(_ui_tr('E-Mail-Builder öffnen'), lambda: self.action_requested.emit('builder', None)))
        templates.addWidget(button(_ui_tr('Dokumente öffnen / PDF erzeugen'), lambda: self.action_requested.emit('documents', None)))
        templates.addStretch()
        context_card, context = self.card("E-Mail aus Bewerbung / Kontakt")
        self.context_kind = QComboBox()
        _ui_locale.add_item(self.context_kind, _ui_tr('Bewerbung'), 'applications')
        _ui_locale.add_item(self.context_kind, _ui_tr('Kontakt'), 'contacts')
        context.addWidget(self.context_kind)
        self.context_record = QComboBox()
        context.addWidget(self.context_record)
        self.context_compose = button(_ui_tr('E-Mail aus Auswahl schreiben'), self.compose_context, primary=True)
        context.addWidget(self.context_compose)
        context.addWidget(label(_ui_tr('Empfänger und Text werden vorgeschlagen. Passende Bewerbungsdokumente gezielt auswählen; anschließend alles prüfen.'), 'muted'))
        context.addStretch()
        self.context_kind.currentIndexChanged.connect(self.update_context_choices)
        self.context_record.currentIndexChanged.connect(lambda _: self.context_compose.setEnabled(bool(self.context_record.currentData())))
        self.update_context_choices()
        self.reflow()
        layout.addStretch()

    def card(self, title):
        widget = QFrame()
        widget.setObjectName("card")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(label(_ui_tr(title)))
        self.cards.append(widget)
        return widget, layout

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        columns = 2 if self.viewport().width() >= 760 else 1
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)

    def update_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.display_bulk_groups(snapshot.get("bulk_groups", []) if snapshot else [])
        self.setEnabled(bool(snapshot))
        _ui_locale.set_text(self.project_title, snapshot['name'] if snapshot else _ui_tr('Bitte zuerst ein Projekt öffnen.'))
        _ui_locale.set_text(self.goal, snapshot.get('project_goal', '') if snapshot else '')
        self.goal.setVisible(bool(self.goal.text()))
        mode = snapshot.get("workspace_mode", "applications") if snapshot else "applications"
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        mail = mode == "mail"
        _ui_locale.set_text(self.buttons["bulk"], _ui_tr("Bulk-E-Mails vorbereiten" if mail else "Bulk-Bewerbungen vorbereiten"))
        if getattr(self, "_context_mode", None) != mode:
            self.context_kind.setCurrentIndex(1 if mail else 0)
            self._context_mode = mode
        self.mail_workflow.setVisible(bool(snapshot) and (mail or bool(snapshot["counts"].get("mail_drafts") or snapshot["counts"].get("mail_jobs"))))
        counts = snapshot["counts"] if snapshot else {}
        self.update_guided_progress(counts, mail)
        from ..preferences import Preferences
        prefs = getattr(self.window(), 'preferences', Preferences())
        self.guided_panel.setVisible(bool(snapshot) and prefs.guided_workspace)
        _ui_locale.set_text(self.summary, _ui_format('{0} Entwürfe · {1} Versandaufträge · {2} fällige Erinnerungen', f"{counts.get('mail_drafts', 0)}", f"{counts.get('mail_jobs', 0)}", f"{counts.get('followups', 0)}") if mail else _ui_format('{0} Bewerbungen · {1} Dokumente · {2} fällige Erinnerungen', f"{counts.get('applications', 0)}", f"{counts.get('documents', 0)}", f"{counts.get('followups', 0)}"))
        for key in ("profile", "company", "application"):
            self.buttons[key].setVisible(not mail)
        for key in ("compose", "contact", "mail"):
            self.buttons[key].setVisible(mail)
        self.buttons["application"].setEnabled(bool(counts.get("companies") and counts.get("applicants")))
        _ui_locale.set_text(self.hint, _ui_tr('Einzel- oder Bulk-Nachrichten vorbereiten → persönliche Inhalte prüfen → freigeben und direkt/geplant senden.') if mail else _ui_tr('Profil und Unternehmen anlegen → Bewerbung erfassen → Vorlage verwenden → E-Mail vorbereiten.'))
        if snapshot and not mail:
            from ..language import join_text
            missing = [_ui_tr(caption) for key, caption in (("applicants", "Bewerberprofil"), ("companies", "Unternehmen")) if not counts.get(key)]
            if missing:
                _ui_locale.set_text(self.hint, _ui_format('Für die erste Bewerbung noch anlegen: {0}.', join_text(', ', missing)))
        # E-mail is also available directly while working on applications.
        self.buttons["compose"].setVisible(bool(snapshot))
        self.recent.clear()
        records = snapshot.get("recent_mail_jobs" if mail else "recent_applications", []) if snapshot else []
        for record in records:
            title = record["subject_snapshot"] if mail else record["title"]
            status = _ui_tr(STATUS.get(record["status"], record["status"])) if mail else record["status_label"]
            if mail and record["approval_status"] != "approved" and record["status"] in ("Scheduled", "Queued"):
                status = _ui_format('{0} · Freigabe erforderlich', status)
            _ui_locale.add_item(self.recent, _ui_format('{0} · {1}', title, status))
            self.recent.item(self.recent.count() - 1).setData(Qt.ItemDataRole.UserRole, ("job" if mail else "edit_application", record["id"]))
        self.empty.setVisible(not records)
        previous = self.templates.currentData()
        self.templates.clear()
        for record in snapshot.get("workspace_templates", []) if snapshot else []:
            _ui_locale.add_item(self.templates, _ui_format('{0} · Version {1}', f"{record['template_name']}", f"{record['version_number']}"), record)
        if previous:
            for index in range(self.templates.count()):
                if self.templates.itemData(index)["id"] == previous["id"]:
                    self.templates.setCurrentIndex(index)
                    break
        elif snapshot:
            preferred = snapshot.get("project_settings", {}).get("defaults", {}).get("document_version_id")
            for index in range(self.templates.count()):
                if self.templates.itemData(index)["id"] == preferred:
                    self.templates.setCurrentIndex(index)
                    break
        self.use_template.setEnabled(bool(self.templates.count()))
        self.update_context_choices()

    def update_guided_progress(self, counts, mail):
        steps = [(_ui_tr('Projekt angelegt'), bool(self.snapshot), 'project_settings')]
        if not mail:
            steps.append((_ui_tr('Bewerberprofil vorhanden'), bool(counts.get('applicants')), 'profile'))
        steps.extend([
            (_ui_tr('Kontakte / Empfänger vorhanden'), bool(counts.get('contacts')), 'contact'),
            (_ui_tr('Vorlagen / Dokumente vorbereitet'), bool(counts.get('templates') or counts.get('documents')), 'templates'),
            (_ui_tr('Persönliche E-Mail-Entwürfe erstellt'), bool(counts.get('mail_drafts')), 'builder'),
            (_ui_tr('Gmail verbunden'), bool(counts.get('connected_accounts')), 'mail'),
            (_ui_tr('Versandaufträge freigegeben'), bool(counts.get('approved_jobs') or counts.get('sent_jobs')), 'mail'),
            (_ui_tr('Ersten Versand abgeschlossen'), bool(counts.get('sent_jobs')), 'mail'),
        ])
        if mail:
            steps = [s for s in steps if s[2] != 'templates']
        self._guided_action = next((action for _, ready, action in steps if not ready), 'mail')
        _ui_locale.set_text(self.guided_steps, '\n'.join(('✓ ' if ready else '○ ') + str(title) for title, ready, _ in steps))
        self.guided_steps.setToolTip(str(_ui_tr('Fortschritt aus gespeicherten Projektdaten. Eine vorhandene Vorlage oder ein Entwurf ersetzt keine Inhaltsprüfung. Für Excel-Bulk direkt den Builder öffnen.')))

    def update_context_choices(self):
        previous = self.context_record.currentData()
        self.context_record.clear()
        _ui_locale.add_item(self.context_record, _ui_tr('Bitte auswählen …'), None)
        kind = self.context_kind.currentData()
        caption = "title" if kind == "applications" else "display_name"
        for record in self.snapshot.get("choices", {}).get(kind, []) if self.snapshot else []:
            self.context_record.addItem(record[caption], record["id"])
        self.context_record.setCurrentIndex(max(0, self.context_record.findData(previous)))
        self.context_compose.setEnabled(bool(self.context_record.currentData()))

    def compose_context(self):
        identifier = self.context_record.currentData()
        if identifier:
            key = "application_id" if self.context_kind.currentData() == "applications" else "contact_id"
            self.action_requested.emit("compose_context", {key: identifier})

    def open_recent(self, item):
        action, identifier = item.data(Qt.ItemDataRole.UserRole)
        self.action_requested.emit(action, identifier)

    def generate(self):
        record = self.templates.currentData()
        if record:
            self.action_requested.emit("generate", record)

    def display_bulk_groups(self, groups):
        previous = self.bulk_groups.currentData()
        self.bulk_groups.clear()
        for group in groups:
            details = _ui_format('{0} · {1} · {2}/{3} heute', group['name'], group['status'],
                                 group.get('daily_used', 0), group.get('daily_budget', 100))
            _ui_locale.add_item(self.bulk_groups, _ui_format('{0}{1}', details,
                                ' · ' + group['wait_reason'] if group.get('wait_reason') else ''), group)
        if previous:
            for index in range(self.bulk_groups.count()):
                if self.bulk_groups.itemData(index)["id"] == previous["id"]:
                    self.bulk_groups.setCurrentIndex(index)
        self.bulk_panel.setVisible(bool(groups))

    def bulk_action(self, key):
        group = self.bulk_groups.currentData()
        if group:
            self.action_requested.emit(key, group)
