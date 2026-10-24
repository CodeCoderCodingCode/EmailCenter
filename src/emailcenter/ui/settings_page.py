"""Persistent app preferences grouped by workflow."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout,
                              QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..preferences import Preferences
from ..appearance import THEMES
from ..language import translate, translate_tree
from ..shortcuts import SHORTCUTS, default_shortcuts, validate_shortcuts, CANVAS_SHORTCUTS, default_canvas_shortcuts, validate_canvas_shortcuts
from .pages import button, label
from .responsive import ActionFlowLayout


class SettingsPage(QWidget):
    save_requested = Signal(object)
    reload_requested = Signal()
    diagnostic_requested = Signal()

    def __init__(self, preferences, warning=None):
        super().__init__()
        self.saved, self.controls, self.shortcut_controls = preferences, {}, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label(_ui_tr('Einstellungen'), 'pageTitle'))
        self.notice = label(warning or "", "muted")
        self.notice.setVisible(bool(warning))
        layout.addWidget(self.notice)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        appearance = self.add_tab("Design / Zeitzone")
        appearance.addRow(label(_ui_tr('Sprache für Oberfläche und App-Meldungen. Eigene Texte, Projektdaten und importierte Werte bleiben unverändert.'), 'muted'))
        self.combo(appearance, "language", "Sprache / Language", [("Deutsch", "de"), ("English", "en")])
        self.theme = self.combo(appearance, "theme", "Design", [(spec["title"], key) for key, spec in THEMES.items()])
        self.accent = QComboBox()
        for title, color in (("Blau", "#2862c4"), ("Grün", "#087f5b"), ("Violett", "#7045b8"), ("Orange", "#b45309")):
            _ui_locale.add_item(self.accent, _ui_tr(title), color)
        self.controls["accent"] = self.accent
        accent_row = QHBoxLayout()
        accent_row.addWidget(self.accent, 1)
        accent_row.addWidget(button(_ui_tr('Eigene Farbe …'), self.choose_color))
        _ui_locale.add_row(appearance, _ui_tr('Akzentfarbe'), accent_row)
        motion = _ui_locale.widget(QCheckBox, _ui_tr('Reduzierte Bewegung · Animationen ausschalten'))
        self.controls["reduced_motion"] = motion
        appearance.addRow(motion)
        self.combo(appearance, 'transition_style', 'Seitenübergang', [('Nach Design', 'theme'), ('Überblenden', 'fade'), ('Gleiten', 'slide'), ('Zoom', 'zoom'), ('Aus', 'none')])
        self.spin(appearance, 'animation_ms', 'Animationsdauer (ms)', 60, 1000)
        self.check(appearance, 'hover_feedback', 'Animierte Reaktion auf Maus und Fokus')
        self.spin(appearance, 'builder_preview_delay_ms', 'Builder-Reaktionszeit (ms)', 0, 2000)
        self.zone = QComboBox()
        self.zone.setEditable(True)
        _ui_locale.add_items(self.zone, [_ui_tr('Europe/Berlin'), _ui_tr('UTC'), _ui_tr('Europe/London'), _ui_tr('America/New_York')])
        self.controls["timezone_id"] = self.zone
        _ui_locale.add_row(appearance, _ui_tr('Anzeigezeitzone'), self.zone)
        appearance.addRow(label(_ui_tr('Termine und Heute-Filter verwenden diese Zeitzone. Neue Erinnerungen übernehmen sie als Vorgabe.'), 'muted'))
        workspace = self.add_tab("Arbeitsbereich / Listen")
        self.check(workspace, 'guided_workspace', 'Geführte Schritte im Arbeitsbereich')
        self.check(workspace, 'tooltips_enabled', 'Tooltips anzeigen')
        self.combo(workspace, "workspace_mode", "Neue Projekte", [("Bewerbungen", "applications"), ("E-Mail-Aufträge", "mail")])
        self.combo(workspace, "start_page", "Projekt-Startansicht", [("Arbeitsbereich", "workspace"), ("Übersicht", "overview"), ("E-Mail-Builder", "builder"), ("Word Replace", "word_replace")])
        self.spin(workspace, "list_page_size", "Zeilen je Seite", 10, 200)
        for key, caption in (("list_alternating_rows", "Abwechselnde Zeilenfarben"), ("list_word_wrap", "Text in Tabellen umbrechen"), ("list_compact_rows", "Kompakte Tabellenzeilen")):
            self.check(workspace, key, caption)
        mail = self.add_tab("E-Mail-Vorgaben")
        for key, caption in (("mail_account_email", "Bevorzugte Konto-Adresse"), ("mail_signature_name", "Bevorzugter Signaturname"), ("mail_timezone_id", "Versandzeitzone"), ("mail_window_start", "Fenster ab (HH:mm)"), ("mail_window_end", "Fenster bis (HH:mm)")):
            control = QLineEdit()
            self.controls[key] = control
            _ui_locale.add_row(mail, _ui_tr(caption), control)
        self.combo(mail, "mail_body_format", "Nachrichtenformat", [("Text", "plain"), ("HTML", "html")])
        self.combo(mail, "mail_delivery_mode", "Neue Versandplanung", [("Nur lokale Entwürfe", "drafts"), ("Sofort nach Freigabe", "now"), ("Geplant", "scheduled")])
        self.spin(mail, "mail_interval_seconds", "Abstand in Sekunden", 1, 3600)
        self.spin(mail, "mail_daily_budget", "Tagesbudget je Konto / Projekt", 1, 10000)
        mail.addRow(label(_ui_tr('Vorgaben erzeugen keine Versandfreigabe. Projektvorgaben haben Vorrang; bestehende Entwürfe bleiben erhalten. Gleiche Fenstergrenzen = ganzer Tag. Konto und Signatur müssen im Projekt vorhanden sein.'), 'muted'))
        backup = self.add_tab("Backup / Wiederherstellung")
        self.path(backup, "backup_directory", "Backup-Ziel")
        self.spin(backup, "backup_retention", "Sicherungen aufbewahren (0 = alle)", 0, 1000)
        backup.addRow(label(_ui_tr('Leer = backups im Projekt. Aufbewahrung betrifft ausschließlich unveränderte, verifizierte Sicherungen dieses Projekts im gewählten Ziel. Wiederherstellung legt einen neuen Projektordner an.'), 'muted'))
        backup.addRow(button(_ui_tr('Diagnosebericht exportieren …'), self.diagnostic_requested.emit))
        self.backup_privacy_label=label(_ui_tr('Projektbackups sind unverschlüsselte ZIP-Dateien mit Projektdaten, Nachrichten und Dokumenten. App-eigene Gmail-Zugangstokens liegen getrennt im Windows-Tresor.'), 'muted')
        backup.addRow(self.backup_privacy_label)
        backup.addRow(label(_ui_tr('Der Bericht enthält Laufzeit-/Paketversionen, Datenbankprüfungen und Statusanzahlen. Keine Nachrichten, Adressen, Dateien, Projektpfade oder Zugangsdaten. Er wird nur lokal gespeichert.'), 'muted'))
        export = self.add_tab("Export")
        self.combo(export, "export_format", "Standardformat", [("CSV", "csv"), ("Excel", "xlsx")])
        self.path(export, "export_directory", "Standardordner")
        self.combo(export, "csv_delimiter", "CSV-Trennzeichen", [("Semikolon", ";"), ("Komma", ","), ("Tabulator", "\t")])
        self.combo(export, "csv_encoding", "CSV-Zeichensatz", [("UTF-8 mit BOM (Excel)", "utf-8-sig"), ("UTF-8", "utf-8"), ("Windows-1252", "cp1252"), ("UTF-16", "utf-16")])
        export.addRow(label(_ui_tr('Ein leerer Ordner verwendet exports im aktuellen Projekt. Filter und Spalten werden vor jedem Export geprüft.'), 'muted'))
        word = self.add_tab("Word Replace")
        for key, caption in (("word_replace_case_sensitive", "Groß-/Kleinschreibung beachten"), ("word_replace_whole_words", "Nur ganze Wörter")):
            control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
            self.controls[key] = control
            word.addRow(control)
        self.combo(word, "word_replace_missing", "Fehlende Werte", [("Ausgabe sperren", "error"), ("Originaltext behalten", "keep")])
        self.combo(word, "word_replace_format", "Standardausgabe", [("DOCX", "docx"), ("PDF", "pdf")])
        self.path(word, "word_replace_directory", "Ausgabeordner")
        self.combo(word, "word_replace_style", "Ersatzformatierung", [("Ersten Text-Run übernehmen", "first"), ("Absatzstandard ohne direkte Formatierung", "plain"), ("Fett", "bold"), ("Kursiv", "italic")])
        pattern = QLineEdit()
        pattern.setMaxLength(200)
        _ui_locale.set_placeholder(pattern, _ui_tr('{prefix}-{number:03d}-{company.name}'))
        self.controls["word_replace_filename_pattern"] = pattern
        _ui_locale.add_row(word, _ui_tr('Dateinamensmuster'), pattern)
        word.addRow(label(_ui_tr('Leer = bisherige Namen. Muster ohne Dateiendung: {prefix}, {number:03d}, {name} und Datenfelder. Fehlende Felder oder doppelte Namen sperren die Ausgabe. Formatierungsregeln ändern nur Ersatztext.'), 'muted'))
        self.path(word, "libreoffice_path", "LibreOffice-Programmdatei", executable=True)
        timeout = QSpinBox()
        timeout.setRange(10, 600)
        _ui_locale.set_suffix(timeout, _ui_tr(' Sekunden'))
        self.controls["conversion_timeout"] = timeout
        _ui_locale.add_row(word, _ui_tr('PDF-Zeitlimit je Datei'), timeout)
        word.addRow(label(_ui_tr('Leeres Programmfeld sucht LibreOffice automatisch. PDF benötigt eine lokale Installation. Originale werden beim Ersetzen erhalten.'), 'muted'))
        keys = self.add_tab("Hotkeys")
        for action, (caption, default) in SHORTCUTS.items():
            control = QLineEdit()
            control.setMaxLength(80)
            _ui_locale.set_placeholder(control, _ui_format('{0} · leer = deaktiviert', default))
            self.shortcut_controls[action] = control
            _ui_locale.add_row(keys, _ui_tr(caption), control)
        keys.addRow(button(_ui_tr('Nur Hotkeys auf Standards setzen'), self.reset_shortcuts))
        keys.addRow(label(_ui_tr('Einzelkombinationen: Ctrl/Strg, Alt, Shift + Buchstabe/Ziffer oder F1–F12. Texteingabekürzel bleiben reserviert. Speichern betrifft nur das aktive Formular; Versand/Freigabe besitzen kein Tastenkürzel.'), 'muted'))
        keys.addRow(label(_ui_tr('Builder-Zeichenfläche · nur bei Fokus auf der Zeichenfläche aktiv'), 'pageTitle'))
        self.canvas_controls = {}
        for action, (caption, default) in CANVAS_SHORTCUTS.items():
            control = QLineEdit()
            control.setMaxLength(80)
            _ui_locale.set_placeholder(control, _ui_format('{0} · leer = deaktiviert', default))
            self.canvas_controls[action] = control
            _ui_locale.add_row(keys, _ui_tr(caption), control)
        keys.addRow(label(_ui_tr('Baustein wählen → Stecker wählen → Ausgang aktivieren → Zielbaustein und Eingang wählen → erneut aktivieren. Escape bricht ab. App-Hotkeys dürfen nicht doppelt belegt werden.'), 'muted'))
        builder = self.add_tab("E-Mail-Builder")
        from ..email_builder import NODE_TYPES
        self.default_blocks = QListWidget()
        self.default_blocks.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.default_blocks.setMaximumHeight(190)
        for kind in ("text", "description", "paragraph", "heading", "html", "greeting", "closing", "separator", "list"):
            item = _ui_locale.item(QListWidgetItem, _ui_tr(NODE_TYPES[kind]["title"]))
            item.setData(Qt.ItemDataRole.UserRole, kind)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.default_blocks.addItem(item)
        self.controls["builder_default_blocks"] = self.default_blocks
        self.default_blocks.itemChanged.connect(self.update_dirty)
        self.default_blocks.model().rowsMoved.connect(self.update_dirty)
        _ui_locale.add_row(builder, _ui_tr('Standardbausteine für neue Abläufe'), self.default_blocks)
        builder.addRow(label(_ui_tr('Datenquelle, Betreff und E-Mail-Ausgabe werden immer verbunden ergänzt. Undo/Redo wird zusammen mit dem Arbeitsstand gesichert; maximal 100 Schritte, bei großen Graphen weniger.'), 'muted'))
        for key, caption in (("builder_grid", "Raster anzeigen"), ("builder_snap", "Bausteine am Raster einrasten"), ("builder_autosave", "Arbeitsstand automatisch sichern / wiederherstellen")):
            control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
            self.controls[key] = control
            builder.addRow(control)
        zoom = QSpinBox()
        zoom.setRange(25, 250)
        zoom.setSuffix(" %")
        self.controls["builder_zoom"] = zoom
        _ui_locale.add_row(builder, _ui_tr('Standardzoom'), zoom)
        interval = QSpinBox()
        interval.setRange(1, 60)
        _ui_locale.set_suffix(interval, _ui_tr(' Sekunden'))
        self.controls["builder_autosave_seconds"] = interval
        _ui_locale.add_row(builder, _ui_tr('Sichern nach Eingabepause'), interval)
        for key, caption in (("builder_show_palette", "Bausteinpalette in breiten Fenstern anzeigen"), ("builder_show_inspector", "Eigenschaften / Vorschau anzeigen"), ("builder_compact_tools", "Kompakte Werkzeugleiste")):
            control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
            self.controls[key] = control
            builder.addRow(control)
        for key, caption, minimum, maximum in (("builder_palette_width", "Palettenbreite", 150, 320), ("builder_inspector_width", "Eigenschaftenbreite", 220, 700)):
            control = QSpinBox()
            control.setRange(minimum, maximum)
            _ui_locale.set_suffix(control, _ui_tr(' px'))
            self.controls[key] = control
            _ui_locale.add_row(builder, _ui_tr(caption), control)
        notifications = self.add_tab("Benachrichtigungen")
        duration = QSpinBox()
        duration.setRange(2, 30)
        _ui_locale.set_suffix(duration, _ui_tr(' Sekunden'))
        self.controls["toast_seconds"] = duration
        _ui_locale.add_row(notifications, _ui_tr('Anzeigedauer'), duration)
        for key, caption in (("toast_info", "Informationen anzeigen"), ("toast_success", "Erfolgsmeldungen anzeigen"), ("toast_persistent_errors", "Fehler bis zum ausdrücklichen Schließen anzeigen")):
            control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
            self.controls[key] = control
            notifications.addRow(control)
        notifications.addRow(label(_ui_tr('Warnungen und Fehler bleiben aktiviert. Reduzierte Bewegung deaktiviert auch die Toastanimation. Ein offener dauerhafter Fehler wird von Erfolgsmeldungen nicht verdrängt.'), 'muted'))
        builder.addRow(label(_ui_tr('Autosicherung behält auch unfertige Eingaben, Konto/Planung und Ansicht. Sie erzeugt keine benannte Version und keine Versandfreigabe. Beim Schließen/Projektwechsel wird der letzte Stand gesichert.'), 'muted'))
        builder.addRow(label(_ui_tr('Zeichenfläche: mittlere Maustaste verschiebt die Ansicht; Ctrl+Mausrad zoomt. Tastaturbelegungen für Bausteine, Stecker und Verbindungen unter Hotkeys; F1 zeigt die aktuelle Belegung. Versionen ausdrücklich speichern; PDF-Konverter unter Word Replace.'), 'muted'))
        self.state = label("", "muted")
        layout.addWidget(self.state)
        actions = ActionFlowLayout()
        self.save_button = button(_ui_tr('Speichern und anwenden'), lambda: self.save_requested.emit(self.values()), primary=True)
        self.discard_button = button(_ui_tr('Änderungen verwerfen'), self.discard)
        self.defaults_button = button(_ui_tr('Standardwerte'), lambda: self.populate(Preferences()))
        self.reload_button = button(_ui_tr('Neu laden'), self.reload_requested.emit)
        for control in (self.save_button, self.discard_button, self.defaults_button, self.reload_button):
            actions.addWidget(control)
        layout.addLayout(actions)
        self.accept_preferences(preferences, warning=warning)
        for control in self.controls.values():
            if isinstance(control, QComboBox):
                control.currentTextChanged.connect(self.update_dirty)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self.update_dirty)
            elif isinstance(control, QSpinBox):
                control.valueChanged.connect(self.update_dirty)
            elif isinstance(control, QLineEdit):
                control.textChanged.connect(self.update_dirty)
        for control in self.shortcut_controls.values():
            control.textChanged.connect(self.update_dirty)
        for control in self.canvas_controls.values():
            control.textChanged.connect(self.update_dirty)

    def add_tab(self, title):
        scroll, body = QScrollArea(), QWidget()
        scroll.setWidgetResizable(True)
        form = QFormLayout(body)
        form.setContentsMargins(20, 20, 20, 20)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll.setWidget(body)
        _ui_locale.add_tab(self.tabs, scroll, _ui_tr(title))
        return form

    def combo(self, form, key, caption, choices):
        control = QComboBox()
        for title, value in choices:
            _ui_locale.add_item(control, _ui_tr(title), value)
        self.controls[key] = control
        _ui_locale.add_row(form, _ui_tr(caption), control)
        return control

    def spin(self, form, key, caption, minimum, maximum):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        self.controls[key] = control
        _ui_locale.add_row(form, _ui_tr(caption), control)

    def check(self, form, key, caption):
        control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
        self.controls[key] = control
        form.addRow(control)

    def path(self, form, key, caption, *, executable=False):
        control, row = QLineEdit(), QHBoxLayout()
        self.controls[key] = control
        row.addWidget(control, 1)
        def choose():
            value = QFileDialog.getOpenFileName(self, caption)[0] if executable else QFileDialog.getExistingDirectory(self, caption, control.text())
            if value:
                control.setText(value)
        row.addWidget(button(_ui_tr('Wählen …'), choose))
        _ui_locale.add_row(form, _ui_tr(caption), row)

    def values(self):
        result = {}
        for key, control in self.controls.items():
            if isinstance(control, QComboBox):
                result[key] = control.currentText().strip() if key == "timezone_id" else control.currentData()
            elif isinstance(control, QCheckBox):
                result[key] = control.isChecked()
            elif isinstance(control, QSpinBox):
                result[key] = control.value()
            elif isinstance(control, QListWidget):
                result[key] = [control.item(i).data(Qt.ItemDataRole.UserRole) for i in range(control.count()) if control.item(i).checkState() == Qt.CheckState.Checked]
            else:
                result[key] = control.text().strip()
        return {**result, "shortcuts": {action: control.text().strip() for action, control in self.shortcut_controls.items()},
                "canvas_shortcuts": {action: control.text().strip() for action, control in self.canvas_controls.items()}}

    def populate_values(self, values):
        for key, control in self.controls.items():
            control.blockSignals(True)
            value = values[key]
            if isinstance(control, QComboBox):
                if key == "timezone_id":
                    control.setCurrentText(value)
                else:
                    index = control.findData(value)
                    if index < 0:
                        _ui_locale.add_item(control, _ui_format('Eigene Farbe: {0}', value), value)
                        index = control.count() - 1
                    control.setCurrentIndex(index)
            elif isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QSpinBox):
                control.setValue(value)
            elif isinstance(control, QListWidget):
                control.model().blockSignals(True)
                items = [control.takeItem(0) for _ in range(control.count())]
                order = value + [item.data(Qt.ItemDataRole.UserRole) for item in items if item.data(Qt.ItemDataRole.UserRole) not in value]
                by_kind = {item.data(Qt.ItemDataRole.UserRole): item for item in items}
                for kind in order:
                    control.addItem(by_kind[kind])
                for i in range(control.count()):
                    item = control.item(i)
                    item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in value else Qt.CheckState.Unchecked)
                control.model().blockSignals(False)
            else:
                control.setText(value)
            control.blockSignals(False)
        for action, control in self.shortcut_controls.items():
            control.blockSignals(True)
            control.setText(values["shortcuts"][action])
            control.blockSignals(False)
        for action, control in self.canvas_controls.items():
            control.blockSignals(True)
            control.setText(values["canvas_shortcuts"][action])
            control.blockSignals(False)
        self.update_dirty()

    def populate(self, preferences):
        self.populate_values(preferences.values())

    def update_dirty(self):
        try:
            validate_shortcuts(self.values()["shortcuts"])
            validate_canvas_shortcuts(self.values()["canvas_shortcuts"], validate_shortcuts(self.values()["shortcuts"]))
            _ui_locale.set_text(self.state, translate('Ungespeicherte Änderungen' if self.values() != self.saved.values() else 'Keine ungespeicherten Änderungen.'))
        except ValueError as error:
            _ui_locale.set_text(self.state, str(error))

    def reset_shortcuts(self):
        for action, value in default_shortcuts().items():
            self.shortcut_controls[action].setText(value)
        for action, value in default_canvas_shortcuts().items():
            self.canvas_controls[action].setText(value)

    def accept_preferences(self, preferences, *, preserve_edits=False, warning=None):
        draft, previous = self.values(), self.saved.values()
        self.saved = preferences
        values = preferences.values()
        if preserve_edits:
            for key in values:
                if key != "theme" and draft[key] != previous[key]:
                    values[key] = draft[key]
        self.populate_values(values)
        translate_tree(self)
        _ui_locale.set_text(self.notice, warning or '')
        self.notice.setVisible(bool(warning))

    def discard(self):
        self.populate(self.saved)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.accent.currentData()), self, str(_ui_tr('Akzentfarbe wählen')))
        if color.isValid():
            value = color.name()
            index = self.accent.findData(value)
            if index < 0:
                _ui_locale.add_item(self.accent, _ui_format('Eigene Farbe: {0}', value), value)
                index = self.accent.count() - 1
            self.accent.setCurrentIndex(index)
