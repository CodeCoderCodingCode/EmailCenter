EMAILCENTER 1.0.1 — WINDOWS-INSTALLER
Stand: 2026-10-14

Für normale Nutzer:
1. Install_EmailCenter.cmd oder dist/release/EmailCenter-Setup-1.0.1-Windows-x64.exe starten.
2. Optional Startmenü- und Desktop-Verknüpfung wählen.
3. Projekt erstellen/öffnen und über E-Mail -> Gmail verbinden das eigene Konto anmelden.
   Der Betreiber muss das Google-Konto als Testnutzer freischalten.
4. Hilfe / Guide bzw. F1 erklärt die aktuelle Ansicht und den ausgewählten Baustein.

Python und PDF-Konverter sind enthalten. Persönliche Tokens und Projekte werden
nicht mitgeliefert. Im Google-Testmodus nach sieben Tagen ggf. erneut verbinden.
Geplanter Versand benötigt ein geöffnetes EmailCenter und einen aktiven Rechner.

Guide: guide/EmailCenter_Guide.html
Betreiber-Anleitung: docs/45_Release_Operator.md
Release-Nachweis und Restabnahme: docs/47_Windows_DLL_Fix.md

DLL-/Startpfad-Korrektur 1.0.1:
- build/pyinstaller ist nur ein Zwischenordner und keine startbare Anwendung.
- Start_EmailCenter.cmd verwendet die vollstaendige App unter dist/runtime/EmailCenter.
- Bei Weitergabe nur den Setup-Installer verschicken. Eine einzelne EmailCenter.exe
  aus dem Build-Ordner enthaelt weder Python noch Qt oder den PDF-Konverter.
- Der Build prueft alle wichtigen Laufzeitdateien vor der Installer-Erstellung und
  entfernt die nicht eigenstaendig startbare Zwischen-EXE nach erfolgreicher Sammlung.

Die folgenden Entwicklungs- und früheren Abnahmehinweise bleiben als Verlauf erhalten.
EMAILCENTER — START HERE
Stand: 2026-10-13

AKTUELL — EXCEL-BEWERBUNGSWORKFLOW IM BUILDER / SCHEMA 14
- A11: PDF-Dateiname am DOCX -> PDF-Baustein einstellen, z. B.
  Anschreiben{{Unternehmen}}.pdf. Leer = ursprünglicher DOCX-Name.pdf.
  Derselbe Name in Vorschau, gespeichertem PDF, Dokumentverwaltung und Mailanhang.
  Version speichern, App neu starten, Muster einstellen und eine neue Gruppe erstellen.
  Anleitung: docs/44_Builder_PDF_Names.md.
- A10: Regelnummern und markierte Fehlerzeilen, konkrete Bausteinvorschaufehler,
  Restplatzhalter mit Leerzeichen/Umlauten sowie sichtbare Schritte bis zur
  Entwurfsgruppe und Versandfreigabe. Ablauf: docs/43_Builder_Feedback_And_Review.md.
- Nachbesserung: bestehende Word-Replace-Felder mit Leerzeichen/Umlauten blockieren
  die Excel-Übernahme nicht mehr. Konkrete Fehler zeigen jetzt das fehlende Feld.
  App neu starten; vorhandene XLSX kann weiterverwendet werden.
  Aktueller Nachweis: docs/42_Builder_Mapping_Fix.md (A9).
- Datenbaustein -> Excel / CSV laden: direkter Workflow-Import ohne vorherige
  Firmen-/Bewerberprofile; alle Excel-Spalten können als Platzhalter verwendet werden.
- 20 Fake-Ziele nur mit den fünf gewünschten Adressen:
  outputs/01a12c0f-69bf-71e0-a70f-f1d66a02b353/EmailCenter_Bewerbungsziele.xlsx
- Wiederholte Testadressen im Datenbaustein ausdrücklich zulassen.
- Persönliche Word-Replace-DOCX bleiben neben den angehängten PDFs gespeichert.
- App nach Update neu starten; vorhandene Projekte erhalten Migration 14.
- Anleitung für alle Schritte und aktueller Prüfnachweis: docs/41_Builder_Excel_Workflow.md.
- Benutzer bestätigt den Kernworkflow; letzter Wunsch PDF-Dateiname umgesetzt.
  Nächster Ausbau: Anschlussphase B1-B5 aus docs/34_Final_TODO.md.
- Aktuelle A11-Suite: 676 Tests / 675 bestanden / ein optionaler nativer Vault-Skip.
  Dieselbe XLSX mit vorhandener Word-Replace-Kette und erneuter Übernahme im UI,
  dazu 20 echte persönliche PDF/DOCX und geplanter Testprovider-Versand geprüft.
  Persönliche Namen auch in gespeicherten PDFs und MIME-Anhängen geprüft.
  Gesamtsuite, Excel-UI, Workflow und Archiv verwenden dieselben unveränderten Quellen.
  Abschluss: docs/abnahme/A11_Builder_PDF_Names/Completion_Result.json.

VORHERIGES PAKET — A1–A7 TECHNISCH ABNAHMEBEREIT / SCHEMA 13
- Eigene Dateien und praktische Windows-Bedienung nimmt der Benutzer am Ende
  selbst ab; Zwischenfreigaben und eigene Dateien werden jetzt nicht verlangt.
- Builder-Widgetbesitz, DE/EN-Menüs und lange Windows-Restore-Stagingpfade korrigiert.
- Durchgehender lokaler Ablauf mit echten Excel-/DOCX-/PDF-Dateien, zwei
  Bewerbungen, Testprovider, CSV/XLSX und geprüfter Wiederherstellung besteht.
- Keine zusätzlichen echten Mails gesendet. TEST 1–4 und beide PDFs sind bestätigt.
- Abschlussprüfungen: 644 Tests, 643 bestanden / ein optionaler Vault-Skip;
  540 UI-Prüfungen in sechs Runden, keine zurückbleibenden Widgets/Fenster.
  Code während aller finalen Prüfungen unverändert und im geprüften Archiv gesichert.
- Abschlussnachweis: docs/40_Technical_Completion.md.
- Verbindliche technische/praktische Restliste: docs/34_Final_TODO.md.

VORHERIGES PAKET — A5 SPRACHE / UI
- Englische Apptexte, Fehlermeldungen, Dialoge und Projektassistent ergänzt.
- Sprachwechsel erhält persönliche Werte, Platzhalter, Mailinhalte und Auswahl-IDs.
- Englischer Neustart, Vorschau-Bereinigung und vier Qt-Skalierungen geprüft.
- 492 verwendete Beschriftungsquellen abgedeckt; native Windows-Abnahme offen.
- Damaliger Gesamtlauf: 638 Tests, 637 bestanden, ein optionaler Vault-Skip;
  Quellen unverändert. Zusätzlich 144 wiederholte UI-Prüfungen bestanden.
- Beide bisherigen Gmail-Testmails angekommen (Benutzerbestätigung 13.10.2026).
- Zusätzlich TEST 3/4 mit konkreter Freigabe: Gmail-Draft, Sofort-/Terminversand
  und zwei persönliche PDFs erfolgreich; Gmail-Inhalt und Anhanghashes stimmen.
- Ergebnis/Sammelprüfung: docs/39_Gmail_Attachment_Review.md; native Abnahme offen.
- Empfang beider neuen Mails und korrekte Anzeige beider PDFs vom Benutzer bestätigt.
- Anleitung/Prüfung: docs/38_Localization_UI_Completion.md.
- Verbindliche Restliste: docs/34_Final_TODO.md; Phase B folgt nach A.

NEU — ABSCHLUSSPAKET A1 / A2 / A3
- Echte LibreOffice-PDF-Konvertierung; persönliche Layouts und Excel-Daten geprüft.
- Builder mit 26 Bausteinarten, Bausteingruppen, Inline-Bildern,
  persönlichen Anhangnamen/Reihenfolge und PDF-Seitenlayout vor Gruppenanlage.
- Verwaltung: Status/Signaturen/Standardsignatur, Historien, Dokumentensätze,
  Exporthistorie, Archiv/Papierkorb/Restore und nachholbare Dateibereinigung.
- Adressen, typisierte Zusatzfelder und Stellenbeginn in den Formularen.
- Anleitung und gemeinsame Abnahme: docs/35_Completion_A1_A3.md.
- Gesamtlauf A1–A3: 601 Tests, 600 bestanden, ein optionaler Tresor-Test übersprungen.
- Prüfbericht: docs/36_Completion_Test_Report.txt; Laufzeit/Lizenzen: docs/37_Runtime_Dependencies.md.
- Codearchiv mit Prüfsummen: docs/abnahme/Code_Snapshot.json.
- Schema 13; bestehende Projekte werden über die normalen Migrationen übernommen.

FINALE REIHENFOLGE
docs/34_Final_TODO.md: A1–A7 schließen das aktuelle Programm funktional ab.
Danach B1–B5: fertige Vorlagen, Dokumentation/Tooltips, geführte Projektmodi,
Anmeldung über Neustarts und Installer/Anleitung für weitere Nutzer.

DESKTOP STARTEN
Doppelklick auf Start_EmailCenter.cmd.
Oder im Projektordner:
.\.venv\Scripts\python.exe start_emailcenter.py

Bestehendes Projekt beim Start öffnen:
.\.venv\Scripts\python.exe start_emailcenter.py --project "C:\Pfad\zum\Projekt"

Abhängigkeiten (GUI, Excel, PDF-Tabellen, Gmail-OAuth, Windows-Tokenablage und Zeitzonen sind installiert):
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Tests:
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

Projektstatus:
- Anforderungen und Architektur sind dokumentiert.
- Sprint 1 (SQLite-Verbindung, Migration Runner, Company-/Contact-Repositories) ist abgeschlossen.
- Sprint 2 (Projekt erstellen/öffnen, sichere Dateipfade, geprüftes Projektarchiv) ist abgeschlossen.
- Sprint 3 (Bewerbungsdomain, Statuswerte/-wechsel, Stellen und Kontaktverknüpfungen) ist abgeschlossen.
- Sprint 4 ist technisch umgesetzt: Vorlagenversionen mit Änderungsprüfung, gespeicherte Feldzuordnungen,
  DOCX-Erzeugung, Dokumentensätze, temporärer Vorschau-Service und PDF-Konvertierungsanbindung.
- Sprint 5 (CSV/XLSX) ist abgeschlossen: Importprofile, Vorschau/Feldzuordnung,
  Zeilenvalidierung, Duplikatprüfung, Korrektur, Protokolle, Pause und Wiederaufnahme.
- Sprint 6 ist technisch umgesetzt: Gmail-OAuth mit PKCE/Systembrowser, Windows Credential
  Manager, lokale/Gmail-Entwürfe, Signaturen, feste Versandaufträge/Anhänge,
  Freigabe, Zeitplanung, Versandprotokolle und Abgleich unklarer Ergebnisse.
  Echte Anmeldung und TEST 1–4 samt persönlichen PDFs und Terminlauf sind erfolgreich;
  Empfang und PDFs bestätigt. Native Bedienabnahme folgt am Ende.
- Sprint 7 ist technisch umgesetzt: erweiterbare Desktop-Oberfläche mit Navigation,
  Projekt-/Backup-Aktionen, Listen/Suche/Seitenwechsel, Erfassungsdialogen, Bewerbungsstatus,
  Vorlagenimport/-versionen, Dokumenterzeugung, Textvergleich, PDF-Anzeige,
  Datenimport und E-Mail-Seite mit Nachrichteneditor/Freigabe/Versandhistorie.
- Datensätze bearbeiten: Unternehmen, Kontakte, Bewerberprofile, Stellen und
  Bewerbungen. Stellenzuordnung, Kontaktrollen/Hauptkontakt und Konfliktprüfung
  sind in der Oberfläche bedienbar; Eingaben bleiben bei Speicherfehlern erhalten.
- Nachfassen: fällige Bewerbungen und eigene Erinnerungen, Kalender-/Zeitzonen-
  dialog, Verschieben, Abschluss, Historie und minütliche Prüfung in der laufenden App.
- Zentrale Einstellungen mit dauerhaftem Hell/Dunkel-Design, wählbarer/eigener
  Akzentfarbe und Anzeigezeitzone; unabhängig vom geöffneten Projekt.
- Datei-/Datenbankabläufe laufen in einem eigenen Qt-Worker; Widgets enthalten kein SQL.
- Arbeitsbereich: Projekteinstieg ohne Projekt, Modus/Ziel bei Projektanlage,
  direkter Wechsel nach Öffnen, Bewerbungs-/E-Mail-Modus, direkte Editoren,
  Vorlagenaktionen und responsive Karten. Lokale animierte Toasts sind vorhanden.
- Einzelaufträge vollständig im Arbeitsbereich: Entwurf auswählen/bearbeiten,
  Kalender/Zeitzone, Vorprüfung, Auftrag prüfen/freigeben, manueller Versand,
  Storno, Status und Abgleich unklarer Ergebnisse.
- Gmail-Fix: alte Entwürfe wählen ihren Absender beim Vorbereiten; verbundene
  Adresse, Gmail verbinden und Scheduler stehen direkt im Arbeitsbereich bereit.
- Freigeben & jetzt senden sowie Jetzt senden können nach Bestätigung vor einem
  geplanten Termin ausführen. Automatische geplante Ausführung bleibt termingebunden.
- Beschriftung: Senden ohne Termin, Versand planen mit Termin; Prüfung bleibt erhalten.
- Projektassistent mit drei Schritten, optionalem Profil/Standardsignatur und
  Zusammenfassung. Abbruch/Fehler bewahren ein bestehendes Projekt und Eingaben.
  Standardsignatur wird bei neuen Entwürfen vorgeschlagen. docs/16_Project_Wizard.txt.
- Kontext: E-Mail aus Bewerbung/Kontakt im Arbeitsbereich oder der jeweiligen
  Liste starten. Empfänger, Betreff, Texteinstieg und Dokumentauswahl übernehmen;
  Mehrfachwahl, Bestätigung und Fehlererholung. docs/17_Mail_Context.txt.
- UI: scrollbarer E-Mail-Editor mit erreichbaren Abschlussaktionen und
  Datensatzaktionsleisten, die in mehrere Zeilen umbrechen.
- E-Mail-Vorlagen: Name/Betreff/Text/Format, Versionen, Duplikate und Namenssuche.
  Projekt-/eigene Platzhalterwerte in der Vorschau prüfen und ausdrücklich in
  den Entwurf übernehmen. Empfänger/Anhänge bleiben erhalten. docs/18_Mail_Templates.txt.
- Bulk im Arbeitsbereich: Kontakte über Seiten hinweg wählen, persönliche Vorlagenwerte,
  Bewerbungsdokumente und gemeinsame Dateien prüfen. Eine Gruppe atomar als einzelne
  lokale Entwürfe speichern, wieder öffnen und bearbeiten; anschließend Gruppenversand öffnen.
  Anleitung: docs/19_Bulk_Drafts.txt. Migration 005 erhält bestehende Entwürfe/Aufträge.
- Visueller E-Mail-Builder: Palette/Drag & Drop, typisierte Stecker, gemeinsame
  Excel-/Listenquellen, persönliche Texte/Dateipfade, Word Replace und DOCX→PDF.
  Zeilenvorschau → lokale Entwurfsgruppe → bestehende Prüfung/Freigabe/Versand.
  Graphen versionieren/wiederverwenden, Zoom/Raster, Undo/Redo und eigener
  Einstellungs-Tab. Anleitung: docs/27_Email_Builder.txt. Migration 009.
  Neu: Betreff/Beschreibung/Absatz/Überschrift/HTML/Anrede/Gruß/Trennlinie,
  Live-Text-/HTML-/Bild-/Video-/PDF-Vorschau und persönliche DOCX-Texte.
  Bulk-Aufträge direkt im Builder vorbereiten oder Datum/Zone/Abstand planen.
  Suchpalette, mittlere Maustaste, Verbindungsvorschau und schnellere Kanten.
  Neu: Autosicherung mit unfertigen Eingaben/Planung/Ansicht und Wiederherstellung
  nach Neustart; getrennt von benannten Versionen (Migration 010). Weiterarbeiten
  während Sicherung, Nachsichern vor Projektwechsel/Backup/Schließen, Konflikterkennung.
  Link-/Button-/Listenbausteine (insgesamt 22 Arten), Anordnen/Undo, freie
  Standardplatzierung und direkt zum Baustein springen. Einstellungen: Autosicherung
  und Eingabepause. Ansicht: docs/builder_workspace_preview.png.
  Neu: fertiger Mailrenderer direkt im E-Mail-Baustein und Mail-Tab, inklusive
  Empfänger/Betreff/Signatur/Anhängen. Zeilenvorschau lädt persönliche Inhalte
  automatisch am Baustein; Mail-/HTML-/Bild-Miniaturen auf der Zeichenfläche.
  Lokale Medien im Eigenschaftenbereich, gemeinsame Vorschauzeile und begrenzter
  Hintergrundcache. Ansicht: docs/builder_renderer_preview.png.
  Acht dauerhafte Themes mit vier Hell-/Dunkel-Paaren und eigener Akzentfarbe.
  Die Umsetzungsschritte stehen in docs/14_Workspace_TODO.md.
- Direkte Excel-/CSV-Importzeilen und manuelle Listen versorgen E-Mails und
  persönliche Anschreiben mit denselben Daten. Anrede/Name/E-Mail/Firma/Stelle/
  Anschreiben einmal zuordnen; zusätzliche Spalten bleiben erhalten. Excel-Zellen
  einfügen, DOCX-Text übernehmen, eigene Dateien anhängen und DOCX/PDF-Ausgabe wählen.
  Migration 006 erhält Kontaktgruppen und speichert Herkunft/Zuordnung/Werte.
  Anleitung: docs/20_Bulk_Data_Sources.txt.
- Gruppenversand: feste Einzelaufträge schrittweise vorbereiten, gemeinsam prüfen/
  freigeben, direkt oder geplant mit Abstand senden; Fortschritt, Pause/Fortsetzen,
  Abbruch, Einzelabgleich und ausdrücklicher Retry. Fenster/App bleiben geöffnet.
  Migration 007 erhält bestehende Daten. Anleitung: docs/21_Bulk_Delivery.txt.
- Historischer Endspurt-Gesamtlauf: 561 Tests; 560 bestehen, ein nativer Windows-Vault-Test ist opt-in
  und hier übersprungen. Er wurde in einem früheren Schritt separat erfolgreich geprüft.
- Neu: wiederverwendbare Datenlisten und Zuordnungsprofile/Standardwerte (Migration 008).
  Dieselben Zeilen versorgen Bulk und Word Replace. Anleitung: docs/22_Data_Source_Library.txt.
- Neu: CSV/XLSX-Export mit Filter/Mehrfachauswahl, Spalten und Gruppenbericht.
  Im Arbeitsbereich oder den Datensatzlisten öffnen. Anleitung: docs/23_Data_Export.txt.
- Neu: eigene Word-Replace-Seite mit freien Regeln, Fundstellen, Textvergleich,
  persönlichen DOCX-/PDF-Kopien und Abbruch. Excel-Dokumentdaten benötigen keine
  E-Mail-Spalte. Abschlussaktionen bleiben auch beim Scrollen erreichbar.
  Anleitung: docs/24_Word_Replace.txt; Ansicht: docs/word_replace_preview.png.
- Einstellungen besitzen Tabs für Export, Word Replace/PDF-Konverter und Hotkeys.
- Hotkeys mit eigener Belegung, Deaktivierung, Konfliktprüfung und Tastaturhilfe;
  Speichern/Suchen und Navigation sind angebunden. Anleitung: docs/26_Hotkeys.txt.
- Manuelle Zwischenabnahmen werden auf Benutzerwunsch gesammelt:
  docs/25_Bundled_Acceptance.md. LibreOffice-/Gmail-/Windows-Prüfungen bleiben offen.
- Benutzerpaket fertig implementiert: OAuth-Abschlussseite/Tab-Schließen/Logo,
  gemeinsame Vorlagensuche, DOCX-Duplikate und gerenderte HTML-Mailvorschau,
  strukturierte DOCX-/PDF-Tabellen, DOCX/PDF-ZIP und konfigurierbare Canvas-Hotkeys.
  Danach Graphtransfer ergänzt; Quellen/Dateipfade beim Import neu zuordnen.
  33 neue Tests. Anleitung und Ansichten: docs/28_Completion_Package.md.
- Neuer Ausbau (Migration 011): Projektvorgaben/Übernahme, Kontaktgruppen/Filter,
  persönliche DOCX-Versionen und optionale Domain-Bewerbungen samt Mailstatus;
  Budget/Versandfenster/Quotensperren und Hintergrundlauf bei geöffneter App.
- Word Replace: gespeicherte fortsetzbare Läufe, Ersatzformatierung und Dateinamensmuster.
- UI: responsive Aktionsleisten, Fortschritt/Abbruch, Übergänge/reduzierte Bewegung,
  Toast-Einstellungen und Builder-Panels. Direkt danach Bedingungen/Zusammenführen ergänzt.
  Anleitung und Ansichten: docs/29_Sprint_7_Expansion.md; Sammelabnahme Paket I.
- Builder-Ausbau implementiert: Inline-Bilder, Bausteingruppen und DOCX/PDF-Seitenlayout;
  weitere globale Vorgaben und dauerhafte Undo-/Redo-Graphhistorie sind implementiert.

Nächster Sprint:
Sprint 4: echten LibreOffice-Lauf und Layoutprüfung nachholen, sobald LibreOffice vorhanden ist.
Die sichtbare Text-/PDF-Vorschau und der Datenimport sind angebunden.
Sprint 6: Gmail-Clientdatei auswählen und Anmeldung/Testversand praktisch abnehmen.
Sprint 7A: Projektvorgaben, persönliche Bulk-Bewerbungen und Hintergrundsteuerung
sind implementiert; tatsächliche Abnahme der Abläufe ist offen.
Sprint 7B: responsive Kernseiten, kurze Übergänge, reduzierte Bewegung und weitere
Einstellungen inklusive Sprachwahl und globaler Vorgaben sind implementiert; vollständige englische Fachtexte und Windows-Abnahme offen.
Die gestaltete OAuth-Abschlussseite und der Tab-schließen-Button sind implementiert;
manueller Browserablauf und Fallback stehen in der Sammelabnahme.
Dokumentworkflow: docs/06_Document_Workflow.txt. GUI/Erweiterungen: docs/07_Desktop_GUI.txt.
Importanleitung: docs/08_Import_Workflow.txt.
Gmail-Einrichtung und Versand: docs/09_Gmail_Workflow.txt.
Datensätze, Stellen und Kontakte: docs/10_Record_Management.txt.
Nachfassen und Erinnerungen: docs/11_Reminders.txt.
Alle Features und UI-Änderungen: docs/12_Feature_Status.md.
Einstellungen und Design: docs/13_Settings.txt.
Neue Feature-/UI-TODOs mit Abnahmekriterien: docs/14_Workspace_TODO.md.
Aktueller Arbeitsbereich mit Testdaten: docs/workspace_preview.png.
Einzelaufträge im Arbeitsbereich: docs/15_Mail_Workspace.txt.
Aktueller E-Mail-Arbeitsbereich: docs/mail_workspace_preview.png.

Lies zuerst docs/04_Sprint_Plan.txt und docs/05_Open_Decisions.txt.

Neues Sprint-7-Paket: 48 zusätzliche Tests (31 Kern/Migration, 17 Qt).
Historischer Sprint-7-Lauf: 561 Tests, 560 bestanden, ein optionaler nativer Vault-Test übersprungen.
Projekt/Bulk/Word/UI und Textwahl: docs/29_Sprint_7_Expansion.md; Abnahme Paket I.

ENDSPURT — SPRINT 7B / 8
Dauerhafte Sprachwahl, Projekt-/Start-/E-Mail-/Listenvorgaben, geordnete Builder-
Standardbausteine und gespeicherte Undo-/Redo-Graphhistorie sind implementiert.
Backup-Ziel/Aufbewahrung, Prüfsummenarchive, sichere Wiederherstellung in neue
Ordner und lokaler Diagnoseexport sind verfügbar. Gmail wird nach Wiederherstellung
nicht automatisch aktiviert; Aufträge und alte Word-Ausgabeziele verlangen Prüfung.
Historischer Endspurt-Lauf: 561 Tests: 560 bestanden, ein optionaler nativer Vault-Test übersprungen.
Echte PDF-/Windows-Abnahme sowie vollständige Übersetzung/Paketierung offen.
Gmail-Test erfolgreich: 2 Versandversuche / 2 Sent, Fenster/Hintergrund/Budget
geprüft; Empfang und weitere reale Versandabläufe bleiben offen.
Anleitung: docs/31_Endspurt.md. Bericht: docs/32_Endspurt_Test_Report.txt.
Gebündelte praktische Abnahme: Paket J in docs/25_Bundled_Acceptance.md.
