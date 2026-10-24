"""Application captions with explicit sources; user content is never translated."""

from dataclasses import dataclass, replace
import re

from .language_catalog import TEXTS as EXTRA_TEXTS, TEMPLATES

LANGUAGE = "de"
TEXTS = {
    'Excel / CSV laden': 'Load Excel / CSV',
    'Alle Quellspalten bleiben verfügbar. Im Builder kannst du Dateien direkt mit „Excel / CSV laden“ importieren. Ungültige Zeilen in der Quelldatei korrigieren und erneut laden.': 'All source columns remain available. In the builder, import files directly with “Load Excel / CSV”. Correct invalid rows in the source file and load it again.',
    'Eine Nachricht je Datenzeile. Erst Versandkopien prüfen und freigeben, dann den Gruppenversand starten.': 'One message per data row. Review and approve the prepared messages before starting group delivery.',
    'Datenquelle (Builder / Word Replace)': 'Data source (builder / Word Replace)',
    'Mehrere Bewerbungsziele an dieselbe E-Mail-Adresse zulassen': 'Allow several application targets at the same email address',
    'Mehrere Nachrichten an dieselbe Adresse sind für diese Builder-Gruppe ausdrücklich zugelassen. Jede Datenzeile bleibt ein eigener Auftrag.': 'Multiple messages to the same address are explicitly allowed for this builder group. Each data row remains a separate job.',
    "Übersicht / Projekte": "Overview / projects", "Arbeitsbereich": "Workspace",
    "Einstellungen": "Settings", "E-Mail-Builder": "Email builder", "Nachfassen": "Follow-ups",
    "Datenimport": "Data import", "E-Mail": "Email", "Bewerbungen": "Applications",
    "Unternehmen": "Companies", "Kontakte": "Contacts", "Bewerberprofile": "Applicant profiles",
    "Stellen": "Jobs", "Vorlagen": "Templates", "Dokumente": "Documents",
    "Neues Projekt": "New project", "Projekt öffnen": "Open project", "Öffnen": "Open",
    "Schließen": "Close", "Aktualisieren": "Refresh", "Projektordner": "Project folder",
    "Dunkles Design": "Dark theme", "Helles Design": "Light theme", "Tastaturhilfe": "Keyboard help",
    "Backup wiederherstellen": "Restore backup", "Projektbackup wiederherstellen": "Restore project backup",
    "Design / Zeitzone": "Appearance / timezone", "Design": "Theme", "Akzentfarbe": "Accent colour",
    "Eigene Farbe …": "Custom colour …", "Anzeigezeitzone": "Display timezone",
    "Arbeitsbereich / Listen": "Workspace / lists", "Neue Projekte": "New projects",
    "Projekt-Startansicht": "Project start page", "Übersicht": "Overview", "E-Mail-Aufträge": "Email orders",
    "Zeilen je Seite": "Rows per page", "Abwechselnde Zeilenfarben": "Alternating row colours",
    "Text in Tabellen umbrechen": "Wrap table text", "Kompakte Tabellenzeilen": "Compact table rows",
    "E-Mail-Vorgaben": "Email defaults", "Bevorzugte Konto-Adresse": "Preferred account address",
    "Bevorzugter Signaturname": "Preferred signature name", "Versandzeitzone": "Delivery timezone",
    "Fenster ab (HH:mm)": "Window starts (HH:mm)", "Fenster bis (HH:mm)": "Window ends (HH:mm)",
    "Nachrichtenformat": "Message format", "Text": "Plain text", "Neue Versandplanung": "New delivery plan",
    "Nur lokale Entwürfe": "Local drafts only", "Sofort nach Freigabe": "After approval", "Geplant": "Scheduled",
    "Abstand in Sekunden": "Interval in seconds", "Tagesbudget je Konto / Projekt": "Daily budget per account / project",
    "Backup / Wiederherstellung": "Backup / restore", "Backup-Ziel": "Backup destination",
    "Sicherungen aufbewahren (0 = alle)": "Backups to keep (0 = all)", "Standardformat": "Default format",
    "Standardordner": "Default folder", "CSV-Trennzeichen": "CSV delimiter", "CSV-Zeichensatz": "CSV encoding",
    "Semikolon": "Semicolon", "Komma": "Comma", "Tabulator": "Tab", "Wählen …": "Choose …",
    "Groß-/Kleinschreibung beachten": "Case sensitive", "Nur ganze Wörter": "Whole words only",
    "Fehlende Werte": "Missing values", "Ausgabe sperren": "Block output", "Originaltext behalten": "Keep original text",
    "Standardausgabe": "Default output", "Ausgabeordner": "Output folder", "Ersatzformatierung": "Replacement style",
    "Ersten Text-Run übernehmen": "Use first text run style", "Absatzstandard ohne direkte Formatierung": "Paragraph default style",
    "Fett": "Bold", "Kursiv": "Italic", "Dateinamensmuster": "Filename pattern",
    "LibreOffice-Programmdatei": "LibreOffice executable", "PDF-Zeitlimit je Datei": "PDF timeout per file",
    "Standardbausteine für neue Abläufe": "Default blocks for new workflows", "Raster anzeigen": "Show grid",
    "Bausteine am Raster einrasten": "Snap blocks to grid", "Standardzoom": "Default zoom",
    "Sichern nach Eingabepause": "Save after idle period", "Eigenschaften / Vorschau anzeigen": "Show properties / preview",
    "Kompakte Werkzeugleiste": "Compact toolbar", "Palettenbreite": "Palette width", "Eigenschaftenbreite": "Properties width",
    "Benachrichtigungen": "Notifications", "Anzeigedauer": "Display duration", "Informationen anzeigen": "Show information",
    "Erfolgsmeldungen anzeigen": "Show success notifications", "Fehler bis zum ausdrücklichen Schließen anzeigen": "Keep errors until dismissed",
    "Reduzierte Bewegung · Animationen ausschalten": "Reduced motion · disable animations",
    "Speichern und anwenden": "Save and apply", "Änderungen verwerfen": "Discard changes",
    "Standardwerte": "Defaults", "Neu laden": "Reload", "Speichern": "Save", "Abbrechen": "Cancel",
    "Zurück": "Back", "Weiter": "Next", "Suchen": "Search", "Bearbeiten": "Edit", "Löschen": "Delete",
    "Duplizieren": "Duplicate", "Importieren": "Import", "Neue Version": "New version", "Verwenden": "Use",
    "Senden": "Send", "Versand planen": "Schedule delivery", "Entwurf speichern": "Save draft",
    "Keine Signatur": "No signature", "Absender": "Sender", "Signatur": "Signature", "Betreff": "Subject",
    "Name": "Name", "Telefon": "Phone", "Adresse": "Address", "Datei": "File", "Erstellt": "Created",
    "Übergeordneter Ordner": "Parent folder", "Neuer Projektordner": "New project folder",
    "Zielordner wählen …": "Choose destination …", "Prüfen und wiederherstellen": "Verify and restore",
    "Bausteinpalette in breiten Fenstern anzeigen": "Show block palette in wide windows",
    "Arbeitsstand automatisch sichern / wiederherstellen": "Automatically save / restore workspace",
    "Bewerbungen & Dokumente": "Applications & documents", "Bereit": "Ready",
    "Keine ungespeicherten Änderungen.": "No unsaved changes.", "Ungespeicherte Änderungen": "Unsaved changes",
    "Diagnosebericht exportieren …": "Export diagnostic report …",
    "Vorgaben erzeugen keine Versandfreigabe. Projektvorgaben haben Vorrang; bestehende Entwürfe bleiben erhalten. Gleiche Fenstergrenzen = ganzer Tag. Konto und Signatur müssen im Projekt vorhanden sein.": "Defaults do not approve delivery. Project defaults take precedence; existing drafts are preserved. Identical window limits mean all day. The account and signature must exist in the project.",
}


@dataclass(frozen=True)
class Message:
    source: str
    arguments: tuple = ()
    template: bool = False
    context: str | None = None


def render(message, language=None):
    language = language or LANGUAGE
    source = message.source
    if language == "en":
        source = TEMPLATES.get(source, source) if message.template else EXTRA_TEXTS.get(source, TEXTS.get(source, source))
        if message.context == 'field' and message.source == 'Unternehmen':
            source = 'Company'
    if message.template:
        def argument(match):
            value = message.arguments[int(match.group(1))]
            return render(value, language) if isinstance(value, Message) else str(value)
        source = re.sub(r"\{(\d+)\}", argument, source)
    return source


class LocalizedText(str):
    def __new__(cls, message):
        value = super().__new__(cls, render(message))
        value.message = message
        return value

    def __reduce_ex__(self, protocol):
        # Copying a preview keeps its rendered snapshot, even after a language switch.
        return _restore_localized_text, (str(self), self.message)


def _restore_localized_text(value, message):
    result = str.__new__(LocalizedText, value)
    result.message = message
    return result


def translate(text, *, context=None):
    if isinstance(text, Message):
        return LocalizedText(replace(text, context=context) if context is not None else text)
    if isinstance(text, LocalizedText):
        return LocalizedText(replace(text.message, context=context) if context is not None else text.message)
    return LocalizedText(Message(str(text), context=context))


def format_text(source, *arguments):
    values = tuple(value.message if isinstance(value, LocalizedText) else str(value) for value in arguments)
    return LocalizedText(Message(source, values, True))


def join_text(separator, values):
    """Join caption fragments while retaining each fragment's owned metadata."""
    values = tuple(values)
    return format_text(separator.join('{' + str(index) + '}' for index in range(len(values))), *values)


def set_language(language):
    global LANGUAGE
    if language not in ("de", "en"):
        raise ValueError(translate('Unbekannte Sprache.'))
    LANGUAGE = language


def get_language():
    return LANGUAGE


def translate_tree(root):
    """Re-render explicitly marked captions without touching editable contents."""
    from PySide6.QtWidgets import (QWidget, QComboBox, QTabWidget, QTableWidget, QTreeWidget, QListWidget,
                                  QDateTimeEdit, QCalendarWidget, QDialogButtonBox)
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QAction
    from .ui.localization import SOURCE_ROLE

    def translated(source):
        return render(source if isinstance(source, Message) else Message(str(source)))

    for control in [root, *root.findChildren(QWidget), *root.findChildren(QAction)]:
        if isinstance(control, (QDateTimeEdit, QCalendarWidget)):
            control.setLocale(QLocale('en_GB' if LANGUAGE == 'en' else 'de_DE'))
        if isinstance(control, QDialogButtonBox):
            for role, source in ((control.StandardButton.Close, 'Schließen'),
                                 (control.StandardButton.Cancel, 'Abbrechen'),
                                 (control.StandardButton.Save, 'Speichern'),
                                 (control.StandardButton.Yes, 'Ja'), (control.StandardButton.No, 'Nein')):
                button = control.button(role)
                if button and button.property('languageSource') is None:
                    button.setProperty('languageSource', Message(source))
        properties = (("languageSource", "setText"), ("languageTitleSource", "setTitle"),
                      ("languageSubtitleSource", "setSubTitle"),
                      ("languageWindowSource", "setWindowTitle"), ("languageTooltipSource", "setToolTip"),
                      ("languagePlaceholderSource", "setPlaceholderText"), ("languageSuffixSource", "setSuffix"),
                      ("languageFormatSource", "setFormat"),
                      ("languagePlainTextSource", "setPlainText"),
                      ("languageAccessibleNameSource", "setAccessibleName"),
                      ("languageAccessibleDescriptionSource", "setAccessibleDescription"))
        for property_name, setter in properties:
            source = control.property(property_name)
            if source is not None and hasattr(control, setter):
                getattr(control, setter)(translated(source))
        if isinstance(control, QTabWidget):
            for index in range(control.count()):
                source = control.widget(index).property("languageTabSource")
                if source is not None:
                    control.setTabText(index, translated(source))
        if isinstance(control, QComboBox):
            editor = control.lineEdit() if control.isEditable() else None
            preserve = bool(editor and (editor.isModified() or editor.text() != control.itemText(control.currentIndex())))
            # Qt selection offsets count UTF-16 units, including two units for emoji.
            saved = (editor.text(), editor.cursorPosition(), editor.selectionStart(),
                     len(editor.selectedText().encode('utf-16-le', errors='surrogatepass')) // 2) if preserve else None
            blocked = control.blockSignals(True)
            editor_blocked = editor.blockSignals(True) if editor else None
            try:
                for index in range(control.count()):
                    source = control.itemData(index, SOURCE_ROLE)
                    if source is not None:
                        control.setItemText(index, translated(source))
                if saved:
                    editor.setText(saved[0]);editor.setCursorPosition(saved[1])
                    if saved[2] >= 0:editor.setSelection(saved[2], saved[3])
                    editor.setModified(True)
            finally:
                if editor:editor.blockSignals(editor_blocked)
                control.blockSignals(blocked)
        if isinstance(control, (QTableWidget, QTreeWidget, QListWidget)):
            blocked = control.blockSignals(True)
            try:
                if isinstance(control, QTableWidget):
                    for column in range(control.columnCount()):
                        item = control.horizontalHeaderItem(column)
                        if item and item.data(SOURCE_ROLE) is not None:
                            item.setText(translated(item.data(SOURCE_ROLE)))
                    for row in range(control.rowCount()):
                        for column in range(control.columnCount()):
                            item = control.item(row, column)
                            if item and item.data(SOURCE_ROLE) is not None:
                                item.setText(translated(item.data(SOURCE_ROLE)))
                elif isinstance(control, QListWidget):
                    for index in range(control.count()):
                        item = control.item(index)
                        if item.data(SOURCE_ROLE) is not None:
                            item.setText(translated(item.data(SOURCE_ROLE)))
                else:
                    def visit(item):
                        for column in range(control.columnCount()):
                            source = item.data(column, SOURCE_ROLE)
                            if source is not None:item.setText(column, translated(source))
                        for index in range(item.childCount()):visit(item.child(index))
                    visit(control.headerItem())
                    for index in range(control.topLevelItemCount()):visit(control.topLevelItem(index))
            finally:
                control.blockSignals(blocked)


def install_dialog_translation(application):
    from PySide6.QtCore import QObject, QEvent
    class CaptionFilter(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Show and hasattr(watched, "isWindow") and watched.isWindow():
                translate_tree(watched)
            return False
    if not hasattr(application, "_emailcenter_language_filter"):
        application._emailcenter_language_filter = CaptionFilter(application)
        application.installEventFilter(application._emailcenter_language_filter)
