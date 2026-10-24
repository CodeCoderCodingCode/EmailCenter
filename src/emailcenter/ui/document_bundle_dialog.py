"""Explicit document-set scope, ZIP preview and incomplete-package confirmation."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                              QMessageBox, QPlainTextEdit, QVBoxLayout)
from .mail_template_dialogs import BusyDialog
from .pages import button, label


class DocumentBundleDialog(BusyDialog):
    cancel_requested = Signal()

    def __init__(self, project_path, parent=None, *, search="", selected_ids=None, defaults=None):
        super().__init__(parent)
        self.project_path, self.defaults, self.selected_ids = Path(project_path), defaults or {}, selected_ids or []
        self.preview = None
        self.resize(800, 660)
        _ui_locale.set_window_title(self, _ui_tr('Dokumentensätze exportieren'))
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Dokumentpaket · DOCX / PDF'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Ausgewählte Dokumente schließen ihren gesamten Satz ein. Das Paket enthält nur geprüfte Dokumentkopien, einen Bericht und ein Manifest.'), 'muted'))
        form = QFormLayout()
        self.scope, self.search, self.formats = QComboBox(), QLineEdit(search), QComboBox()
        _ui_locale.add_item(self.scope, _ui_tr('Suchfilter / alle Dokumentensätze'), 'filtered')
        if self.selected_ids:
            _ui_locale.add_item(self.scope, _ui_format('Sätze der {0} ausgewählten Dokumente', f'{len(self.selected_ids)}'), 'selected')
            self.scope.setCurrentIndex(1)
        for title, value in (("DOCX und PDF", ["docx", "pdf"]), ("Nur DOCX", ["docx"]), ("Nur PDF", ["pdf"])):
            _ui_locale.add_item(self.formats, _ui_tr(title), value)
        _ui_locale.add_row(form, _ui_tr('Umfang'), self.scope)
        _ui_locale.add_row(form, _ui_tr('Datei / Satz / Bewerbung'), self.search)
        _ui_locale.add_row(form, _ui_tr('Formate'), self.formats)
        layout.addLayout(form)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Unvollständiges Paket mit den aufgeführten Auslassungen ausdrücklich exportieren'))
        layout.addWidget(self.confirm)
        self.status = label(_ui_tr('Vorschau laden.'), 'muted')
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.preview_button = button(_ui_tr('Vorschau laden'), self.request_preview)
        self.export_button = button(_ui_tr('ZIP exportieren'), self.export, primary=True)
        self.cancel_button = button(_ui_tr('Export abbrechen'), self.cancel_requested.emit)
        self.close_button = button(_ui_tr('Schließen'), self.reject)
        for control in (self.preview_button, self.export_button, self.cancel_button, self.close_button):
            actions.addWidget(control)
        layout.addLayout(actions)
        self.scope.currentIndexChanged.connect(self.invalidate)
        self.formats.currentIndexChanged.connect(self.invalidate)
        self.search.textChanged.connect(self.invalidate)
        self.confirm.toggled.connect(self.update_buttons)
        self.invalidate()

    def invalidate(self):
        self.preview = None
        self.confirm.setChecked(False)
        _ui_locale.set_text(self.status, _ui_tr('Vorschau erneut laden und prüfen.'))
        self.report.clear()
        self.update_buttons()

    def request_preview(self):
        if not self.busy:
            self.invalidate()
            self.operation_requested.emit("document_bundle_preview", {"search": self.search.text() if self.scope.currentData() == "filtered" else "",
                "selected_ids": self.selected_ids if self.scope.currentData() == "selected" else None, "formats": self.formats.currentData()})

    def display(self, value):
        self.preview = value
        self.confirm.setChecked(False)
        lines = [f"{len(value['sets'])} Sätze · {value['count']} verwendbare Dateien · {value['bytes']/1024/1024:.1f} MiB", ""]
        lines += [f"{f['filename']} · {f['format'].upper()} · {f['error'] or 'bereit'}" for f in value["files"]]
        lines += ["", "Fehlende Dateien / Hinweise:"] + (value["warnings"] or ["Keine."])
        _ui_locale.set_plain_text(self.report, '\n'.join(lines))
        _ui_locale.set_text(self.status, _ui_tr('Auslassungen beheben oder unten ausdrücklich bestätigen.') if value['warnings'] else _ui_tr('Vorschau geprüft: Paket kann exportiert werden.'))
        self.update_buttons()

    def update_buttons(self):
        self.preview_button.setEnabled(not self.busy)
        self.export_button.setEnabled(bool(not self.busy and self.preview and self.preview["count"] and (not self.preview["warnings"] or self.confirm.isChecked())))
        self.cancel_button.setVisible(self.busy)
        self.close_button.setEnabled(not self.busy)
        self.confirm.setEnabled(bool(not self.busy and self.preview and self.preview["warnings"]))
        self.search.setEnabled(not self.busy and self.scope.currentData() == "filtered")
        self.scope.setEnabled(not self.busy)
        self.formats.setEnabled(not self.busy)

    def export(self):
        if not self.export_button.isEnabled():
            return
        folder = Path(self.defaults.get("export_directory") or self.project_path / "exports")
        path, _ = QFileDialog.getSaveFileName(self, _ui_tr('Dokumentpaket speichern'), str(folder / 'Dokumentpaket.zip'), _ui_tr('ZIP (*.zip)'), options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".zip")
        overwrite = target.exists()
        if overwrite and QMessageBox.question(self, _ui_tr('ZIP ersetzen'), _ui_format('{0} ausdrücklich ersetzen?', f'{target.name}')) != QMessageBox.StandardButton.Yes:
            return
        self.operation_requested.emit("document_bundle_write", {"preview_id": self.preview["preview_id"], "target_path": str(target),
                                       "overwrite": overwrite, "allow_incomplete": self.confirm.isChecked()})

    def written(self, value):
        self.preview = None
        _ui_locale.set_plain_text(self.report, f"{value['count']} Dateien exportiert: {value['path']}\n\n" + '\n'.join(value['warnings']))
        _ui_locale.set_text(self.status, _ui_tr('Dokumentpaket gespeichert.'))
        self.update_buttons()

    def set_busy(self, busy):
        self.busy = busy
        self.update_buttons()
