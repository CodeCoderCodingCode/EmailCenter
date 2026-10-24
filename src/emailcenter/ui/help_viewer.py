"""Offline illustrated handbook with context anchors."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton
from ..resources import resource_path
from ..language import translate as _ui_tr


def context_anchor(page_key, page=None):
    if page_key == 'builder' and page is not None:
        selected = next((n for n in page.graph['nodes'] if n['id'] == page.selected_id), None)
        return 'node-' + selected['kind'] if selected else 'builder'
    if page_key == 'settings' and page is not None:
        return 'settings-' + str(page.tabs.currentIndex())
    return page_key or 'first-steps'


class HelpDialog(QDialog):
    def __init__(self, anchor='first-steps', parent=None):
        super().__init__(parent)
        self.setWindowTitle(str(_ui_tr('EmailCenter · Hilfe')))
        self.resize(1050, 780)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser)
        self.url = QUrl.fromLocalFile(str(resource_path('guide', 'EmailCenter_Guide.html')))
        self.url.setFragment(anchor)
        self.browser.setSource(self.url)
        open_browser = QPushButton(str(_ui_tr('Guide im Browser öffnen')))
        open_browser.clicked.connect(lambda: QDesktopServices.openUrl(self.url))
        layout.addWidget(open_browser)

    def navigate(self, anchor):
        self.url.setFragment(anchor)
        self.browser.setSource(self.url)
        self.show(); self.raise_(); self.activateWindow()
