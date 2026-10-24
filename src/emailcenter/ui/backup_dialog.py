"""Review a backup and restore it into a new folder via the workspace worker."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QLineEdit, QVBoxLayout, QWidget
from .pages import button, label


class RestoreDialog(QDialog):
    operation_requested = Signal(str, object)
    operation_cancel_requested = Signal()

    def __init__(self, review, parent=None):
        super().__init__(parent)
        self.review, self.busy = review, False
        _ui_locale.set_window_title(self, _ui_tr('Projektbackup wiederherstellen'))
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_format('{0} · {1}\n{2} Dateien · {3} MiB', f"{review['name']}", f"{review['created_at']}", f"{review['files']}", f"{review['bytes'] / 1024 ** 2:.1f}"), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Datei-Hashes vorhanden; alle Inhalte werden bei der Wiederherstellung geprüft.') if review['verified_index'] else _ui_tr('Ältere Sicherung ohne Datei-Hashes: ZIP-Prüfsummen und Datenbank werden geprüft.'), 'muted'))
        layout.addWidget(label(_ui_tr('Es wird ein neues Projekt angelegt. Gmail-Verbindungen werden deaktiviert, offene Aufträge verlieren ihre Freigabe, Bulk-Läufe pausieren. Das aktuelle Projekt bleibt geöffnet. Nach der Wiederherstellung das neue Projekt ausdrücklich öffnen.'), 'muted'))
        self.privacy_notice=label(_ui_tr('Projektbackups sind unverschlüsselte ZIP-Dateien mit Projektdaten, Nachrichten und Dokumenten. App-eigene Gmail-Zugangstokens liegen getrennt im Windows-Tresor.'), 'muted')
        layout.addWidget(self.privacy_notice)
        form = QFormLayout()
        self.parent_path = QLineEdit()
        _ui_locale.add_row(form, _ui_tr('Übergeordneter Ordner'), self.parent_path)
        layout.addWidget(button(_ui_tr('Zielordner wählen …'), self.choose_directory))
        self.folder = QLineEdit("Wiederhergestelltes-Projekt")
        _ui_locale.add_row(form, _ui_tr('Neuer Projektordner'), self.folder)
        layout.addLayout(form)
        self.notice = label("", "muted")
        layout.addWidget(self.notice)
        self.restore_button = button(_ui_tr('Prüfen und wiederherstellen'), self.restore, primary=True)
        layout.addWidget(self.restore_button)
        self.close_button = button(_ui_tr('Abbrechen'), self.cancel_or_close)
        layout.addWidget(self.close_button)

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, _ui_tr('Ziel der Wiederherstellung'))
        if path:
            self.parent_path.setText(path)

    def restore(self):
        folder, parent = self.folder.text().strip(), Path(self.parent_path.text().strip())
        if not parent.is_absolute() or not folder or folder in (".", "..") or any(c in folder for c in '/\\:\x00'):
            _ui_locale.set_text(self.notice, _ui_tr('Absoluten Zielordner und einen neuen Ordnernamen wählen.'))
            return
        destination = parent / folder
        if destination.exists():
            _ui_locale.set_text(self.notice, _ui_tr('Dieser Ordner existiert bereits. Bitte einen neuen Namen wählen.'))
            return
        self.operation_requested.emit("backup_restore", {"path": self.review["path"], "destination": str(destination), "expected_hash": self.review["hash"]})

    def set_busy(self, busy):
        self.busy = busy
        for control in self.findChildren(QWidget):
            if control is not self.close_button:
                control.setEnabled(not busy)
        self.close_button.setEnabled(True)
        _ui_locale.set_text(self.close_button, _ui_tr('Wiederherstellung abbrechen') if busy else _ui_tr('Abbrechen'))

    def cancel_or_close(self):
        if self.busy:
            self.operation_cancel_requested.emit()
        else:
            self.reject()

    def reject(self):
        if not self.busy:
            super().reject()
