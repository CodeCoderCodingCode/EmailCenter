"""Small shared palette; pages inherit the same visual rules."""

from PySide6.QtGui import QColor, QPalette
import re
from ..appearance import THEMES, is_dark_theme
from ..language import translate as _ui_tr


def accent_text_color(accent):
    """Choose black or white text so custom primary colors remain readable."""
    channels = [int(accent[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    luminance = sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#ffffff" if 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 else "#000000"


def apply_theme(application, dark=False, accent="#2862c4", *, theme=None):
    if theme is not None:
        dark = is_dark_theme(theme)
    if not isinstance(accent, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", accent) is None:
        raise ValueError(_ui_tr('Ungültige Akzentfarbe.'))
    application.setStyle("Fusion")
    colors = {
        "background": "#101827" if dark else "#f4f6fa",
        "surface": "#192438" if dark else "#ffffff",
        "text": "#e8eef8" if dark else "#172238",
        "muted": "#b0bed2" if dark else "#596980",
        "border": "#34425b" if dark else "#dce3ed",
        "selected": "#234368" if dark else "#e6f0ff",
    }
    colors.update(THEMES[theme]["colors"] if theme else {})
    colors["accent"] = accent
    colors['radius'] = THEMES.get(theme, {}).get('radius', 6)
    colors["accent_text"] = accent_text_color(accent)
    base, tint = QColor(colors["surface"]), QColor(accent)
    amount = 0.25 if dark else 0.10
    colors["selected"] = QColor(*[round(getattr(base, channel)() * (1 - amount) + getattr(tint, channel)() * amount)
                                 for channel in ("red", "green", "blue")]).name()
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "background"),
                        (QPalette.ColorRole.Base, "surface"),
                        (QPalette.ColorRole.AlternateBase, "background"),
                        (QPalette.ColorRole.Button, "surface"),
                        (QPalette.ColorRole.WindowText, "text"),
                        (QPalette.ColorRole.Text, "text"),
                        (QPalette.ColorRole.ButtonText, "text")):
        palette.setColor(role, QColor(colors[color]))
    palette.setColor(QPalette.ColorRole.Mid, QColor(colors["border"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["accent_text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors["muted"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(colors["muted"]))
    application.setPalette(palette)
    application.setStyleSheet("""
        QWidget { font-family: 'Segoe UI'; font-size: 10pt; }
        QMainWindow, QDialog { background: %(background)s; }
        QLabel#pageTitle { font-size: 22pt; font-weight: 600; }
        QLabel#brand { font-size: 17pt; font-weight: 700; }
        QLabel#muted { color: %(muted)s; }
        QLabel#metric { font-size: 30pt; font-weight: 600; }
        QFrame#card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px; }
        QListWidget#navigation { background: %(surface)s; border: 0; outline: 0; }
        QListWidget#navigation::item { padding: 13px 14px; margin: 3px 7px; border-radius: 7px; }
        QListWidget#navigation::item:selected { background: %(selected)s; color: %(text)s; font-weight: 600; }
        QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTableWidget {
            background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; padding: 6px;
        }
        QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid %(accent)s; }
        QPushButton { padding: 8px 14px; border: 1px solid %(border)s; border-radius: %(radius)spx; background: %(surface)s; }
        QPushButton:hover { border-color: %(accent)s; }
        QPushButton[primary="true"] { background: %(accent)s; color: %(accent_text)s; border: 1px solid %(accent)s; }
        QPushButton:disabled { color: %(muted)s; }
        QPushButton[primary="true"]:disabled { background: %(background)s; color: %(muted)s; border: 1px solid %(border)s; }
        QHeaderView::section { padding: 9px; background: %(background)s; border: 0; font-weight: 600; }
        QTabWidget::pane { border: 1px solid %(border)s; background: %(surface)s; }
        QTabBar::tab { padding: 9px 18px; background: %(background)s; color: %(muted)s; border: 1px solid %(border)s; }
        QTabBar::tab:selected { background: %(surface)s; color: %(text)s; border-bottom: 2px solid %(accent)s; }
        QToolBar { spacing: 7px; padding: 8px; border-bottom: 1px solid %(border)s; }
        QStatusBar { color: %(muted)s; }
    """ % colors)
