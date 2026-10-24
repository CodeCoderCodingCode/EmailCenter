"""Desktop shell: register pages here as more use cases become available."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
import time

from PySide6.QtCore import QStandardPaths, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QStackedWidget, QToolBar, QVBoxLayout, QWidget,
)

from .controller import WorkspaceController
from .dialogs import FormDialog, GenerateDialog, PreviewDialog, TemplateDialog
from .pages import OverviewPage, RecordPage, button, label
from .template_page import TemplatePage
from .import_page import ImportMappingDialog, ImportPage
from .mail_page import ComposeDialog, MailJobDialog, MailPage, job_actions
from .mail_workflow import PrepareMailDialog
from .mail_template_dialogs import MailTemplateLibrary, MailTemplateEditor, MailTemplatePreview
from .mail_bulk_dialog import BulkMailDialog
from .bulk_source_dialogs import ImportRowsDialog, ManualRowsDialog
from .bulk_delivery_dialog import BulkDeliveryDialog
from .export_dialog import ExportDialog
from .document_bundle_dialog import DocumentBundleDialog
from .project_wizard import ProjectWizard
from .project_settings_dialog import ProjectSettingsDialog
from .backup_dialog import RestoreDialog
from .record_dialogs import RecordDialog, ContactLinksDialog
from .reminder_page import FollowUpPage, ReminderDialog
from .settings_page import SettingsPage
from .workspace_page import WorkspacePage
from .word_replace_page import WordReplacePage
from .email_builder_page import EmailBuilderPage
from .toast import Toast
from .transitions import PageTransition, InteractionFeedback
from .administration_page import AdministrationPage, AdministrationEditor
from ..preferences import Preferences, PreferencesStore
from ..shortcuts import SHORTCUTS, CANVAS_SHORTCUTS
from .theme import apply_theme
from ..appearance import is_dark_theme, paired_theme
from ..branding import logo_path
from ..language import set_language, translate, translate_tree, install_dialog_translation


class MainWindow(QMainWindow):
    def __init__(self, *, controller=None, settings_store=None):
        super().__init__()
        _ui_locale.set_window_title(self, 'EmailCenter')
        self.setWindowIcon(QIcon(str(logo_path())))
        QApplication.instance().setWindowIcon(self.windowIcon())
        self.resize(1250, 820)
        self.setMinimumSize(820, 600)
        self.snapshot = None
        self.settings_store = settings_store or PreferencesStore(
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "preferences.json")
        self.preferences, settings_warning = self.settings_store.load()
        set_language(self.preferences.language)
        install_dialog_translation(QApplication.instance())
        self.dark = is_dark_theme(self.preferences.theme)
        apply_theme(QApplication.instance(), self.dark, self.preferences.accent, theme=self.preferences.theme)
        self._shutdown_ready = False
        self._close_requested = False
        self._generation_dialog = None
        self._preview_dialog = None
        self._pending_template = None
        self._import_mapping_dialog = None
        self._mail_dialog = None
        self._record_dialog = None
        self._project_dialog = None
        self._template_library = None
        self._template_editor = None
        self._template_preview = None
        self._template_render_payload = None
        self._selected_template_version = None
        self._bulk_dialog = None
        self._bulk_source_dialog = None
        self._bulk_delivery_dialog = None
        self._export_dialog = None
        self._source_owner = "bulk"
        self._last_mail_tick = time.monotonic()
        self._mail_gap_pending = False
        self._background_groups, self._bulk_control_pending = [], None
        self._bulk_refresh_pending = False
        self._last_bulk_tick, self._bulk_gap_pending = time.monotonic(), False
        self.controller = controller or WorkspaceController(self)
        self.controller.completed.connect(self.operation_completed)
        self.controller.failed.connect(self.operation_failed)
        self.controller.progress_changed.connect(self.operation_progress)
        self.controller.busy_changed.connect(self.set_busy)
        self.controller.shutdown_finished.connect(self.shutdown_finished)
        self.pages, self.page_order = {}, []
        self._build_toolbar()
        central = QWidget()
        body = QHBoxLayout(central)
        body.setContentsMargins(0, 0, 0, 0)
        sidebar = QWidget()
        sidebar.setFixedWidth(225)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 20, 6, 16)
        self.brand_logo = label("")
        self.brand_logo.setPixmap(QPixmap(str(logo_path())).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        self.brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(self.brand_logo)
        sidebar_layout.addWidget(label(_ui_tr('EmailCenter'), 'brand'))
        sidebar_layout.addWidget(label(_ui_tr('Bewerbungen & Dokumente'), 'muted'))
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.currentRowChanged.connect(self.show_page)
        sidebar_layout.addWidget(self.navigation, 1)
        self.project_label = label(_ui_tr('Kein Projekt geöffnet'), 'muted')
        sidebar_layout.addWidget(self.project_label)
        self.stack = QStackedWidget()
        self.page_transition = PageTransition(self.stack)
        self.page_transition.configure(self.preferences)
        self.interaction_feedback = InteractionFeedback(QApplication.instance(), self.preferences, self)
        body.addWidget(sidebar)
        body.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        overview = OverviewPage()
        overview.update_snapshot(None)
        overview.action_requested.connect(self.overview_action)
        self.register_page("overview", "Übersicht / Projekte", overview)
        workspace = WorkspacePage()
        workspace.action_requested.connect(self.workspace_action)
        workspace.mail_workflow.load_requested.connect(self.controller.submit)
        workspace.mail_workflow.action_requested.connect(self.workspace_mail_action)
        workspace.mode_requested.connect(lambda mode: self.controller.submit("set_workspace_mode", {"mode": mode}))
        self.register_page("workspace", "Arbeitsbereich", workspace)
        definitions = (
            ("applications", "Bewerbungen", "Bewerbungen erfassen und ihren Fortschritt verfolgen.",
             [("Bewerbung", "title"), ("Unternehmen", "company_name"), ("Status", "status_label"), ("Nachfassen", "next_follow_up_at")],
             [("Neue Bewerbung", "new_application", False), ("Bearbeiten", "edit", True), ("Status ändern", "status", True), ("Kontakte zuordnen", "links", True), ("E-Mail schreiben", "compose_context", True)]),
            ("companies", "Unternehmen", "Deine Unternehmen und Ansprechpartner zentral verwalten.",
             [("Unternehmen", "name"), ("Branche", "industry"), ("Website", "website")],
             [("Unternehmen anlegen", "new_company", False), ("Bearbeiten", "edit", True), ("Kontakte zuordnen", "links", True)]),
            ("contacts", "Kontakte", "Kontaktdaten für deine Bewerbungen erfassen.",
             [("Name", "display_name"), ("E-Mail", "email"), ("Telefon", "phone"), ("Position", "position")],
             [("Kontakt anlegen", "new_contact", False), ("Bearbeiten", "edit", True), ("E-Mail schreiben", "compose_context", True)]),
            ("applicants", "Bewerberprofile", "Deine Profile für Bewerbungen und Dokumente verwalten.",
             [("Name", "display_name"), ("E-Mail", "email"), ("Telefon", "phone")],
             [("Profil anlegen", "new_applicant", False), ("Bearbeiten", "edit", True)]),
            ("jobs", "Stellen", "Stellen erfassen und beim Anlegen oder Bearbeiten einer Bewerbung zuordnen.",
             [("Stelle", "title"), ("Unternehmen", "company_name"), ("Ort", "location"), ("Referenz", "reference_number"), ("Frist", "deadline")],
             [("Stelle anlegen", "new_job", False), ("Bearbeiten", "edit", True)]),
            ("templates", "Vorlagen", "DOCX-Vorlagen importieren, Felder zuordnen und konkrete Versionen verwenden.",
             [("Vorlage", "template_name"), ("Version", "version_number"), ("Importiert", "created_at")],
             [("Importieren", "import", False), ("Neue Version", "version", True), ("Verwenden", "generate", True)]),
            ("documents", "Dokumente", "Erzeugte Dokumente öffnen und als PDF bereitstellen.",
             [("Datei", "original_filename"), ("Format", "format"), ("Bewerbung", "application_title"), ("Erstellt", "created_at")],
             [("Öffnen", "open_document", True), ("PDF erzeugen", "pdf", True), ("Dokumentpaket exportieren", "document_bundle", False)]),
        )
        for entity, title, description, columns, actions in definitions:
            if entity in ("companies", "contacts", "applications", "applicants", "jobs"):
                actions = [*actions, ("CSV / Excel exportieren", "export", False)]
            page = TemplatePage() if entity == "templates" else RecordPage(entity, title, description, columns, actions)
            page.load_requested.connect(self.controller.submit)
            page.action_requested.connect(self.record_action)
            self.register_page(entity, title, page)
        followups = FollowUpPage()
        followups.load_requested.connect(self.controller.submit)
        followups.action_requested.connect(self.followup_action)
        self.register_page("followups", "Nachfassen", followups)
        import_page = ImportPage()
        import_page.operation_requested.connect(self.controller.submit)
        self.register_page("import", "Datenimport", import_page)
        mail_page = MailPage()
        mail_page.operation_requested.connect(self.controller.submit)
        mail_page.compose_requested.connect(self.compose_mail)
        mail_page.review_requested.connect(self.review_mail)
        mail_page.scheduler.toggled.connect(self.scheduler_toggled)
        workspace.mail_workflow.scheduler.toggled.connect(mail_page.scheduler.setChecked)
        mail_page.scheduler.toggled.connect(workspace.mail_workflow.scheduler.setChecked)
        self.register_page("mail", "E-Mail", mail_page)
        word_page = WordReplacePage(self.preferences)
        word_page.operation_requested.connect(self.controller.submit)
        word_page.source_requested.connect(self.open_word_replace_source)
        word_page.cancel_requested.connect(self.controller.cancel_current)
        word_page.settings_requested.connect(self.open_word_replace_settings)
        word_page.path_requested.connect(self.open_local_path)
        self.register_page("word_replace", "Word Replace", word_page)
        builder_page = EmailBuilderPage(self.preferences)
        builder_page.operation_requested.connect(self.controller.submit)
        builder_page.source_requested.connect(self.open_builder_source)
        builder_page.cancel_requested.connect(self.controller.cancel_current)
        builder_page.delivery_requested.connect(lambda identifier: self.controller.submit("mail_bulk_delivery_details", {"batch_id": identifier}))
        builder_page.settings_requested.connect(self.open_builder_settings)
        builder_page.checkpoint_requested.connect(self.submit_builder_checkpoint)
        builder_page.asset_autoload_requested.connect(self.submit_builder_asset_autoload)
        self.controller.background_completed.connect(lambda action, value: builder_page.checkpoint_saved(value) if action == "builder_workspace_save" else None)
        self.controller.background_failed.connect(lambda action, message: builder_page.checkpoint_failed(message) if action == "builder_workspace_save" else None)
        self.controller.background_completed.connect(lambda action, value: builder_page.display_auto_asset_preview(value) if action == "builder_asset_preview" else None)
        self.controller.background_failed.connect(lambda action, message: builder_page.display_auto_asset_preview(error=message) if action == "builder_asset_preview" else None)
        self.controller.checkpoint_provider = self.builder_checkpoint_before_operation
        self.controller.shutdown_blocked.connect(self.shutdown_checkpoint_failed)
        self.register_page("builder", "E-Mail-Builder", builder_page)
        builder_page.panel_preferences_requested.connect(lambda values: self.save_preferences(values, preserve_edits=True))
        builder_page.apply_panel_layout()
        administration_page = AdministrationPage()
        administration_page.operation_requested.connect(self.controller.submit)
        administration_page.editor_requested.connect(lambda section,row:self.open_record_dialog(AdministrationEditor(section,row,self)))
        self.register_page('administration','Verwaltung',administration_page)
        settings_page = SettingsPage(self.preferences, settings_warning)
        settings_page.save_requested.connect(self.save_preferences)
        settings_page.reload_requested.connect(self.reload_preferences)
        settings_page.diagnostic_requested.connect(self.export_diagnostic)
        self.register_page("settings", "Einstellungen", settings_page)
        followups.timezone_id = self.preferences.timezone_id
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.pause_import = button(_ui_tr('Import anhalten'), self.pause_current_import)
        self.pause_import.hide()
        self.statusBar().addPermanentWidget(self.pause_import)
        self.cancel_work = button(_ui_tr('Vorgang abbrechen'), self.controller.cancel_current)
        self.cancel_work.hide()
        self.statusBar().addPermanentWidget(self.cancel_work)
        self.toast = Toast(self)
        self.toast.configure(self.preferences)
        for page in self.pages.values():
            if isinstance(page, RecordPage):
                page.apply_settings(self.preferences)
        self.navigation.setCurrentRow(0)
        self.update_actions()
        self.statusBar().showMessage(_ui_tr('Bereit – Projekt erstellen oder öffnen.'))
        if settings_warning:
            self.statusBar().showMessage(_ui_tr('Einstellungen prüfen – siehe Einstellungen.'))
        self.mail_timer = QTimer(self)
        self.mail_timer.setInterval(15000)
        self.mail_timer.timeout.connect(self.mail_tick)
        self.mail_timer.start()
        self.bulk_timer = QTimer(self)
        self.bulk_timer.setInterval(1000)
        self.bulk_timer.timeout.connect(self.bulk_background_tick)
        self.bulk_timer.start()
        self.followup_timer = QTimer(self)
        self.followup_timer.setInterval(60000)
        self.followup_timer.timeout.connect(self.followup_tick)
        self.followup_timer.start()

    def register_page(self, key, title, page):
        """Add a page without changing existing page implementations."""
        if key in self.pages:
            raise ValueError(f"Duplicate page key: {key}")
        self.pages[key] = page
        self.page_order.append(key)
        self.stack.addWidget(page)
        _ui_locale.add_item(self.navigation, translate(title))
        self.navigation.item(self.navigation.count() - 1).setData(Qt.ItemDataRole.UserRole, title)

    def open_guide(self):
        from .help_viewer import HelpDialog, context_anchor
        key = self.page_order[self.stack.currentIndex()] if self.stack.currentIndex() >= 0 else 'first-steps'
        anchor = context_anchor(key, self.current_page())
        if not getattr(self, '_guide_dialog', None):
            self._guide_dialog = HelpDialog(anchor, self)
        self._guide_dialog.navigate(anchor)

    def _build_toolbar(self):
        toolbar = QToolBar(str(_ui_tr('Projekt')))
        _ui_locale.set_window_title(toolbar, _ui_tr('Projekt'))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.actions = {}
        for key, caption, callback in (
            ("new", "Neues Projekt", self.create_project), ("open", "Öffnen", self.open_project),
            ("close", "Schließen", lambda: self.controller.submit("close_project")),
            ("backup", "Backup", lambda: self.controller.submit("backup", {"directory": self.preferences.backup_directory, "retention": self.preferences.backup_retention})),
            ("folder", "Projektordner", self.open_project_folder),
            ("refresh", "Aktualisieren", lambda: self.controller.submit("snapshot")),
            ("theme", "Dunkles Design", self.toggle_theme),
            ("settings", "Einstellungen", lambda: self.navigate("settings")),
            ("help", "Hilfe / Guide", self.open_guide),
            ('keyboard_help', 'Tastaturhilfe', self.shortcut_help),
        ):
            action = QAction(translate(caption), self)
            action.setProperty("languageSource", caption)
            action.triggered.connect(callback)
            self.actions[key] = action
            toolbar.addAction(action)
        for key in ("workspace", "word_replace", "export", "search", "save"):
            action = QAction(SHORTCUTS[key][0], self)
            action.triggered.connect(lambda checked=False, key=key: self.trigger_hotkey(key))
            self.addAction(action)
            self.actions[key] = action
        restore = QAction(translate("Backup wiederherstellen"), self)
        restore.setProperty("languageSource", "Backup wiederherstellen")
        restore.triggered.connect(self.restore_backup)
        self.actions["restore"] = restore
        toolbar.addAction(restore)
        self.apply_shortcuts()
        _ui_locale.set_text(self.actions["theme"], translate("Helles Design" if self.dark else "Dunkles Design"))

    def apply_shortcuts(self):
        for key, (caption, _) in SHORTCUTS.items():
            self.actions[key].setShortcut(self.preferences.shortcuts[key])
            _ui_locale.set_tooltip(self.actions[key], _ui_format('{0} · {1}', _ui_tr(caption), self.preferences.shortcuts[key] or _ui_tr('deaktiviert')))
        for name in ("_record_dialog", "_mail_dialog", "_template_editor", "_template_library", "_bulk_dialog"):
            dialog = getattr(self, name, None)
            if dialog:
                self.install_dialog_shortcuts(dialog)

    def install_dialog_shortcuts(self, dialog):
        if not hasattr(dialog, "_emailcenter_shortcuts"):
            dialog._emailcenter_shortcuts = {}
            for key in ("save", "search", "help"):
                action = QAction(SHORTCUTS[key][0], dialog)
                action.triggered.connect(lambda checked=False, key=key: self.trigger_hotkey(key))
                dialog.addAction(action)
                dialog._emailcenter_shortcuts[key] = action
        for key, action in dialog._emailcenter_shortcuts.items():
            action.setShortcut(self.preferences.shortcuts[key])

    def trigger_hotkey(self, key):
        if self.controller.busy or self.controller.stopping:
            return
        modal = QApplication.activeModalWidget()
        target = modal or self.current_page()
        if key == "help":
            self.open_guide()
        elif key == "search":
            search = getattr(target, "search", None)
            if isinstance(search, QLineEdit) and search.isEnabled():
                search.setFocus()
                search.selectAll()
        elif key == "save":
            if isinstance(target, (RecordDialog, ComposeDialog, MailTemplateEditor)):
                save = target.buttons.button(QDialogButtonBox.StandardButton.Save)
                if save and save.isEnabled():
                    save.click()
            elif isinstance(target, (SettingsPage, ContactLinksDialog)) and target.save_button.isEnabled():
                target.save_button.click()
            elif isinstance(target, WordReplacePage) and target.create_button.isEnabled():
                target.create_button.click()
            elif isinstance(target, EmailBuilderPage) and target.save_button.isEnabled():
                target.save_button.click()
        elif not modal and self.snapshot:
            if key in ("workspace", "word_replace"):
                self.navigate(key)
            elif key == "export":
                self.open_export()

    def shortcut_help(self):
        text = "\n".join(str(_ui_format('{0}: {1}', _ui_tr(caption), self.preferences.shortcuts[key] or _ui_tr('deaktiviert'))) for key, (caption, _) in SHORTCUTS.items())
        text += str(_ui_tr('\n\nBuilder-Zeichenfläche (nur mit Canvas-Fokus):\n')) + "\n".join(str(_ui_format('{0}: {1}', _ui_tr(caption), self.preferences.canvas_shortcuts[key] or _ui_tr('deaktiviert'))) for key, (caption, _) in CANVAS_SHORTCUTS.items())
        text += str(_ui_tr('\n\nÄndern: Einstellungen → Hotkeys.\nSpeichern wirkt auf das aktive Formular. Versand und Freigabe werden über ihre eigenen Schaltflächen bestätigt.'))
        QMessageBox.information(QApplication.activeModalWidget() or self, _ui_tr('Tastenkürzel'), text)

    def current_page(self):
        index = self.navigation.currentRow()
        return self.pages[self.page_order[index]] if index >= 0 else None

    def show_page(self, index):
        if index < 0 or index >= len(self.page_order):
            return
        self.stack.setCurrentIndex(index)
        self.page_transition.play(self.preferences.reduced_motion)
        page = self.current_page()
        if isinstance(page, RecordPage) and self.snapshot:
            page.request_load()
        elif isinstance(page, ImportPage) and self.snapshot:
            page.request_history()
        elif isinstance(page, MailPage) and self.snapshot:
            page.request_load()
        elif isinstance(page, WorkspacePage) and self.snapshot:
            page.mail_workflow.request_load()
        elif isinstance(page, WordReplacePage) and self.snapshot:
            page.request_load()
        elif isinstance(page, EmailBuilderPage) and self.snapshot:
            page.request_load()
        elif isinstance(page, AdministrationPage) and self.snapshot:
            page.request_load()
        self.update_actions()

    def navigate(self, key):
        self.navigation.setCurrentRow(self.page_order.index(key))

    def overview_action(self, action):
        if action == "new":
            self.create_project()
        elif action == "open":
            self.open_project()
        elif action == "profile":
            self.create_record("applicants")
        elif action == "followups":
            self.navigate("followups")

    def workspace_action(self, action, value):
        if action in ("bulk_pause", "bulk_cancel") and self.snapshot:
            if action == "bulk_cancel" and QMessageBox.question(self, _ui_tr('Gruppe abbrechen'), _ui_tr('Offene Aufträge dieser Gruppe stornieren?')) != QMessageBox.StandardButton.Yes:
                return
            operation = "mail_bulk_delivery_" + ("pause" if action == "bulk_pause" else "cancel")
            payload = {"dispatch_id": value["id"]}
            if self.controller.busy and self.controller.current_action == "mail_bulk_background":
                self._bulk_control_pending = (operation, payload)
                self.statusBar().showMessage(_ui_tr('Steuerung vorgemerkt; laufenden Einzelauftrag abschließen.'))
            elif not self.controller.busy:
                self.controller.submit(operation, payload)
            return
        if not self.snapshot or self.controller.busy:
            return
        entities = {"profile": "applicants", "company": "companies", "application": "applications", "contact": "contacts"}
        if action in entities:
            self.create_record(entities[action])
        elif action == "compose":
            self.controller.submit("mail_compose_details")
        elif action == "bulk":
            self.workspace_mail_action("bulk", None)
        elif action == "compose_context":
            self.controller.submit("mail_compose_details", value)
        elif action == "mail_templates":
            self.open_template_library()
        elif action == "export":
            self.open_export()
        elif action == "project_settings":
            self.controller.submit("project_setup_details", {"purpose": "edit"})
        elif action == "bulk_open":
            self.controller.submit("mail_bulk_delivery_details", {"batch_id": value["batch_id"]})
        elif action == "word_replace":
            self.navigate("word_replace")
        elif action == "builder":
            self.navigate("builder")
        elif action == "reminder":
            self.controller.submit("reminder_details")
        elif action == "edit_application":
            self.controller.submit("record_details", {"entity": "applications", "record_id": value})
        elif action == "job":
            self.controller.submit("mail_job_details", {"job_id": value})
        elif action in ("generate", "import_template"):
            self.record_action("generate" if action == "generate" else "import", value)
        elif action in ("followups", "mail", "templates", "documents"):
            self.navigate(action)

    def workspace_mail_action(self, action, record):
        if not self.snapshot or self.controller.busy or self.controller.stopping or self._mail_dialog:
            return
        if action == "new":
            self.controller.submit("mail_compose_details")
        elif action == "templates":
            self.open_template_library()
        elif action == "bulk":
            self.controller.submit("mail_bulk_details")
        elif action == "connect":
            self.pages['mail'].connect_gmail()
        elif action == "edit":
            self.controller.submit("mail_compose_details", {"draft_id": record["id"]})
        elif action == "prepare":
            data = self.pages["workspace"].mail_workflow.data
            self.open_mail_dialog(PrepareMailDialog(record, self.preferences.mail_timezone_id, self,
                accounts=data["accounts"] if data else ()))
        elif action == "review":
            self.controller.submit("mail_job_details", {"job_id": record["id"]})
        elif action in ("send", "reconcile", "cancel") and job_actions(record)[action]:
            if action == "send":
                message = _ui_format('Diese freigegebene Nachricht jetzt über Gmail senden?\n\n{0}\nAn: {1}', record['subject_snapshot'], '; '.join(record['recipients']['to']))
                if QMessageBox.question(self, _ui_tr('Freigegebenen Auftrag senden'), message) != QMessageBox.StandardButton.Yes:
                    return
            elif action == "cancel" and QMessageBox.question(self, _ui_tr('Auftrag stornieren'), _ui_tr('Diesen Versandauftrag stornieren?')) != QMessageBox.StandardButton.Yes:
                return
            payload = {"job_id": record["id"]}
            if action == "send":
                payload["send_now"] = True
            self.controller.submit("mail_" + action, payload)

    def create_project(self):
        if self.controller.busy or self.controller.stopping or self._project_dialog:
            return
        if self.snapshot:
            self.controller.submit("project_setup_details", {"purpose": "create"})
            return
        self.show_project_wizard()

    def show_project_wizard(self, choices=None):
        dialog = ProjectWizard(self, choices=choices)
        dialog.fields["workspace_mode"].setCurrentIndex(dialog.fields["workspace_mode"].findData(self.preferences.workspace_mode))
        dialog.account_email.setCurrentText(self.preferences.mail_account_email)
        dialog.body_format.setCurrentIndex(dialog.body_format.findData(self.preferences.mail_body_format))
        self._project_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.finished.connect(lambda result: setattr(self, "_project_dialog", None))
        dialog.open()

    def open_project(self):
        path = QFileDialog.getExistingDirectory(self, _ui_tr('EmailCenter-Projektordner öffnen'))
        if path:
            self.controller.submit("open_project", {"path": path})

    def export_diagnostic(self):
        if self.controller.busy:
            return
        path = QFileDialog.getExistingDirectory(self, _ui_tr('Lokalen Diagnosebericht speichern'))
        if path:
            self.controller.submit("diagnostic_export", {"directory": path, "libreoffice_path": self.preferences.libreoffice_path})

    def restore_backup(self):
        if self.controller.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Projektbackup prüfen'), self.preferences.backup_directory, _ui_tr('Projektbackup (*.zip)'))
        if path:
            self.controller.submit("backup_inspect", {"path": path})

    def open_project_folder(self):
        if self.snapshot:
            self.open_local_path(self.snapshot["path"])

    def open_local_path(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, _ui_tr('Datei öffnen'), _ui_tr('Für diese Datei konnte kein Programm geöffnet werden.'))

    def toggle_theme(self):
        values = {**self.preferences.values(), "theme": paired_theme(self.preferences.theme)}
        self.save_preferences(values, preserve_edits=True)

    def save_preferences(self, values, *, preserve_edits=False):
        try:
            preferences = Preferences.validate(values)
            self.settings_store.save(preferences)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, _ui_tr('Einstellungen nicht gespeichert'), str(error))
            return
        self.apply_preferences(preferences, preserve_edits=preserve_edits)
        self.statusBar().showMessage(_ui_tr('Einstellungen gespeichert.'))
        self.toast.notify(_ui_tr('Einstellungen'), _ui_tr('Änderungen gespeichert und angewendet.'))

    def reload_preferences(self):
        preferences, warning = self.settings_store.load()
        self.apply_preferences(preferences, warning=warning)
        self.statusBar().showMessage(_ui_tr('Einstellungen prüfen.') if warning else _ui_tr('Einstellungen geladen.'))

    def apply_preferences(self, preferences, *, preserve_edits=False, warning=None):
        self.preferences = preferences
        set_language(preferences.language)
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            _ui_locale.set_text(item, translate(item.data(Qt.ItemDataRole.UserRole)))
        for action in self.actions.values():
            source = action.property("languageSource") or action.text()
            action.setProperty("languageSource", source)
            _ui_locale.set_text(action, translate(source))
        translate_tree(self)
        self.dark = is_dark_theme(preferences.theme)
        self.page_transition.configure(preferences)
        self.interaction_feedback.configure(preferences)
        apply_theme(QApplication.instance(), self.dark, preferences.accent, theme=preferences.theme)
        _ui_locale.set_text(self.actions["theme"], translate("Helles Design" if self.dark else "Dunkles Design"))
        self.pages["settings"].accept_preferences(preferences, preserve_edits=preserve_edits, warning=warning)
        self.pages["followups"].timezone_id = preferences.timezone_id
        self.pages["word_replace"].apply_settings(preferences)
        self.pages["builder"].apply_settings(preferences)
        self.pages['workspace'].guided_panel.setVisible(bool(self.snapshot) and preferences.guided_workspace)
        self.toast.configure(preferences)
        for page in self.pages.values():
            if isinstance(page, RecordPage):
                page.apply_settings(preferences)
        if self.snapshot and isinstance(self.current_page(), RecordPage):
            self.current_page().request_load()
        self.page_transition.play(preferences.reduced_motion)
        self.apply_shortcuts()
        if self.snapshot and isinstance(self.current_page(), FollowUpPage):
            self.current_page().request_load()

    def create_record(self, entity):
        self.controller.submit("record_details", {"entity": entity})

    def open_record_dialog(self, dialog):
        self._record_dialog = dialog
        self.install_dialog_shortcuts(dialog)
        dialog.operation_requested.connect(self.controller.submit)
        if hasattr(dialog, "operation_cancel_requested"):
            dialog.operation_cancel_requested.connect(self.controller.cancel_current)
            dialog.setProperty("cancelWired", True)
        dialog.finished.connect(lambda result: setattr(self, "_record_dialog", None))
        dialog.setModal(True)
        dialog.open()

    def record_action(self, action, record):
        if action == 'builtin_templates':
            from ..builtin_templates import DOCUMENTS, MAILS
            from PySide6.QtWidgets import QInputDialog
            choices = {title: ('document', key) for key, (title, _) in DOCUMENTS.items()}
            choices.update({value[0]: ('email', key) for key, value in MAILS.items()})
            title, accepted = QInputDialog.getItem(self, str(_ui_tr('Mitgelieferte Vorlagen')), str(_ui_tr('Vorlage auswählen')), list(choices), 0, False)
            if accepted:
                kind, key = choices[title]
                self.controller.submit('builtin_template_install', {'kind': kind, 'key': key})
        elif action == "document_bundle":
            page = self.pages["documents"]
            selected = [page.rows[index.row()]["id"] for index in page.table.selectionModel().selectedRows()]
            self.open_document_bundle(search=page.search.text(), selected_ids=selected)
        elif action == "new_mail_template":
            self.open_template_editor()
        elif action == "edit_mail_template" and record:
            self._selected_template_version = record["id"]
            self.controller.submit("mail_template_details", {"template_id": record["template_id"]})
        elif action == "duplicate_template" and record:
            operation = "mail_template_duplicate" if record["template_type"] == "email" else "document_template_duplicate"
            self.controller.submit(operation, {"version_id": record["id"]})
        elif action == "export":
            page = self.current_page()
            selected = [page.rows[index.row()]["id"] for index in page.table.selectionModel().selectedRows()]
            self.open_export(entity=page.entity, search=page.search.text(), selected_ids=selected)
        elif action in ("new_company", "new_contact", "new_application", "new_applicant", "new_job"):
            self.create_record({"new_company": "companies", "new_contact": "contacts", "new_application": "applications", "new_applicant": "applicants", "new_job": "jobs"}[action])
        elif action == "compose_context" and record:
            key = "application_id" if self.current_page().entity == "applications" else "contact_id"
            self.controller.submit("mail_compose_details", {key: record["id"]})
        elif action in ("edit", "links") and record:
            self.controller.submit("record_details" if action == "edit" else "record_links",
                                   {"entity": self.current_page().entity, "record_id": record["id"]})
        elif action == "status" and record:
            statuses = self.snapshot["statuses"]
            dialog = FormDialog(_ui_tr('Bewerbungsstatus'), [('status_code', 'Neuer Status', [(r['label'], r['code']) for r in statuses])], parent=self)
            combo = dialog.fields["status_code"]
            combo.setCurrentIndex(combo.findData(record["status_code"]))
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.controller.submit("change_status", {"application_id": record["id"], **dialog.values()})
        elif action in ("import", "version"):
            path, _ = QFileDialog.getOpenFileName(self, _ui_tr('DOCX-Vorlage wählen'), '', _ui_tr('Word-Dokumente (*.docx)'))
            if path:
                self._pending_template = record if action == "version" else None
                self.controller.submit("analyze_template", {"source_path": path})
        elif action == "generate" and record:
            dialog = GenerateDialog(record, self.snapshot, self)
            self._generation_dialog = dialog
            dialog.operation_requested.connect(self.controller.submit)
            dialog.finished.connect(lambda: setattr(self, "_generation_dialog", None))
            dialog.operation_cancel_requested.connect(self.controller.cancel_current)
            dialog.setModal(True)
            dialog.open()
        elif action == "pdf" and record:
            self.controller.submit("create_pdf", {"document_id": record["id"]})
        elif action == "open_document" and record:
            self.controller.submit("document_path", {"document_id": record["id"]})

    def set_busy(self, busy):
        import_page = self.pages.get("import")
        locked = busy or bool(import_page and import_page.auto_running)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0)
        self.cancel_work.setVisible(busy and self.controller.current_action in ("preview_document", "generate_document", "create_pdf"))
        self.navigation.setEnabled(not locked)
        self.stack.setEnabled(not locked)
        if busy and self.controller.current_action == "mail_bulk_background":
            self.stack.setEnabled(True)
            self.navigation.setEnabled(True)
        if self._generation_dialog:
            self._generation_dialog.set_busy(busy)
        if self._import_mapping_dialog:
            self._import_mapping_dialog.set_busy(busy)
        if self._mail_dialog:
            self._mail_dialog.set_busy(busy)
        if self._record_dialog:
            self._record_dialog.set_busy(busy)
        if self._project_dialog:
            self._project_dialog.set_busy(busy)
        for dialog in (self._template_library, self._template_editor, self._template_preview, self._bulk_dialog, self._bulk_source_dialog):
            if dialog:
                if hasattr(dialog, "operation_cancel_requested") and not dialog.property("cancelWired"):
                    dialog.operation_cancel_requested.connect(self.controller.cancel_current)
                    dialog.setProperty("cancelWired", True)
                dialog.set_busy(busy)
        if self._bulk_delivery_dialog:
            # Its own pause/cancel controls remain usable; disabling its parent would also disable them.
            if self._bulk_dialog:
                self._bulk_dialog.setEnabled(True)
                self._bulk_dialog.busy = busy
            self._bulk_delivery_dialog.set_busy(busy)
        if self._export_dialog:
            if self._bulk_dialog:
                self._bulk_dialog.setEnabled(True)
                self._bulk_dialog.busy = busy
            self._export_dialog.set_busy(busy)
        word_page = self.pages.get("word_replace")
        if word_page:
            word_page.set_busy(busy)
            if busy and self.current_page() is word_page and (self.controller.current_action or "").startswith("word_replace_"):
                self.stack.setEnabled(True)
        builder_page = self.pages.get("builder")
        if builder_page:
            builder_page.set_busy(busy)
            if busy and self.current_page() is builder_page and (self.controller.current_action or "").startswith("builder_"):
                self.stack.setEnabled(True)
        self.pause_import.setVisible(bool(import_page and import_page.auto_running))
        self.update_actions()
        if busy:
            self.statusBar().showMessage(_ui_tr('Vorgang läuft …'))
        elif not self._close_requested:
            self.statusBar().showMessage(_ui_tr('Bereit'))

    def update_actions(self):
        import_page = self.pages.get("import")
        idle = not self.controller.busy and not self.controller.stopping and not (import_page and import_page.auto_running)
        for key, action in self.actions.items():
            action.setEnabled(idle and (key in ("new", "open", "theme", "settings", "help", "save", "restore") or bool(self.snapshot)))
        for key, page in self.pages.items():
            if isinstance(page, (RecordPage, ImportPage, MailPage, WorkspacePage, WordReplacePage, EmailBuilderPage, AdministrationPage)):
                page.setEnabled(bool(self.snapshot))
                self.navigation.item(self.page_order.index(key)).setHidden(not bool(self.snapshot))

    def operation_progress(self, action, value):
        if self.controller.current_action == action:
            self.progress.setRange(0, value["total"])
            self.progress.setValue(value["current"])
            self.statusBar().showMessage(f"{value['message']} · {value['current']}/{value['total']}")

    def apply_snapshot(self, snapshot):
        self.snapshot = snapshot
        self._background_groups = snapshot.get("bulk_groups", []) if snapshot else []
        self.pages["overview"].update_snapshot(snapshot)
        self.pages["workspace"].update_snapshot(snapshot)
        _ui_locale.set_text(self.project_label, snapshot['name'] if snapshot else _ui_tr('Kein Projekt geöffnet'))
        self.project_label.setToolTip(snapshot["path"] if snapshot else "")
        _ui_locale.set_window_title(self, f"{snapshot['name']} — EmailCenter" if snapshot else 'EmailCenter')
        due = snapshot["counts"]["followups"] if snapshot else 0
        _ui_locale.set_text(self.navigation.item(self.page_order.index('followups')), _ui_format('{0} ({1})', translate('Nachfassen'), due) if due else translate('Nachfassen'))
        self.update_actions()

    def operation_completed(self, action, value):
        if self._close_requested:
            # The committed operation finishes before checkpointing and closing.
            # Suppress UI follow-up requests and scheduler races during shutdown.
            self.controller.shutdown()
            return
        if action == 'administration_export_path':
            self.open_local_path(value['path'])
            return
        if action == 'administration_list':
            self.pages['administration'].display(value)
            return
        if action.startswith('administration_'):
            if self._record_dialog and isinstance(self._record_dialog,AdministrationEditor):
                self._record_dialog.accept()
            blocked = action == 'administration_cleanup' and value.get('status') == 'Blocked' or isinstance(value,dict) and any(item['status']=='Blocked' for item in value.get('cleanup',[]))
            self.toast.notify(_ui_tr('Verwaltung'),(_ui_tr('Gespeichert. Dateibereinigung noch offen; in der Verwaltung erneut versuchen.') if blocked else _ui_tr('Änderung gespeichert.')))
            self.controller.submit('snapshot')
            return
        if action == "project_setup_details":
            if value.get("purpose") == "create":
                self.show_project_wizard(value)
            else:
                self.open_record_dialog(ProjectSettingsDialog(value, self))
            return
        if action == "project_setup_save":
            if isinstance(self._record_dialog, ProjectSettingsDialog):
                self._record_dialog.accept()
            self.apply_snapshot(value)
            self.toast.notify(_ui_tr('Projektvorgaben'), _ui_tr('Gespeichert; neue Vorgänge verwenden die Vorgaben.'))
            return
        self.statusBar().showMessage(translate("Bereit"))
        if action in ("create_project", "open_project", "snapshot", "set_workspace_mode"):
            if action == "create_project" and self._project_dialog:
                self._project_dialog.creation_completed()
            if action in ("create_project", "open_project"):
                self.close_template_dialogs()
                self.toast.dismiss()
                self.pages["import"].reset()
                self.pages["mail"].reset()
                self.pages["followups"].reset()
                self.pages["workspace"].mail_workflow.reset()
                self.pages["word_replace"].reset(value["path"])
                self.pages["builder"].reset(value["path"])
                self._mail_gap_pending = False
                self._last_mail_tick = time.monotonic()
            self.apply_snapshot(value)
            if action in ("create_project", "open_project"):
                self.navigate(self.preferences.start_page)
                self.toast.notify(_ui_tr('Projekt bereit'), _ui_format('{0} · Arbeitsbereich geöffnet.', value['name']))
            page = self.current_page()
            if isinstance(page, RecordPage):
                if action != "snapshot":
                    page.offset = 0
                page.request_load()
            elif isinstance(page, ImportPage):
                if page.run_id:
                    page.request_rows()
                else:
                    page.request_history()
            elif isinstance(page, MailPage):
                page.request_load()
            elif isinstance(page, WorkspacePage):
                page.mail_workflow.request_load()
            elif isinstance(page, AdministrationPage):
                page.request_load()
        elif action == "close_project":
            self.close_template_dialogs()
            self.toast.dismiss()
            self.apply_snapshot(None)
            self.navigate("overview")
            self.pages["import"].reset()
            self.pages["mail"].reset()
            self.pages["followups"].reset()
            self.pages["workspace"].mail_workflow.reset()
            self.pages["word_replace"].reset()
            self.pages["builder"].reset()
            for page in self.pages.values():
                if isinstance(page, RecordPage):
                    page.offset = 0
                    page.display({"rows": [], "offset": 0, "total": 0})
        elif action == "list":
            self.pages[value["entity"]].display(value)
        elif action == "followup_list":
            self.pages["followups"].display(value)
            self.apply_followup_summary(value["summary"])
        elif action == "followup_summary":
            self.apply_followup_summary(value)
        elif action == "reminder_details":
            self.open_record_dialog(ReminderDialog(value, self, default_timezone=self.preferences.timezone_id))
        elif action in ("reminder_save", "reminder_finish"):
            if action == "reminder_save" and isinstance(self._record_dialog, ReminderDialog):
                self._record_dialog.accept()
            self.controller.submit("snapshot")
            self.toast.notify(_ui_tr('Erinnerung'), (_ui_tr('Gespeichert.') if action == "reminder_save" else _ui_tr('Status aktualisiert.')))
        elif action == "record_details":
            self.open_record_dialog(RecordDialog(value, self))
        elif action in ("record_links", "save_record_link"):
            if isinstance(self._record_dialog, ContactLinksDialog):
                self._record_dialog.populate(value)
            else:
                self.open_record_dialog(ContactLinksDialog(value, self))
        elif action == "analyze_template":
            record = self._pending_template
            self._pending_template = None
            dialog = TemplateDialog(value["source_path"], value["placeholders"], record=record, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                payload = {"source_path": value["source_path"], **dialog.values()}
                if record:
                    payload["template_id"] = record["template_id"]
                self.controller.submit("import_template", payload)
        elif action == "document_values" and self._generation_dialog:
            self._generation_dialog.populate(value["values"])
        elif action == "preview_document":
            self.show_preview(value, temporary=True)
        elif action == "document_path":
            if value["format"] == "pdf":
                self.show_preview({"pdf_path": value["path"], "pdf_bytes": value["pdf_bytes"]}, temporary=False)
            else:
                self.open_local_path(value["path"])
        elif action == "diagnostic_export":
            self.toast.notify(_ui_tr('Diagnose gespeichert'), _ui_format('Lokaler Bericht: {0}', value))
        elif action == "backup_inspect":
            self.open_record_dialog(RestoreDialog(value, self))
        elif action == "backup_restore":
            if self._record_dialog:
                self._record_dialog.accept()
            self.toast.notify(_ui_tr('Projekt wiederhergestellt'), _ui_format('Geprüftes Projekt: {0} · jetzt über Öffnen auswählen.', value))
        elif action == "backup":
            self.toast.notify(_ui_tr('Backup erstellt'), _ui_format('Geprüftes Projektarchiv gespeichert:\n{0}', value))
        elif action in ("inspect_import", "inspect_builder_source"):
            if self._import_mapping_dialog:
                self._import_mapping_dialog.update_inspection(value)
            else:
                dialog = ImportMappingDialog(value, self, source_only=action == 'inspect_builder_source')
                self._import_mapping_dialog = dialog
                dialog.operation_requested.connect(self.controller.submit)
                dialog.finished.connect(lambda result: setattr(self, "_import_mapping_dialog", None))
                dialog.setModal(True)
                dialog.open()
        elif action == 'prepare_builder_source':
            if self._import_mapping_dialog:
                self._import_mapping_dialog.accept()
            self.pages['builder'].data['runs'] = value['runs']
            self.open_builder_source('import')
            if self._bulk_source_dialog:
                self._bulk_source_dialog.run.setCurrentIndex(self._bulk_source_dialog.run.findData(value['run']['id']))
        elif action == "prepare_import":
            if self._import_mapping_dialog:
                self._import_mapping_dialog.accept()
            page = self.pages["import"]
            page.set_run(value)
            page.history_offset = 0
            if self.current_page() is page:
                page.request_history()
            else:
                self.navigate("import")
        elif action == "import_runs":
            self.pages["import"].display_history(value)
        elif action == "import_rows":
            page = self.pages["import"]
            page.display_rows(value)
            if page.auto_running:
                QTimer.singleShot(0, page.continue_import)
        elif action == "process_import":
            page = self.pages["import"]
            page.set_run(value)
            if value.get("paused") or not value["counts"].get("Valid", 0):
                page.auto_running = False
            self.controller.submit("snapshot")
        elif action in ("edit_import_row", "review_import_row"):
            page = self.pages["import"]
            page.set_run(value)
            page.request_rows()
        elif action == "mail_snapshot":
            self.pages["mail"].display(value)
            if self.current_page() is self.pages["workspace"]:
                self.controller.submit("snapshot")
        elif action == "mail_job_details":
            self.review_mail(value)
        elif action == "workspace_mail_snapshot":
            self.pages["workspace"].mail_workflow.display(value)
        elif action == "mail_compose_details":
            self.open_mail_dialog(ComposeDialog(value["snapshot"], value["draft"], self, context=value.get("context")))
        elif action == "mail_context_details":
            if isinstance(self._mail_dialog, ComposeDialog):
                self._mail_dialog.apply_context(value)
        elif action == "mail_template_list":
            if self._template_library:
                self._template_library.display(value)
            if isinstance(self._mail_dialog, ComposeDialog):
                self._mail_dialog.refresh_templates(value["choices"])
        elif action == "mail_template_details":
            if self._template_editor:
                self._template_editor.populate(value)
            else:
                self.open_template_editor(value)
            if self._selected_template_version and self._template_editor:
                editor = self._template_editor
                editor.versions.setCurrentIndex(next((i for i in range(editor.versions.count()) if editor.versions.itemData(i)["id"] == self._selected_template_version), 0))
            self._selected_template_version = None
        elif action in ("mail_template_save", "mail_template_duplicate"):
            if self._template_editor:
                self._template_editor.accept()
            self.toast.notify(_ui_tr('E-Mail-Vorlage'), _ui_format('{0} · Version {1} gespeichert.', value['name'], value['version_number']))
            if self._template_library:
                self._template_library.offset = 0
                self._template_library.request_load()
            elif isinstance(self.current_page(), TemplatePage):
                self.current_page().request_load()
        elif action == "mail_template_render":
            if self._template_preview:
                self._template_preview.display(value)
            elif isinstance(self._mail_dialog, ComposeDialog):
                dialog = MailTemplatePreview(value, self._template_render_payload or {}, self._mail_dialog)
                self._template_preview = dialog
                dialog.operation_requested.connect(self.controller.submit)
                dialog.apply_requested.connect(self.apply_mail_template)
                dialog.finished.connect(lambda result: setattr(self, "_template_preview", None))
                dialog.open()
        elif action == "mail_bulk_details":
            if not self._bulk_dialog:
                dialog = BulkMailDialog(value, self)
                self._bulk_dialog = dialog
                self.install_dialog_shortcuts(dialog)
                dialog.operation_requested.connect(self.controller.submit)
                dialog.source_requested.connect(self.open_bulk_source)
                dialog.cancel_requested.connect(self.controller.cancel_current)
                dialog.delivery_requested.connect(lambda identifier: self.controller.submit("mail_bulk_delivery_details", {"batch_id": identifier}))
                dialog.draft_requested.connect(lambda identifier: self.controller.submit("mail_compose_details", {"draft_id": identifier}))
                dialog.finished.connect(lambda result: setattr(self, "_bulk_dialog", None))
                dialog.open()
                self._source_owner = "bulk"
                preferred = value.get("project_settings", {}).get("defaults", {}).get("source_list_id")
                if preferred:
                    self.controller.submit("source_list_details", {"list_id": preferred})
        elif action in ("recipient_library_save", "recipient_library_delete"):
            if self._bulk_dialog:
                self._bulk_dialog.display_collections(value)
                self._bulk_dialog.show_contacts()
        elif action == "mail_bulk_delivery_details":
            if not self._bulk_delivery_dialog:
                dialog = BulkDeliveryDialog(value, self._bulk_dialog or self)
                self._bulk_delivery_dialog = dialog
                dialog.operation_requested.connect(self.controller.submit)
                dialog.export_requested.connect(lambda batch: self.open_export(entity="email_jobs", batch_id=batch))
                dialog.finished.connect(self.bulk_delivery_closed)
                dialog.open()
        elif action.startswith("mail_bulk_delivery_"):
            if self._bulk_delivery_dialog and (not self._bulk_delivery_dialog.dispatch or self._bulk_delivery_dialog.dispatch["id"] == value["id"]):
                self._bulk_delivery_dialog.display(value)
            if value["status"] == "Completed" and action == "mail_bulk_delivery_next":
                self.toast.notify(_ui_tr('Gruppenversand abgeschlossen'), _ui_format('{0} Nachrichten gesendet · {1} storniert.', value['counts']['sent'], value['counts']['cancelled']))
            elif value.get("last_error") and action in ("mail_bulk_delivery_next", "mail_bulk_delivery_prepare_next"):
                self.toast.notify(_ui_tr('Gruppenversand pausiert'), value["last_error"], category="warning")
            self.apply_bulk_dispatch(value)
            self._bulk_refresh_pending = True
        elif action == "mail_bulk_background":
            self._background_groups = value["groups"]
            self.pages["workspace"].display_bulk_groups(value["groups"])
            dispatch = value["dispatch"]
            if dispatch:
                self._bulk_refresh_pending = True
            if dispatch and self._bulk_delivery_dialog and self._bulk_delivery_dialog.dispatch and self._bulk_delivery_dialog.dispatch["id"] == dispatch["id"]:
                self._bulk_delivery_dialog.display(dispatch)
            if dispatch and dispatch["status"] == "Completed":
                self.toast.notify(_ui_tr('Gruppenversand abgeschlossen'), _ui_format('{0} Nachrichten gesendet.', dispatch['counts']['sent']))
            elif dispatch and dispatch.get("last_error"):
                self.toast.notify(_ui_tr('Gruppenversand pausiert'), dispatch["last_error"], category="warning")
            if self._bulk_control_pending:
                operation, payload = self._bulk_control_pending
                self._bulk_control_pending = None
                self.controller.submit(operation, payload)
        elif action in ('builder_groups_list','builder_groups_save','builder_groups_delete'):
            self.pages['builder'].display_node_groups(value,choose=action=='builder_groups_list')
        elif action == "builder_details":
            self.pages["builder"].display_details(value)
        elif action == "builder_load":
            self.pages["builder"].loaded(value)
        elif action == 'builtin_template_install':
            self.toast.notify(_ui_tr('Vorlage gespeichert'), _ui_tr('Mitgelieferte Vorlage als eigene bearbeitbare Version angelegt.'))
            if isinstance(self.current_page(), TemplatePage):
                self.current_page().request_load()
        elif action == "builder_import":
            self.pages["builder"].imported(value)
        elif action == "builder_export":
            _ui_locale.set_text(self.pages['builder'].status, _ui_format('Graphvorlage exportiert: {0}', value['path']))
            self.toast.notify(_ui_tr('Graphvorlage gespeichert'), value["path"])
        elif action == "builder_save":
            self.pages["builder"].saved_version(value)
            self.toast.notify(_ui_tr('E-Mail-Builder'), _ui_tr('Builder-Version gespeichert.'))
        elif action == "builder_preview":
            self.pages["builder"].display_preview(value)
        elif action == "builder_asset_preview":
            self.pages["builder"].display_asset_preview(value)
        elif action == "builder_create":
            self.pages["builder"].created(value)
            self.toast.notify(_ui_tr('E-Mail-Builder'), _ui_format('{0} lokale Entwürfe erstellt.', len(value['batch']['items'])))
            if value.get("dispatch"):
                self.controller.submit("mail_bulk_delivery_details", {"batch_id": value["batch"]["id"]})
            else:
                self.controller.submit("snapshot")
        elif action == "word_replace_details":
            self.pages["word_replace"].display_details(value)
        elif action == "word_replace_analyze":
            self.pages["word_replace"].display_analysis(value)
        elif action == "word_replace_preview":
            self.pages["word_replace"].display_preview(value)
        elif action == "word_replace_create":
            self.pages["word_replace"].created(value)
            if not value.get("run"):
                self.toast.notify(_ui_tr('Word Replace'), _ui_format('{0} {1}-Kopien erstellt.', value['count'], value['format'].upper()))
                self.controller.submit("snapshot")
        elif action in ("word_replace_run_load", "word_replace_run_next", "word_replace_run_pause"):
            self.pages["word_replace"].display_run(value)
            if value["status"] == "Completed" and action == "word_replace_run_next":
                self.toast.notify(_ui_tr('Word Replace'), _ui_format('{0} Ausgabekopien fertig; Lauf gespeichert.', value['completed']))
                self.controller.submit("snapshot")
        elif action in ("export_preview", "document_bundle_preview"):
            if self._export_dialog:
                self._export_dialog.display(value)
        elif action in ("export_write", "document_bundle_write"):
            if self._export_dialog:
                self._export_dialog.written(value)
            unit = _ui_tr("Dateien" if action == "document_bundle_write" else "Zeilen")
            self.toast.notify(_ui_tr('Export gespeichert'), _ui_format('{0} {1} · {2}', value['count'], unit, value['path']))
        elif action == "source_profile_save":
            if isinstance(self._bulk_source_dialog, ImportRowsDialog):
                self._bulk_source_dialog.display_profiles(value)
            if self._bulk_dialog:
                self._bulk_dialog.data["source_profiles"] = value["profiles"]
            self.pages["word_replace"].data["profiles"] = value["profiles"]
            self.pages["builder"].data["profiles"] = value["profiles"]
            self.toast.notify(_ui_tr('Datenquelle'), _ui_tr('Zuordnungsprofil gespeichert.'))
        elif action == "source_list_details":
            if isinstance(self._bulk_source_dialog, ManualRowsDialog):
                self._bulk_source_dialog.display_list(value)
            elif self._bulk_dialog and self._source_owner == "bulk":
                self.controller.submit("source_list_select", {"list_id": value["id"], "row_ids": [r["id"] for r in value["rows"]]})
        elif action == "source_list_save":
            if isinstance(self._bulk_source_dialog, ManualRowsDialog):
                self._bulk_source_dialog.list_saved(value)
            if self._bulk_dialog:
                self._bulk_dialog.data["source_lists"] = value["lists"]
            self.pages["word_replace"].data["lists"] = value["lists"]
            self.pages["builder"].data["lists"] = value["lists"]
            self.toast.notify(_ui_tr('Datenquelle'), _ui_tr('Wiederverwendbare Liste gespeichert.'))
        elif action == "source_list_select":
            self.apply_source_selection(value)
            if self._bulk_source_dialog:
                self._bulk_source_dialog.accept()
        elif action == "mail_bulk_source_rows":
            if isinstance(self._bulk_source_dialog, ImportRowsDialog):
                self._bulk_source_dialog.display(value)
        elif action == "source_document_tables":
            if isinstance(self._bulk_source_dialog, ManualRowsDialog):
                self._bulk_source_dialog.display_tables(value)
        elif action == "mail_bulk_source_select":
            self.apply_source_selection(value)
            if self._bulk_source_dialog:
                self._bulk_source_dialog.accept()
        elif action == "mail_bulk_docx_text":
            if isinstance(self._bulk_source_dialog, ManualRowsDialog):
                self._bulk_source_dialog.display_text(value)
        elif action == "mail_bulk_context":
            if self._bulk_dialog:
                self._bulk_dialog.display_context(value)
        elif action == "mail_bulk_preview":
            if self._bulk_dialog:
                self._bulk_dialog.display_preview(value)
        elif action == "mail_bulk_batch":
            if self._bulk_dialog:
                self._bulk_dialog.display_batch(value)
        elif action == "mail_bulk_create":
            if self._bulk_dialog:
                self._bulk_dialog.created(value)
            self.toast.notify(_ui_tr('Bulk-Entwürfe'), _ui_format('{0} persönliche Entwürfe lokal gespeichert.', len(value['batch']['items'])))
            self.controller.submit("snapshot")
        elif action.startswith("mail_"):
            if action in ("mail_save_draft", "mail_approve", "mail_retry", "mail_approve_and_send") and self._mail_dialog:
                self._mail_dialog.accept()
            if action == "mail_prepare_job":
                if isinstance(self._mail_dialog, PrepareMailDialog):
                    self._mail_dialog.accept()
                self.pages["workspace"].mail_workflow.focus_job(value["id"])
                self.pages["mail"].focus_job_id = value["id"]
                self.pages["mail"].job_offset = 0
                self.pages["mail"].tabs.setCurrentIndex(1)
                self.review_mail(value)
            if action == "mail_connect":
                self.statusBar().showMessage(_ui_format('Gmail verbunden: {0}', value['account_email']))
                self.toast.notify(_ui_tr('Gmail verbunden'), _ui_format('{0} · Absender beim Vorbereiten auswählen.', value['account_email']))
            if action in ("mail_send", "mail_reconcile", "mail_approve_and_send"):
                self.statusBar().showMessage(_ui_format('Versandauftrag: {0}', value['status']))
                self.toast.notify(_ui_tr('Versandauftrag'), _ui_format('Status: {0}', value['status']))
            elif action == "mail_save_draft":
                self.toast.notify(_ui_tr('E-Mail'), _ui_tr('Entwurf im Projekt gespeichert.'))
            self.pages["mail"].request_load()
        elif action in ("create_record", "update_record", "change_status", "import_template", "document_template_duplicate", "generate_document", "create_pdf"):
            if action in ("create_record", "update_record") and isinstance(self._record_dialog, RecordDialog):
                self._record_dialog.accept()
            if action == "generate_document":
                if self._generation_dialog:
                    self._generation_dialog.accept()
                message = _ui_tr("DOCX gespeichert.")
                if value["unresolved"]:
                    message = _ui_format("{0}\nOffene optionale Platzhalter: {1}", message, ", ".join(value["unresolved"]))
                self.toast.notify(_ui_tr('Dokument erstellt'), message)
            else:
                self.toast.notify(_ui_tr('Gespeichert'), (_ui_tr('Datensatz aktualisiert.') if action in ("update_record", "change_status") else _ui_tr('Vorgang abgeschlossen.')))
            self.controller.submit("snapshot")

    def show_preview(self, value, *, temporary):
        parent = self._generation_dialog or self
        dialog = PreviewDialog(value, parent)
        self._preview_dialog = dialog
        def finished(result):
            self._preview_dialog = None
            if temporary:
                self.controller.submit("release_preview")
        dialog.finished.connect(finished)
        dialog.open()

    def operation_failed(self, action, message):
        if self._close_requested:
            self._close_requested = False
            self.setEnabled(True)
            for timer in (self.mail_timer,self.bulk_timer,self.followup_timer):timer.start()
        self.toast.notify(_ui_tr('Aktion nicht abgeschlossen'), message, category="error")
        if action == "set_workspace_mode":
            self.pages["workspace"].update_snapshot(self.snapshot)
        if self.pages["import"].auto_running:
            self.pages["import"].auto_running = False
            self.set_busy(self.controller.busy)
            self.pause_import.hide()
        self._pending_template = None
        self.statusBar().showMessage(_ui_tr('Vorgang fehlgeschlagen.'))
        if action.startswith("mail_bulk_delivery_") and self._bulk_delivery_dialog:
            self._bulk_delivery_dialog.failed()
        if action.startswith("word_replace_"):
            self.pages["word_replace"].auto_run = False
            self.pages["word_replace"].invalidate()
            _ui_locale.set_text(self.pages['word_replace'].status, message)
        if action == "builder_asset_preview":
            self.pages["builder"].node_preview.clear(message)
            _ui_locale.set_text(self.pages['builder'].status, message)
        elif action.startswith("builder_"):
            self.pages["builder"].invalidate()
            _ui_locale.set_text(self.pages['builder'].status, message)
        QMessageBox.warning(self._export_dialog or self._bulk_delivery_dialog or self._bulk_source_dialog or self._bulk_dialog or self._template_preview or self._template_editor or self._template_library or self._project_dialog or self._record_dialog or self._mail_dialog or self._import_mapping_dialog or self._generation_dialog or self, _ui_tr('Aktion nicht abgeschlossen'), message)
        if action in ("mail_bulk_preview", "mail_bulk_create") and self._bulk_dialog:
            self._bulk_dialog.invalidate()
        if action == "mail_approve_and_send":
            if isinstance(self._mail_dialog, MailJobDialog):
                self._mail_dialog.reject()
            self.pages["mail"].request_load()

    def compose_mail(self, draft):
        page = self.pages["mail"]
        if not page.data:
            page.request_load()
            return
        self.open_mail_dialog(ComposeDialog(page.data, draft, self))

    def review_mail(self, job):
        self.open_mail_dialog(MailJobDialog(job, self))

    def open_mail_dialog(self, dialog):
        self.install_dialog_shortcuts(dialog)
        self._mail_dialog = dialog
        dialog.operation_requested.connect(self.submit_mail_operation)
        if isinstance(dialog, ComposeDialog):
            dialog.template_library_requested.connect(self.open_template_library)
        dialog.finished.connect(lambda result: setattr(self, "_mail_dialog", None))
        dialog.setModal(True)
        dialog.open()

    def submit_mail_operation(self, action, payload):
        if action == "mail_template_render":
            self._template_render_payload = dict(payload)
        self.controller.submit(action, payload)

    def open_template_library(self):
        if self.controller.busy or self.controller.stopping or self._template_library or not self.snapshot:
            return
        dialog = MailTemplateLibrary(self._mail_dialog or self)
        self._template_library = dialog
        self.install_dialog_shortcuts(dialog)
        dialog.operation_requested.connect(self.controller.submit)
        dialog.action_requested.connect(self.template_action)
        dialog.finished.connect(lambda result: setattr(self, "_template_library", None))
        dialog.open()
        dialog.request_load()

    def template_action(self, action, record):
        if self.controller.busy:
            return
        if action == "new":
            self.open_template_editor()
        elif action == "edit" and record:
            self.controller.submit("mail_template_details", {"template_id": record["id"]})

    def open_template_editor(self, details=None):
        dialog = MailTemplateEditor(details, self._template_library or self)
        self._template_editor = dialog
        self.install_dialog_shortcuts(dialog)
        dialog.operation_requested.connect(self.controller.submit)
        dialog.finished.connect(lambda result: setattr(self, "_template_editor", None))
        dialog.open()

    def apply_mail_template(self, value):
        if self._template_preview and isinstance(self._mail_dialog, ComposeDialog):
            self._mail_dialog.apply_template(value)
            self._template_preview.accept()

    def close_template_dialogs(self):
        if self._export_dialog:
            self._export_dialog.reject()
        if self._bulk_delivery_dialog:
            dialog, self._bulk_delivery_dialog = self._bulk_delivery_dialog, None
            dialog.finished.disconnect(self.bulk_delivery_closed)
            dialog.force_close()
        for dialog in (self._template_preview, self._template_editor, self._template_library, self._bulk_source_dialog, self._bulk_dialog):
            if dialog:
                dialog.reject()
        self._template_render_payload = None

    def bulk_delivery_closed(self, result):
        self._bulk_delivery_dialog = None
        if self._bulk_dialog:
            self._bulk_dialog.setEnabled(True)
            self._bulk_dialog.set_busy(self.controller.busy)
        if self.snapshot and not self.controller.busy and not self.controller.stopping:
            self.controller.submit("snapshot")

    def open_export(self, *, entity="contacts", search="", selected_ids=None, batch_id=None):
        if not self.snapshot or self.controller.busy or self._export_dialog:
            return
        dialog = ExportDialog(self.snapshot["path"], self._bulk_delivery_dialog or self._bulk_dialog or self,
                              entity=entity, search=search, selected_ids=selected_ids, defaults=self.preferences.values(), batch_id=batch_id)
        self._export_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.cancel_requested.connect(self.controller.cancel_current)
        dialog.bundle_requested.connect(self.switch_document_bundle)
        dialog.finished.connect(lambda result: setattr(self, "_export_dialog", None))
        dialog.open()
        dialog.request_preview()

    def switch_document_bundle(self):
        if self._export_dialog and not self.controller.busy:
            self._export_dialog.reject()
            self.open_document_bundle()

    def open_document_bundle(self, *, search="", selected_ids=None):
        if not self.snapshot or self.controller.busy or self._export_dialog:
            return
        dialog = DocumentBundleDialog(self.snapshot["path"], self, search=search, selected_ids=selected_ids, defaults=self.preferences.values())
        self._export_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.cancel_requested.connect(self.controller.cancel_current)
        dialog.finished.connect(lambda result: setattr(self, "_export_dialog", None))
        dialog.open()
        dialog.request_preview()

    def open_bulk_source(self, kind):
        if self.controller.busy or not self._bulk_dialog or self._bulk_source_dialog:
            return
        self._source_owner = "bulk"
        fields = self._bulk_dialog.source_fields()
        if kind == "import":
            dialog = ImportRowsDialog(self._bulk_dialog.data.get("source_runs", []), fields, self._bulk_dialog,
                                      profiles=self._bulk_dialog.data.get("source_profiles", []))
        else:
            dialog = ManualRowsDialog(fields, self._bulk_dialog, lists=self._bulk_dialog.data.get("source_lists", []))
            dialog.rows_ready.connect(self._bulk_dialog.add_sources)
        self._bulk_source_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.finished.connect(lambda result: setattr(self, "_bulk_source_dialog", None))
        dialog.open()
        if kind == "import" and dialog.run.count() == 2:
            dialog.run.setCurrentIndex(1)

    def open_word_replace_settings(self):
        self.navigate("settings")
        self.pages["settings"].tabs.setCurrentIndex(2)

    def open_builder_settings(self):
        self.navigate("settings")
        self.pages["settings"].tabs.setCurrentIndex(4)

    def submit_builder_checkpoint(self, action, payload):
        if self.controller.submit_background(action, payload):
            self.pages["builder"]._checkpoint_force = False
        elif not self.controller.stopping:
            self.pages["builder"].autosave_timer.start(1000)

    def submit_builder_asset_autoload(self, action, payload):
        if not self.controller.submit_background(action, payload):
            page = self.pages["builder"]
            page.autoload_deferred(payload["request_id"])
            if self.controller.stopping:
                page.autoload_timer.stop()

    def builder_checkpoint_before_operation(self, action):
        if action in ("close_project", "open_project", "create_project", "backup", "shutdown"):
            page = self.pages["builder"]
            payload = page.checkpoint_payload(force=page._checkpoint_force)
            return ("builder_workspace_save", payload) if payload else None
        return None

    def shutdown_checkpoint_failed(self, message):
        self._close_requested = False
        for timer in (self.mail_timer,self.bulk_timer,self.followup_timer):timer.start()
        self.setEnabled(True)
        self.statusBar().showMessage(_ui_tr('Schließen angehalten: Arbeitsstand konnte nicht gesichert werden.'))
        self.toast.notify(_ui_tr('Arbeitsstand sichern'), message, category="error")

    def open_builder_source(self, kind):
        if not self.snapshot or self.controller.busy or self._bulk_source_dialog:
            return
        page = self.pages["builder"]
        if kind == 'file':
            path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Excel / CSV laden'), '', 'Excel / CSV (*.xlsx *.csv)')
            if path:
                self.controller.submit('inspect_builder_source', {'source_path': path})
            return
        self._source_owner = "builder"
        if kind == "import":
            dialog = ImportRowsDialog(page.data.get("runs", []), page.fields(), self, profiles=page.data.get("profiles", []))
        else:
            dialog = ManualRowsDialog(page.fields(), self, lists=page.data.get("lists", []))
            dialog.rows_ready.connect(page.add_sources)
        self._bulk_source_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.finished.connect(lambda result: setattr(self, "_bulk_source_dialog", None))
        dialog.open()
        if kind == "import" and dialog.run.count() == 2:
            dialog.run.setCurrentIndex(1)

    def open_word_replace_source(self, kind):
        if not self.snapshot or self.controller.busy or self._bulk_source_dialog:
            return
        page = self.pages["word_replace"]
        self._source_owner = "word_replace"
        if kind == "import":
            dialog = ImportRowsDialog(page.data.get("runs", []), page.fields(), self, profiles=page.data.get("profiles", []), for_documents=True)
        else:
            dialog = ManualRowsDialog(page.fields(), self, lists=page.data.get("lists", []))
            dialog.rows_ready.connect(page.add_sources)
        self._bulk_source_dialog = dialog
        dialog.operation_requested.connect(self.controller.submit)
        dialog.finished.connect(lambda result: setattr(self, "_bulk_source_dialog", None))
        dialog.open()
        if kind == "import" and dialog.run.count() == 2:
            dialog.run.setCurrentIndex(1)

    def apply_source_selection(self, value):
        if self._source_owner == "builder":
            self.pages["builder"].add_sources(value)
        elif self._source_owner == "word_replace":
            self.pages["word_replace"].add_sources(value)
        elif self._bulk_dialog:
            self._bulk_dialog.add_sources(value)

    def scheduler_toggled(self, enabled):
        self._last_mail_tick = time.monotonic()
        if enabled:
            self._mail_gap_pending = True

    def bulk_background_tick(self):
        now = time.monotonic()
        if now - self._last_bulk_tick > 90:
            self._bulk_gap_pending = True
        self._last_bulk_tick = now
        if not self.snapshot or self.controller.busy or self.controller.stopping or QApplication.activeModalWidget() or self.pages["import"].auto_running:
            return
        if self._bulk_refresh_pending and not self._bulk_delivery_dialog:
            if self.controller.submit("snapshot"):
                self._bulk_refresh_pending = False
            return
        if not any(g["status"] == "Running" and g.get("background") for g in self._background_groups):
            return
        if self._bulk_gap_pending:
            if self.controller.submit("mail_bulk_background", {"require_review": True}):
                self._bulk_gap_pending = False
        else:
            self.controller.submit("mail_bulk_background")

    def apply_bulk_dispatch(self, value):
        groups = [g for g in self._background_groups if g["id"] != value["id"]]
        if value["status"] not in ("Completed", "Cancelled"):
            previous = next((g for g in self._background_groups if g["id"] == value["id"]), {})
            name = previous.get("name") or (self._bulk_delivery_dialog.data["batch"]["name"] if self._bulk_delivery_dialog else "Gruppe")
            groups.append({**previous, **{key: v for key, v in value.items() if key not in ("items", "counts", "fingerprint")}, "name": name})
        self._background_groups = groups
        if self.snapshot:
            self.snapshot["bulk_groups"] = groups
        self.pages["workspace"].display_bulk_groups(groups)

    def mail_tick(self):
        now = time.monotonic()
        if now - self._last_mail_tick > 90:
            self._mail_gap_pending = True
        self._last_mail_tick = now
        page = self.pages["mail"]
        if (not self.snapshot or not page.scheduler.isChecked() or self.controller.busy or self.controller.stopping
                or self.pages["import"].auto_running or self._mail_dialog or self._generation_dialog or self._import_mapping_dialog
                or QApplication.activeModalWidget()):
            return
        if self._mail_gap_pending:
            if self.controller.submit("mail_mark_overdue"):
                self._mail_gap_pending = False
            return
        self.controller.submit("mail_due", {"max_jobs": 1})

    def followup_action(self, action, record):
        if action == "new_reminder":
            self.controller.submit("reminder_details")
        elif action == "edit_reminder" and record:
            self.controller.submit("reminder_details", {"source": record["source"], "record_id": record["record_id"]})
        elif action in ("finish_reminder", "dismiss_reminder") and record:
            self.controller.submit("reminder_finish", {"source": record["source"], "record_id": record["record_id"],
                                   "expected_version": record["version"], "status": "Completed" if action == "finish_reminder" else "Dismissed"})
        elif action == "followup_application" and record and record["application_id"]:
            self.controller.submit("record_details", {"entity": "applications", "record_id": record["application_id"]})

    def apply_followup_summary(self, summary):
        if self.snapshot:
            previous_due = self.snapshot["counts"]["followups"]
            self.snapshot["counts"]["followups"] = summary["due"]
            self.pages["overview"].update_snapshot(self.snapshot)
            self.pages["workspace"].update_snapshot(self.snapshot)
            if summary["due"] > previous_due:
                self.toast.notify(_ui_tr('Nachfassen'), _ui_format('{0} Vorgänge sind jetzt fällig. Im Arbeitsbereich Nachfassen prüfen öffnen.', summary['due']))
            index = self.page_order.index("followups")
            _ui_locale.set_text(self.navigation.item(index), _ui_format('{0} ({1})', translate('Nachfassen'), summary['due']) if summary['due'] else translate('Nachfassen'))

    def followup_tick(self):
        if (not self.snapshot or self.controller.busy or self.controller.stopping
                or self.pages["import"].auto_running or QApplication.activeModalWidget()):
            return
        page = self.current_page()
        if isinstance(page, FollowUpPage):
            page.request_load()
        else:
            self.controller.submit("followup_summary")

    def pause_current_import(self):
        self.pages["import"].auto_running = False
        self.controller.cancel_current()
        self.set_busy(self.controller.busy)
        self.pause_import.hide()
        self.statusBar().showMessage(_ui_tr('Import hält nach der laufenden Zeile an. Erledigte Zeilen bleiben gespeichert.'))

    def shutdown_finished(self):
        self.mail_timer.stop()
        self.bulk_timer.stop()
        self.followup_timer.stop()
        self._shutdown_ready = True
        self.close()

    def closeEvent(self, event):
        if self._shutdown_ready:
            event.accept()
        else:
            self._close_requested = True
            for timer in (self.mail_timer,self.bulk_timer,self.followup_timer):timer.stop()
            self.setEnabled(False)
            if self.controller.busy:
                self.statusBar().showMessage(_ui_tr('Laufenden Vorgang abschließen; anschließend wird EmailCenter geschlossen.'))
            else:
                self.controller.shutdown()
            event.ignore()
