"""Edit project defaults after creation; existing work keeps its captured values."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtWidgets import QComboBox, QFormLayout, QPlainTextEdit, QVBoxLayout
from .mail_template_dialogs import BusyDialog
from .pages import button, label


class ProjectSettingsDialog(BusyDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        _ui_locale.set_window_title(self, _ui_tr('Projektziel und Vorgaben'))
        self.resize(620, 580)
        layout = QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Vorgaben für neue Vorgänge'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Gespeicherte Entwürfe, Dokumente und Versandfreigaben behalten ihre Werte.'), 'muted'))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        settings = data["settings"]
        self.goal = QPlainTextEdit(settings["goal"])
        _ui_locale.add_row(form, _ui_tr('Projektziel'), self.goal)
        self.mode = self.combo(form, "Arbeitsmodus", [(_ui_tr('Bewerbungen'), 'applications'), (_ui_tr('E-Mail-Aufträge'), 'mail')], settings["mode"])
        self.controls = {}
        for key, caption, items, current in (
            ("applicant_profile_id", "Bewerberprofil", [(p["display_name"], p["id"]) for p in data["profiles"]], settings["defaults"]["applicant_profile_id"]),
            ("document_version_id", "Dokumentvorlage", [(f"{t['name']} · v{t['version_number']}", t["id"]) for t in data["templates"]], settings["defaults"]["document_version_id"]),
            ("source_list_id", "Empfängerquelle", [(s["name"], s["id"]) for s in data["lists"]], settings["defaults"]["source_list_id"]),
        ):
            self.controls[key] = self.combo(form, caption, [(_ui_tr('Keine Vorgabe'), None), *items], current)
        self.account = QComboBox()
        self.account.setEditable(True)
        self.account.addItems(["", *[a["account_email"] for a in data["accounts"]]])
        self.account.setCurrentText(settings["defaults"]["account_email"])
        _ui_locale.add_row(form, _ui_tr('Standardkonto (E-Mail)'), self.account)
        self.format = self.combo(form, "Nachrichtenformat", [(_ui_tr('Text'), 'plain'), (_ui_tr('HTML'), 'html')], settings["defaults"]["body_format"])
        layout.addWidget(button(_ui_tr('Vorgaben speichern'), self.save, primary=True))
        layout.addWidget(button(_ui_tr('Abbrechen'), self.reject))

    def combo(self, form, caption, items, current):
        widget = QComboBox()
        for title, value in items:
            _ui_locale.add_item(widget, title, value)
        widget.setCurrentIndex(max(0, widget.findData(current)))
        _ui_locale.add_row(form, _ui_tr(caption), widget)
        return widget

    def save(self):
        self.operation_requested.emit("project_setup_save", {
            "goal": self.goal.toPlainText(), "mode": self.mode.currentData(),
            "defaults": {**{key: control.currentData() for key, control in self.controls.items()},
                         "account_email": self.account.currentText().strip(), "body_format": self.format.currentData()},
            "expected_version": self.data["settings"]["version"]})
