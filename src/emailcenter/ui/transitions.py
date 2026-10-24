"""Short opacity transitions which preserve widgets, focus and scroll positions."""

from PySide6.QtCore import QObject, QPropertyAnimation, QEasingCurve, QRect, Qt, QEvent, QVariantAnimation
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QPushButton


class PageTransition(QObject):
    def __init__(self, target):
        super().__init__(target)
        self.target = target
        self.animation = None
        self.effect = None
        self.overlay = None
        self.style, self.duration = 'fade', 140

    def configure(self, preferences):
        from ..appearance import THEMES
        self.style = THEMES[preferences.theme].get('transition', 'fade') if preferences.transition_style == 'theme' else preferences.transition_style
        self.duration = preferences.animation_ms

    def stop(self):
        if self.animation:
            self.animation.stop()
            self.animation.deleteLater()
            self.animation = None
        if self.effect:
            self.target.setGraphicsEffect(None)
            self.effect = None
        if self.overlay:
            self.overlay.deleteLater()
            self.overlay = None

    def play(self, reduced_motion=False):
        self.stop()
        if reduced_motion or self.style == 'none' or not self.target.isVisible():
            return
        if self.style in ('slide', 'zoom'):
            self.overlay = QLabel(self.target)
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.overlay.setPixmap(self.target.grab())
            self.overlay.setScaledContents(True)
            end = self.target.rect()
            start = QRect(end)
            if self.style == 'slide':
                start.translate(22, 0)
            else:
                start.adjust(8, 8, -8, -8)
            self.overlay.setGeometry(start)
            self.overlay.show()
            self.animation = QPropertyAnimation(self.overlay, b'geometry', self)
            self.animation.setStartValue(start)
            self.animation.setEndValue(end)
        else:
            self.effect = QGraphicsOpacityEffect(self.target)
            self.target.setGraphicsEffect(self.effect)
            self.animation = QPropertyAnimation(self.effect, b'opacity', self)
            self.animation.setStartValue(0.82)
            self.animation.setEndValue(1.0)
        self.animation.setDuration(self.duration)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self.stop)
        self.animation.start()


class InteractionFeedback(QObject):
    """Animate button borders, preserving global themes and keyboard focus."""
    def __init__(self, application, preferences, parent=None):
        super().__init__(parent or application)
        self.preferences, self.animations = preferences, {}
        application.installEventFilter(self)

    def configure(self, preferences):
        for control, animation in list(self.animations.items()):
            animation.stop()
            try:
                control.setStyleSheet('')
            except RuntimeError:
                pass
            animation.deleteLater()
        self.animations.clear()
        self.preferences = preferences

    def eventFilter(self, control, event):
        if event.type() == QEvent.Type.ToolTip and not self.preferences.tooltips_enabled:
            return True
        if isinstance(control, QPushButton) and event.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            if self.preferences.reduced_motion or not self.preferences.hover_feedback or not control.isEnabled():
                return False
            active = event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn)
            previous = self.animations.pop(control, None)
            if previous:
                previous.stop(); previous.deleteLater()
            animation = QVariantAnimation(control)
            base = control.palette().color(QPalette.ColorRole.Mid)
            accent = QColor(self.preferences.accent)
            animation.setStartValue(base if active else accent)
            animation.setEndValue(accent if active else base)
            animation.setDuration(self.preferences.animation_ms)
            animation.valueChanged.connect(lambda color: control.setStyleSheet('border-color: ' + color.name() + ';'))
            def finish():
                if self.animations.get(control) is animation:
                    self.animations.pop(control, None)
                    if not active:
                        control.setStyleSheet('')
                animation.deleteLater()
            animation.finished.connect(finish)
            if not control.property('feedbackTracked'):
                control.setProperty('feedbackTracked', True)
                control.destroyed.connect(lambda: self.animations.pop(control, None))
            self.animations[control] = animation
            animation.start()
        return False
