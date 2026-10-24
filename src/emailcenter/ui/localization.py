"""Explicit caption metadata; editable values and imported names stay untouched."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QTableWidgetItem, QListWidget, QTreeWidgetItem
from ..language import LocalizedText

SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 175


def remember(control, property_name, text):
    source = text.message if isinstance(text, LocalizedText) else None
    if hasattr(control, 'setProperty'):
        control.setProperty(property_name, source)
    elif property_name == 'languageSource':
        if isinstance(control, QTreeWidgetItem):
            control.setData(0, SOURCE_ROLE, source)
        else:
            control.setData(SOURCE_ROLE, source)


def widget(factory, *args, **kwargs):
    result = factory(*(str(value) if isinstance(value, LocalizedText) else value for value in args), **kwargs)
    text = next((value for value in args if isinstance(value, LocalizedText)), None)
    if text is not None:
        remember(result, "languageTitleSource" if isinstance(result, QGroupBox) else "languageSource", text)
    return result


def item(factory, *args, **kwargs):
    values = []
    for value in args:
        values.append([str(v) for v in value] if isinstance(value, list) else str(value) if isinstance(value, LocalizedText) else value)
    result = factory(*values, **kwargs)
    for value in args:
        if isinstance(value, LocalizedText):
            result.setData(SOURCE_ROLE, value.message)
        elif isinstance(value, list):
            for column, text in enumerate(value):
                if isinstance(text, LocalizedText):
                    result.setData(column, SOURCE_ROLE, text.message)
    return result


def cell(text):
    return item(QTableWidgetItem, text if isinstance(text, LocalizedText) else str(text))


def set_text(control, text):
    remember(control, "languageSource", text)
    control.setText(str(text))


def add_action(menu, text, callback=None):
    action = menu.addAction(str(text))
    remember(action, 'languageSource', text)
    if callback is not None:
        action.triggered.connect(callback)
    return action


def set_plain_text(control, text):
    remember(control, 'languagePlainTextSource', text)
    control.setPlainText(str(text))


def clear_text(control):
    control.setProperty('languageSource', None)
    control.setProperty('languagePlainTextSource', None)
    control.clear()


def set_html(control, html):
    control.setProperty('languagePlainTextSource', None)
    control.setHtml(html)


def set_title(control, text):
    remember(control, "languageTitleSource", text)
    control.setTitle(str(text))


def set_subtitle(control, text):
    remember(control, 'languageSubtitleSource', text)
    control.setSubTitle(str(text))


def set_wizard_button_text(control, role, text):
    control.setButtonText(role, str(text))
    remember(control.button(role), 'languageSource', text)


def set_window_title(control, text):
    remember(control, "languageWindowSource", text)
    control.setWindowTitle(str(text))


def set_tooltip(control, text):
    remember(control, "languageTooltipSource", text)
    control.setToolTip(str(text))


def set_accessible_name(control, text):
    remember(control, 'languageAccessibleNameSource', text)
    control.setAccessibleName(str(text))


def set_accessible_description(control, text):
    remember(control, 'languageAccessibleDescriptionSource', text)
    control.setAccessibleDescription(str(text))


def set_placeholder(control, text):
    remember(control, "languagePlaceholderSource", text)
    control.setPlaceholderText(str(text))


def set_suffix(control, text):
    remember(control, 'languageSuffixSource', text)
    control.setSuffix(str(text))


def set_format(control, text):
    remember(control, 'languageFormatSource', text)
    control.setFormat(str(text))


def add_item(control, *args):
    control.addItem(*(str(value) if isinstance(value, LocalizedText) else value for value in args))
    text = next((value for value in args if isinstance(value, LocalizedText)), None)
    if text is not None:
        if isinstance(control, QListWidget):
            control.item(control.count() - 1).setData(SOURCE_ROLE, text.message)
        else:
            control.setItemData(control.count() - 1, text.message, SOURCE_ROLE)


def add_items(control, texts):
    for text in texts:
        add_item(control, text)


def set_item_text(control, index, text):
    control.setItemText(index, str(text))
    control.setItemData(index, text.message if isinstance(text, LocalizedText) else None, SOURCE_ROLE)


def add_row(layout, *args):
    row = layout.rowCount()
    layout.addRow(*(str(value) if isinstance(value, LocalizedText) else value for value in args))
    if args and isinstance(args[0], LocalizedText):
        label = layout.itemAt(row, layout.ItemRole.LabelRole)
        if label and label.widget():
            remember(label.widget(), "languageSource", args[0])


def insert_row(layout, index, caption, control):
    layout.insertRow(index, str(caption), control)
    label = layout.itemAt(index, layout.ItemRole.LabelRole)
    if label and label.widget():
        remember(label.widget(), 'languageSource', caption)


def headers(control, texts):
    method = control.setHorizontalHeaderLabels if hasattr(control, "setHorizontalHeaderLabels") else control.setHeaderLabels
    method([str(text) for text in texts])
    for column, text in enumerate(texts):
        if isinstance(text, LocalizedText):
            header = control.horizontalHeaderItem(column) if hasattr(control, "horizontalHeaderItem") else control.headerItem()
            if isinstance(header, QTableWidgetItem):
                header.setData(SOURCE_ROLE, text.message)
            else:
                header.setData(column, SOURCE_ROLE, text.message)


def add_tab(control, *args):
    index = control.addTab(*(str(value) if isinstance(value, LocalizedText) else value for value in args))
    text = next((value for value in args if isinstance(value, LocalizedText)), None)
    if text is not None:
        remember(control.widget(index), "languageTabSource", text)
    return index
