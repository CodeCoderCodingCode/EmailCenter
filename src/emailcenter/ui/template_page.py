"""One searchable, version-specific document and mail template library."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtWidgets import QComboBox
from .pages import RecordPage


class TemplatePage(RecordPage):
    def __init__(self):
        super().__init__("templates", "Vorlagen", "DOCX und E-Mail gemeinsam suchen. Jede Zeile ist eine konkrete gespeicherte Version.",
                         [("Vorlage", "template_name"), ("Typ", "type_label"), ("Version", "version_number"), ("Erstellt", "created_at")],
                         [("Mitgelieferte Vorlagen", "builtin_templates", False), ("DOCX importieren", "import", False), ("Neue E-Mail-Vorlage", "new_mail_template", False),
                          ("Neue DOCX-Version", "version", True), ("Version duplizieren", "duplicate_template", True),
                          ("DOCX verwenden", "generate", True), ("E-Mail bearbeiten", "edit_mail_template", True)])
        self.type_filter = QComboBox()
        for title, value in (("Alle Vorlagen", "all"), ("DOCX", "document"), ("E-Mail", "email")):
            _ui_locale.add_item(self.type_filter, _ui_tr(title), value)
        _ui_locale.set_accessible_name(self.type_filter, _ui_tr('Vorlagentyp filtern'))
        self.layout().insertWidget(3, self.type_filter)
        self.type_filter.currentIndexChanged.connect(self.search_records)

    def request_load(self):
        self.load_requested.emit("list", {"entity": self.entity, "search": self.search.text(), "offset": self.offset,
                                          "limit": self.limit, "template_type": self.type_filter.currentData()})

    def update_selection(self):
        super().update_selection()
        record = self.selected_record()
        for action in ("version", "generate", "edit_mail_template"):
            kind = "email" if action == "edit_mail_template" else "document"
            self.action_buttons[action][0].setEnabled(bool(record and record.get("template_type") == kind))
