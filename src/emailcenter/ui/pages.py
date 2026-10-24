"""Reusable, paginated pages with explicit extension points."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


from ..language import translate, LocalizedText
from .localization import remember


def label(text, object_name=None):
    widget = QLabel(str(text))
    remember(widget, "languageSource", text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def button(text, callback=None, *, primary=False):
    text = translate(text)
    widget = QPushButton(str(text))
    remember(widget, "languageSource", text)
    widget.setProperty("primary", primary)
    if callback:
        widget.clicked.connect(callback)
    return widget


class OverviewPage(QWidget):
    action_requested = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(20)
        layout.addWidget(label(_ui_tr('Übersicht / Projekte'), 'pageTitle'))
        self.subtitle = label(_ui_tr('Erstelle ein Projekt oder öffne einen bestehenden Projektordner.'), 'muted')
        layout.addWidget(self.subtitle)
        actions = QHBoxLayout()
        actions.addWidget(button(_ui_tr('Neues Projekt'), lambda: self.action_requested.emit('new'), primary=True))
        actions.addWidget(button(_ui_tr('Projekt öffnen'), lambda: self.action_requested.emit('open')))
        self.profile_button = button(_ui_tr('Bewerberprofil anlegen'), lambda: self.action_requested.emit('profile'))
        self.profile_button.setEnabled(False)
        actions.addWidget(self.profile_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.followup_button = button(_ui_tr('Nachfassen & Erinnerungen öffnen'), lambda: self.action_requested.emit('followups'))
        self.followup_button.setEnabled(False)
        layout.addWidget(self.followup_button)
        grid = QGridLayout()
        grid.setSpacing(16)
        self.metrics = {}
        for index, (key, name) in enumerate((("applications", "Bewerbungen"), ("companies", "Unternehmen"),
                                             ("contacts", "Kontakte"), ("templates", "Vorlagen"), ("documents", "Dokumente"), ("followups", "Fällig / zu prüfen"))):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 18, 20, 18)
            value = label("—", "metric")
            self.metrics[key] = value
            card_layout.addWidget(value)
            card_layout.addWidget(label(_ui_tr(name), "muted"))
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        self.next_steps = label(_ui_tr('Alles beginnt mit einem Projekt. Deine Daten und Dateien bleiben im gewählten Projektordner.'), 'muted')
        layout.addWidget(self.next_steps)
        layout.addStretch()

    def update_snapshot(self, snapshot):
        self.profile_button.setEnabled(bool(snapshot))
        self.followup_button.setEnabled(bool(snapshot))
        self.profile_button.setVisible(bool(snapshot))
        self.followup_button.setVisible(bool(snapshot))
        for widget in self.metrics.values():
            widget.parentWidget().setVisible(bool(snapshot))
        _ui_locale.set_text(self.subtitle, snapshot['name'] if snapshot else _ui_tr('Erstelle ein Projekt oder öffne einen bestehenden Projektordner.'))
        for key, widget in self.metrics.items():
            _ui_locale.set_text(widget, str(snapshot['counts'].get(key, 0)) if snapshot else '—')
        _ui_locale.set_text(self.next_steps, _ui_tr('Unternehmen und Bewerberprofil anlegen → Bewerbung erfassen → Vorlage importieren → Dokument prüfen.') if snapshot else _ui_tr('Deine Daten und Dateien bleiben im gewählten Projektordner.'))


class RecordPage(QWidget):
    load_requested = Signal(str, object)
    action_requested = Signal(str, object)

    def __init__(self, entity, title, description, columns, actions):
        super().__init__()
        self.entity, self.columns = entity, columns
        self.rows, self.offset, self.total, self.limit = [], 0, 0, 50
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)
        layout.addWidget(label(_ui_tr(title), "pageTitle"))
        layout.addWidget(label(_ui_tr(description), "muted"))
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        _ui_locale.set_placeholder(self.search, _ui_tr('Suchen … (Enter)'))
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.search_records)
        self.search.textChanged.connect(lambda text: self.search_records() if not text else None)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(button(_ui_tr('Suchen'), self.search_records))
        layout.addLayout(toolbar)
        self.actions_row = QGridLayout()
        self.action_buttons = {}
        for caption, action, requires_selection in actions:
            control = button(caption, lambda checked=False, action=action: self.action_requested.emit(action, self.selected_record()),
                             primary=not requires_selection)
            self.action_buttons[action] = (control, requires_selection)
            control.setEnabled(not requires_selection)
        layout.addLayout(self.actions_row)
        self.reflow_actions()
        self.table = QTableWidget(0, len(columns))
        _ui_locale.headers(self.table, [_ui_tr(caption, context='field') for caption, _ in columns])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_selection)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.result_label = label(_ui_tr('Noch keine Daten geladen.'), 'muted')
        footer.addWidget(self.result_label, 1)
        self.previous = button(_ui_tr('Zurück'), lambda: self.move_page(-1))
        self.next = button(_ui_tr('Weiter'), lambda: self.move_page(1))
        footer.addWidget(self.previous)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self.update_selection()
        self.previous.setEnabled(False)
        self.next.setEnabled(False)

    def request_load(self):
        self.load_requested.emit("list", {"entity": self.entity, "search": self.search.text(), "offset": self.offset, "limit": self.limit})

    def apply_settings(self, preferences):
        if self.limit != preferences.list_page_size:
            self.limit, self.offset = preferences.list_page_size, 0
        self.table.setAlternatingRowColors(preferences.list_alternating_rows)
        self.table.setWordWrap(preferences.list_word_wrap)
        self.table.verticalHeader().setDefaultSectionSize(24 if preferences.list_compact_rows else 36)
        self.table.verticalHeader().setMinimumSectionSize(20)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow_actions()

    def reflow_actions(self):
        columns = 3 if self.width() >= 900 else 2 if self.width() >= 550 else 1
        for index, (control, _) in enumerate(self.action_buttons.values()):
            self.actions_row.removeWidget(control)
            self.actions_row.addWidget(control, index // columns, index % columns)

    def search_records(self):
        self.offset = 0
        self.request_load()

    def move_page(self, direction):
        self.offset = max(0, self.offset + direction * self.limit)
        self.request_load()

    def display(self, result):
        self.rows, self.offset, self.total = result["rows"], result["offset"], result["total"]
        self.table.setRowCount(len(self.rows))
        for row_index, record in enumerate(self.rows):
            for column, (_, key) in enumerate(self.columns):
                item = QTableWidgetItem(str(record.get(key) or ""))
                self.table.setItem(row_index, column, item)
        first = self.offset + 1 if self.rows else 0
        _ui_locale.set_text(self.result_label, _ui_format('{0}–{1} von {2}', f'{first}', f'{self.offset + len(self.rows)}', f'{self.total}'))
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(self.offset + len(self.rows) < self.total)
        self.table.clearSelection()
        self.update_selection()

    def selected_record(self):
        row = self.table.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) and self.table.selectedItems() else None

    def update_selection(self):
        record = self.selected_record()
        for action, (control, requires_selection) in self.action_buttons.items():
            enabled = not requires_selection or record is not None
            if action == "pdf":
                enabled = bool(record and record["format"] == "docx")
            if action == "status":
                enabled = bool(record and not record["status_is_terminal"])
            control.setEnabled(enabled)


class PlannedPage(QWidget):
    def __init__(self, title, description):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.addWidget(label(_ui_tr(title), "pageTitle"))
        layout.addWidget(label(_ui_tr(description), "muted"))
        layout.addStretch()
