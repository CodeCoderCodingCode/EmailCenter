"""Nonmodal local feedback: latest event wins, no unbounded message queue."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import QEvent, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QVBoxLayout

from .pages import button, label


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        self.title = label("")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.title, 1)
        self.close_button = button("×", self.dismiss)
        _ui_locale.set_accessible_name(self.close_button, _ui_tr('Benachrichtigung schließen'))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.message = label("")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setDuration(160)
        self.preferences, self.category, self.persistent = None, "info", False
        self.hide()
        parent.installEventFilter(self)

    def configure(self, preferences):
        self.preferences = preferences
        if self.isVisible() and self.category == "error":
            self.persistent = preferences.toast_persistent_errors
            self.timer.stop()
            if not self.persistent:
                self.timer.start(preferences.toast_seconds * 1000)
        if preferences.reduced_motion:
            self.animation.stop()
            self.effect.setOpacity(1)

    def notify(self, title, message, *, duration=None, category="success"):
        if category not in ("success", "info", "warning", "error"):
            raise ValueError(_ui_tr('Unbekannte Benachrichtigungskategorie.'))
        preferences = self.preferences
        if preferences and ((category == "info" and not preferences.toast_info) or (category == "success" and not preferences.toast_success)):
            return
        if self.isVisible() and self.persistent and category in ("success", "info"):
            return
        self.category = category
        self.persistent = bool(category == "error" and preferences and preferences.toast_persistent_errors)
        self.animation.stop()
        self.timer.stop()
        prefix = {"success": "Erfolg · ", "info": "Info · ", "warning": "Hinweis · ", "error": "Fehler · "}[category]
        _ui_locale.set_text(self.title, _ui_format('{0}{1}', _ui_tr(prefix), title if len(str(title)) <= 200 else str(title)[:200]))
        _ui_locale.set_text(self.message, message if len(str(message)) <= 1600 else str(message)[:1600])
        self.setFixedWidth(min(420, max(240, self.parentWidget().width() - 32)))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        if preferences and preferences.reduced_motion:
            self.effect.setOpacity(1)
        else:
            self.animation.start()
        if not self.persistent:
            self.timer.start(duration if duration is not None else 1000 * (preferences.toast_seconds if preferences else 6))

    def dismiss(self):
        self.animation.stop()
        self.timer.stop()
        self.hide()
        self.persistent = False

    def reposition(self):
        self.move(max(0, self.parentWidget().width() - self.width() - 16),
                  max(0, self.parentWidget().height() - self.height() - 40))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self.reposition()
        return super().eventFilter(watched, event)
