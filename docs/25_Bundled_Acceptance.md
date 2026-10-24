# Gebündelte manuelle Abnahme

Aktuelles Paket: [Abschluss A1–A3](35_Completion_A1_A3.md); Umsetzung samt echten lokalen Dateien geprüft, native gemeinsame Abnahme offen.

Die [finale TODO](34_Final_TODO.md) bündelt diese historischen Pakete in A1–A7.
Bereits belegte Prüfungen bleiben erledigt; offene praktische Prüfungen werden
dort abgeschlossen. Installer und Einführung für andere Nutzer folgen danach in B5.

Stand: 12.10.2026. Auf Wunsch werden mehrere Zwischenabnahmen gesammelt.
Die folgenden Punkte sind **noch nicht manuell abgenommen**. Weiterentwicklung
läuft weiter; diese Prüfliste verlangt keine Entscheidung während jedes Teilschritts.

## Automatisch geprüft

- [x] Gesamtsuite: 482 Tests, 481 bestanden; ein optionaler nativer Vault-Test übersprungen.
- [x] 36 neue Serviceprüfungen für Bibliothek, Export und Word Replace.
- [x] Neun neue GUI-Prüfungen, vier zusätzliche Einstellungsprüfungen und Migration 008.
- [x] Geänderte Quellen, Dateischutz, Abbruch, Rollback und Wiederherstellung bei Dateisperren.
- [x] Acht Hotkey-Backendtests und fünf Qt-Tests; Navigation/Suchen/Speichern mit Tastaturereignissen.
- [x] Ansichten mit Testdaten erzeugt und angesehen; Word-Aktionen auch bei 820 × 600 geprüft.
- [x] 31 Builder-Serviceprüfungen, 17 Qt-Prüfungen und Schema-8→9-Upgrade mit Datenerhalt.
- [x] Semantische Textarten, persönliche Vorschauen, atomare Bulk-Planung und Fortsetzen ohne doppelte Aufträge.
- [x] Bild-/DOCX-/PDF-Vorschau, HTML ohne externe Ressourcen, mittlere Maustaste und acht Themes mit vier Paaren geprüft.
- [x] Video-Anzeige ohne Autoplay und verständlicher Fehler bei unlesbarem Container; echte Codecs bleiben manuell offen.
- [x] Builder-Ansichten in Hell/Dunkel angesehen; festes Aktionsfeld bei 820 × 600 geprüft.
- [x] Zehn neue Serviceprüfungen für Arbeitsstände, Backups, Anordnung und Links/Buttons/Listen.
- [x] Neun neue Qt-Prüfungen für Autosicherung, Weiterarbeiten, manuelle Sicherungswarteschlange, Projektwechsel/Schließen, Neustart und Konflikte.
- [x] Schema-9→10-Upgrade erhält Versionen/Entwürfe; neue Autosicherungseinstellungen laden ältere Dateien weiter.
- [x] Neun neue Renderer-/Autoload-Qt-Prüfungen: fertige Mail/Signatur, Live-Skizze, Canvas-Miniaturen, Bild/PDF/Video/DOCX, Zeilenwechsel, Dateikonflikte und begrenzter Cache.
- [x] Zusätzliche Service-Hash-Prüfung für geänderte Mediendateien; Renderer-Ansicht erzeugt und angesehen.

## Paket A – Datenlisten und Profile

- [ ] Excel-Datei mit Name, E-Mail, Anrede, Firma, Stelle und Anschreiben laden.
- [ ] Zuordnung mit Standardanrede speichern, wieder laden und Leerwertregel prüfen.
- [ ] Manuelle Liste speichern, App/Projekt erneut öffnen und Liste wieder laden.
- [ ] Liste bearbeiten; neue Kopie anlegen und prüfen, dass die ursprüngliche Liste erhalten bleibt.
- [ ] Dieselben Zeilen in Bulk und Word Replace verwenden und persönliche Werte vergleichen.

Anleitung: [Datenbibliothek](22_Data_Source_Library.txt).

## Paket B – Export

- [ ] Kontakte/Bewerbungen filtern; mehrere Datensätze markieren; beide Umfänge exportieren.
- [ ] Spalten abwählen, CSV und XLSX in Excel öffnen: Umlaute, Zeilenumbrüche und Formelzeichen prüfen.
- [ ] Termine in XLSX prüfen: Zeitpunkte mit Offset werden als UTC exportiert.
- [ ] Überschreiben bestätigen/ablehnen, Export abbrechen und ursprüngliche Datei vergleichen.
- [ ] Bericht einer Versandgruppe exportieren: nur deren Einzelaufträge enthalten.

Anleitung: [Export](23_Data_Export.txt).

## Paket C – Word Replace / PDF

- [ ] Reales DOCX mit verschiedenen Textformatierungen, Tabellen, Kopf-/Fußzeilen und Bildern verwenden.
- [ ] Regeln mit direktem Text und Excel-/Listenfeldern prüfen; fehlende Werte testen.
- [ ] Alle Zeilenvorschauen vergleichen; DOCX-Kopien in Word öffnen und Original vergleichen.
- [ ] Mehrzeilige Anschreiben, Tabs, lange Namen und Seitenumbrüche prüfen.
- [ ] LibreOffice installieren/auswählen und persönliche PDFs erzeugen; Layout und Umbrüche prüfen.
- [ ] Vorhandene Ausgabe und Abbruch testen; bereits registrierte Ausgaben bleiben erhalten.

Anleitung: [Word Replace](24_Word_Replace.txt).

## Paket D – Einstellungen und Windows-UI

- [ ] Design/Export/Word-Replace-Vorgaben speichern, Neustart und Verwerfen/Standardwerte prüfen.
- [ ] 820 × 600, übliche Fenstergrößen und Windows-Skalierung 100/125/150/200 % ausprobieren.
- [ ] Scrollen, feste Word-Abschlussaktionen, Tastaturfokus und Hell/Dunkel prüfen.

## Paket E – Bestehende offene Gmail-Abnahme

- [ ] Verbundenes eigenes Konto prüfen; einzelne Nachricht bewusst an kontrollierte Testadresse senden.
- [ ] Kleine Gruppe an ausschließlich eigene Testadressen: Vorschau/Anhänge, gemeinsame Freigabe, Direktversand.
- [ ] Geplante Gruppe: Termin, Abstand, Pause/Fortsetzen und Abbruch der offenen Aufträge.
- [ ] App schließen/neu öffnen: erneute Prüfung; bereits gesendete Einzelaufträge bleiben erledigt.

Die automatischen Abläufe verwenden Testprovider. In diesem Entwicklungsschritt
wurde keine echte Gmail-Nachricht gesendet. PDF-Konvertierung ist mit Adaptertests
geprüft; ein realer LibreOffice-Lauf bleibt offen.

## Paket F – Hotkeys

- [ ] Hilfe und aktive Standardbelegung ansehen.
- [ ] Eigene Belegung speichern, eine Aktion deaktivieren und Neustart prüfen.
- [ ] Doppelte/reservierte Belegung testen; Formular erhalten, aktive Belegung unverändert.
- [ ] Suche, Datensatz-/Entwurfsspeichern und Navigation mit Tastatur prüfen.
- [ ] Word-Ausgabe nach Vorschau per Ctrl+S: zusätzliche Ausgabe-Bestätigung bleibt.
- [ ] Verschiedene Dialoge/Fokus und Tab-Reihenfolge auf Windows prüfen.

Anleitung: [Hotkeys](26_Hotkeys.txt).

## Paket G – E-Mail-Builder

- [ ] Im Arbeitsbereich öffnen; Excel-/Listenquelle wählen und Werte-Stecker zu Texten verbinden.
- [ ] Baustein aus Palette ziehen, verschieben, verbinden, duplizieren/löschen und Undo/Redo prüfen.
- [ ] Unpassende Stecker, fehlende Eingänge, Kreise und unverbundene Bausteine testen.
- [ ] Version speichern, verändern, ältere Version öffnen und unabhängige Kopie speichern.
- [ ] Gemeinsame Datei ziehen; individuelle Dateien über {{attachment.path}} und values verbinden.
- [ ] DOCX → Word Replace → PDF → E-Mail mit realen Dokumenten/LibreOffice prüfen.
- [ ] Zeilen vergleichen: Empfänger/Betreff/Text, persönliche Anhänge und DOCX-Text stimmen überein.
- [ ] Fehlerhafte/fehlende Daten und Quelldateiänderungen testen; lokale Gruppe bleibt gesperrt.
- [ ] Lokale Entwurfsgruppe erstellen; bestehende Prüfung/Freigabe/Planung öffnet sich.
- [ ] 820 × 600, helle/dunkle Palette, Raster/Zoom und Canvas-Kürzel auf Windows prüfen.
- [ ] Neue Textarten mit persönlichen Listenwerten in Text/HTML vergleichen; Betreff-Stecker prüfen.
- [ ] Bild/PDF/DOCX im Editor ansehen; echtes lokales Video ausdrücklich abspielen/pausieren.
- [ ] Builder-Planung für Sofortversand und zukünftigen Termin nutzen; Datum/Zeitzone/Abstand vergleichen.
- [ ] Mittlere Maustaste, Bausteinsuche und alle acht Themes praktisch prüfen.
- [ ] Links/Buttons und Listen mit eigenen Excel-Werten in Text und HTML prüfen.
- [ ] Unfertigen Text/Word-Regel eingeben, Eingabepause abwarten, App neu starten und Arbeitsstand vergleichen.
- [ ] Projektwechsel und Backup direkt nach Eingabe; letzte Änderung, Planung und Ansicht sind enthalten.
- [ ] Autosicherung ausschalten, unter Plan manuell sichern und wieder laden; Ctrl+S bleibt eine benannte Version.
- [ ] Zwei Fenster desselben Projekts: Konflikt pausiert, Eingaben bleiben erhalten; vor Neu laden Kopie sichern.
- [ ] Anordnen/Undo, automatische Platzierung und direkte Bausteinauswahl mit größerem Graphen prüfen.
- [ ] E-Mail-Baustein auswählen, Zeilenvorschau ausführen: Mail mit An/Betreff/Text/Signatur/Anhängen direkt im Editor und als Miniatur sichtbar.
- [ ] Vorschauzeile oben wechseln: persönliche Mailtexte, Bausteinbeschriftungen, Bilder und Word-Replace-Dokumenttext passen zur ausgewählten Person.
- [ ] Bild-Miniaturen ohne Zusatzklick; ausgewählte Bild-/PDF-/Video-Bausteine laden im Eigenschaftenbereich, Video spielt erst auf Wunsch.
- [ ] Schnell Person/Baustein wechseln und erneut vorschauen; alte Antworten überschreiben die neue Ansicht nicht.
- [ ] Geänderte Mediendatei testen, Fehlermeldung prüfen, Zeilenvorschau erneuern; Layout mit tatsächlichen Gmail-/Outlook-Mails vergleichen.

Anleitung: [E-Mail-Builder](27_Email_Builder.txt). DOCX→PDF-Vorab-Vorschau zeigt
DOCX-Text; vorhandene PDFs besitzen eine PDF-Anzeige. Generiertes PDF-Layout
erst nach Konvertierung prüfen. Ohne ausdrückliche Freigabe
und Versandstart geht keine Nachricht hinaus.

## Weiterentwicklung nach diesem Paket

- [x] Visueller Builder mit Drag & Drop, typisierten Steckern und gespeicherten Graphversionen.
- [x] Hotkey-Kern samt Hilfe/Einstellungen implementiert.
- [x] Builder-Speichern/Löschen/Duplizieren/Undo/Redo/Zoom und eigene Einstellungen.
- [x] Mehr Textbausteine, Editor-Vorschauen, Builder-Bulk-Planung, mittlere Maustaste und acht Themes.
- [x] Arbeitsstandsicherung/Wiederherstellung, Links/Buttons/Listen, Anordnung und direkte Bausteinauswahl.
- [x] OAuth-Abschlussseite mit Gestaltung, Pixelart-Logo und Tab-Schließen/Fallback implementiert.
- [x] Gemeinsame Vorlagen/DOCX-Duplikate/HTML, Dokumenttabellen/ZIP, Canvas-Hotkeys und Graphtransfer implementiert.
- [x] 33 zusätzliche Prüfungen: 23 Kern/10 Qt; Ansichten erzeugt und geprüft.
- [ ] Inline-Medien, Bedingungen/Gruppen, weitere UI und animierte Themes.
- [ ] Tagesbudgets/Versandfenster, Hintergrundausführung, Recovery und Release.

Gesamtliste: [Workspace-TODO](14_Workspace_TODO.md). [Alle Features](12_Feature_Status.md).

## Paket H – Angefordertes Ausbaupaket und Graphtransfer

- [ ] OAuth in echtem Browser: Hell/Dunkel/mobile Breite, Tab-Fokus, Schließen und
  blockiertes Schließen prüfen; Code/Token werden nicht angezeigt, App meldet Adresse.
- [ ] Logo in Seitenleiste/Fenster bei Windows 100/125/150/200 % und Hell/Dunkel ansehen.
- [ ] Unter Vorlagen DOCX und E-Mail gemeinsam suchen/filtern; konkrete ältere Version
  öffnen, DOCX duplizieren und Mapping/Pflichtwerte/Original vergleichen.
- [ ] HTML-Vorlage im Editor sowie persönliche Nachricht/Quelltext vergleichen;
  geänderte Werte erfordern neue Vorschau, externe Bilder laden nicht.
- [ ] Echte DOCX-/PDF-Tabelle mit verbundenen Zellen bzw. Textspalten laden;
  Kopfzeile/Zeilen auswählen, Felder ausdrücklich zuordnen, Erkennung bestätigen.
- [ ] Werte korrigieren und Liste speichern; dieselben Werte in Bulk-Bewerbung,
  Word Replace und Builder verwenden; Quellspalten/Dateiherkunft kontrollieren.
- [ ] Dokumentpaket nach Auswahl/Filter/Formaten exportieren: Varianten gehören
  zum Satz; ZIP, Manifest und Bericht öffnen, fehlende PDFs ausdrücklich bestätigen.
- [ ] Geänderte/fehlende Datei, Überschreiben und Abbruch beim ZIP testen;
  vorhandenes Ziel und Quelldokumente bleiben erhalten.
- [ ] Builder nur per Tastatur: Baustein/Stecker wählen, Ausgang aktivieren,
  Ziel/Eingang verbinden, unpassenden Typ testen, Verbindung löschen und Undo.
- [ ] Canvas-Belegung ändern/deaktivieren, Neustart, App-Konflikt und Textfeldfokus prüfen.
- [ ] Graphvorlage exportieren und in anderem Projekt importieren: Ablehnen erhält
  Eingaben; Übernehmen verlangt neue Daten/Dateipfade/Konto/Planung und Vorschau.

Anleitung: [Ausbaupaket](28_Completion_Package.md). Diese Punkte bleiben manuell offen.

## Paket I – Projektvorgaben, Bulk, Word Replace und UI

- [ ] Projektassistent: vorhandenes Profil mit Zusatzfeldern, eine DOCX-Version und
  Empfängerliste übernehmen; Ziel, bevorzugte Adresse und HTML wählen, neu öffnen.
- [ ] Vorgaben später bearbeiten; neue Vorgänge übernehmen sie, alte Entwürfe und
  feste Versandaufträge behalten ihren Stand. Fehlende/gelöschte Vorgaben testen.
- [ ] Im Arbeitsbereich Bulk direkt öffnen; Modus und Kontextauswahl prüfen.
  Kontaktgruppe/Empfängerfilter speichern, laden und löschen; Kontakte bleiben erhalten.
- [ ] Zwei Zeilen mit unterschiedlichen DOCX-Versionen, Datenwerten und Anhängen
  prüfen; optional Domain-Bewerbungen erstellen, Firmen/Stellen/Profilwerte kontrollieren.
- [ ] Persönliche PDFs mit echtem LibreOffice auf Layout und Seitenumbrüche prüfen.
- [ ] Kontrollierter echter Gmail-Lauf mit ausdrücklich ausgewählten Testempfängern:
  Tagesbudget, Versandfenster, Abstand und Termin prüfen; Mailstatus der Bewerbungen ansehen.
- [ ] Hintergrundstart bestätigen, Gruppenfenster schließen, im Arbeitsbereich Pause,
  Fortsetzen und Abbruch bedienen; App-Neustart/Standby verlangt erneute Prüfung.
- [ ] Unklare Anbieterantwort abgleichen; keine automatische Wiederholung.
- [ ] Word Replace: Ersatzformatierung und Muster mit Firmenname/Nummer ausprobieren;
  Ergebnisse mit Original und Text-/Fundstellenvorschau vergleichen.
- [ ] Mehrzeiligen Lauf pausieren, App neu starten, gespeicherten Lauf ausdrücklich
  fortsetzen; fertige Dateien bleiben erhalten und werden nicht doppelt registriert.
- [ ] Excel-/Originaländerung beeinflusst den gespeicherten Lauf nicht. Geänderte
  fertige Ausgabe blockiert Fortsetzen; zwei Fenster verarbeiten nicht denselben Lauf.
- [ ] 820 × 600 und Windows 100/125/150/200 %: E-Mail/Bulk/Quellen/Vorlagen/Export,
  Word Replace und Einstellungen scrollen; Aktionen, Fortschritt und Abbruch erreichen.
- [ ] Helle/dunkle Themes wechseln, reduzierte Bewegung aktivieren, Fokus/Eingaben
  erhalten; Toastkategorien, Dauer und anhaltende Fehler prüfen.
- [ ] Builder-Panels verschieben/ausblenden/speichern; Textbedingungen und Zusammenführen
  mit zwei Datenzeilen und HTML/Betreff verwenden; Vorschau und tatsächliche Entwürfe vergleichen.

Anleitung und Demonstrationsansichten: [Sprint-7-Ausbau](29_Sprint_7_Expansion.md).
Die automatischen Prüfungen ersetzen diese realen Abnahmen nicht.

## Paket J – Endspurt: Vorgaben, Historie und Wiederherstellung

- [ ] DE/EN, Startansicht und Standardmodus speichern, neu starten und neue Projekte prüfen.
- [ ] Neue E-Mail-/Bulk-/Builder-Planung übernimmt Konto, Signatur, Format, Zeitzone, Abstand, Budget und Fenster; vorhandene Entwürfe behalten ihren Stand.
- [ ] Datensatzlisten: Seitengröße, Umbruch, Farben und kompakte Ansicht prüfen.
- [ ] Standardbausteine wählen und ordnen; neuen Graphen erstellen, ändern und Undo/Redo nach Neustart bedienen.
- [ ] Backup-Ziel/Aufbewahrung prüfen; Wiederherstellung in neuen Ordner und Abbruch testen. Originalprojekt und unbekannte Archive bleiben erhalten.
- [ ] Wiederhergestellte Konten deaktiviert, Hintergrund aus, Aufträge erneut prüfen; alte Word-Replace-Ziele gesperrt.
- [ ] Lokalen Diagnosebericht öffnen: ausschließlich Runtime-/Integritäts-/Statusdaten.
- [ ] Echten LibreOffice-Lauf, personalisierte PDFs und Seitenumbrüche prüfen.
- [x] Zwei freigegebene Gmail-Testmails kontrolliert gesendet: 2 Versuche / 2 Sent; Budget/Fenster/Hintergrund geprüft.
- [ ] Tatsächlichen Empfang beider Nachrichten und native Gruppensteuerung kontrollieren.
- [ ] Physische Tastatur, Tab-Reihenfolge und Windows 100/125/150/200 % praktisch prüfen.
- [ ] Vollständige englische Fachtexte und Release-Paket nach Abschluss abnehmen.

Implementierung: [Endspurt](31_Endspurt.md). 561 Tests / 560 bestanden / 1 optional übersprungen:
[Prüfbericht](32_Endspurt_Test_Report.txt). Qt-Skalierung wurde simuliert geprüft;
reale PDF-/Browser-/Windows-Abnahme bleibt separat offen.
Gmail-Freigabe: [konkrete Nachrichten](33_Gmail_Test_Review.md).
