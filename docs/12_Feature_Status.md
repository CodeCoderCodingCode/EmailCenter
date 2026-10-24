## Aktuell: Release 1.0.0 (14.10.2026)

Die Anschlussphase ist implementiert: neue Werte-/Bereinigungsbausteine, 14 Designs und Effekte, Vorlagenpaket, geführter Arbeitsbereich, Guide/F1, gemeinsame Gmail-Anmeldung und Windows-Installer. Aktueller Nachweis: [Release 1.0.0](46_Release_1_0.md). Die folgende Matrix enthält auch historische Prüfstände; persönliche Endabnahme bleibt offen.

# EmailCenter – Features und UI-Änderungen

Abschlussumfang und Reihenfolge: [Finale TODO](34_Final_TODO.md).
Installer und die fünf neu beauftragten Einführungspunkte folgen nach dem
funktionalen Abschluss in Phase B.

Stand: 13.10.2026. Diese Liste enthält die Funktionen aus den Anforderungen, dem
Sprintplan und dem vorhandenen Code. Sie wird bei weiteren Änderungen fortgeschrieben.

**Legende:** ✅ implementiert · ◐ teilweise implementiert / Abnahme offen · ⏳ noch umzusetzen · 🔮 spätere Erweiterung.
Ein vorhandener Datenbankeintrag allein gilt nicht als fertiges Feature.

Aktuelles Paket: [Excel-Bewerbungsworkflow im Builder](41_Builder_Excel_Workflow.md).
Aktuelle Abnahme-Nachbesserung: [Einstellbare persönliche PDF-Dateinamen](44_Builder_PDF_Names.md).
Aktueller A11-Nachweis: 676 Tests / 675 bestanden / ein optionaler nativer Vault-Skip;
dieselbe XLSX mit vorhandenen Word-Replace-Regeln und erneuter Übernahme im UI
sowie 20 echten DOCX/PDF im geplanten Testprovider-Ablauf geprüft. Identische
unveränderte Quellen in Gesamtsuite, Excel-UI, Workflow und Archiv.
PDF-Namen am DOCX→PDF-Baustein einstellen: Originalname oder persönliches Muster
mit Excel-Werten; Name in Vorschau, gespeicherter Datei, Dokumentverwaltung und
MIME-Anhang identisch. Bestehende Konverterkonfigurationen bleiben gültig.
Word-Replace-Fehler nennen Regelnummern und markieren die Zeilen; offene DOCX-
Restplatzhalter mit Leerzeichen/Umlauten werden vor der Gruppenanlage blockiert.
Der Builder erklärt Vorschau, Bestätigung, Erstellung und Gruppenfreigabe sichtbar.
Neu: direkter Dateiimport, alle Excel-Spalten als Tokens, wiederholte Testadressen
nach ausdrücklicher Auswahl, dauerhafte persönliche DOCX neben PDF-Anhängen und
Migration 14. Der Benutzer bestätigt den Kernworkflow; der letzte Dateinamenswunsch
ist umgesetzt. Anschlussphase B1–B5 folgt.
Vorheriger A8-Stand: 655 Tests / 654 bestanden / ein optionaler Skip; dazu die echte bereitgestellte
20-Zeilen-XLSX im UI und durch DOCX/PDF/Anhangzusammenstellung/geplanten Testversand
geprüft. Alle Prüfungen verwenden dieselben unveränderten Quellprüfsummen.

Vorheriges Schema-13-Paket: [Technischer Abschluss bis zur Abnahme](40_Technical_Completion.md).
Damals: 644 Tests, 643 bestanden / 1 optionaler Vault-Skip; Quellen
unverändert. Finaler UI-Lauf: 540 Prüfungen in sechs Runden, null zurückbleibende
Widgets/Fenster. A1–A7 technisch abnahmebereit; eigene Dateien/native UI-Abnahme am Ende.
Historisches A5-Paket: 144 UI-Wiederholungsprüfungen bestanden. Empfang beider
bisherigen Gmail-Testmails vom Benutzer bestätigt. Zusätzliche TEST 3/4 mit PDF-/
Terminversand, Gmail-Rückvergleich und vom Benutzer bestätigtem Empfang/PDF-Layout:
[A4](39_Gmail_Attachment_Review.md).
Sammelabnahme: [A1–A3](35_Completion_A1_A3.md).

## Sprintübersicht

| Sprint | Inhalt | Stand / Restarbeit |
|---|---|---|
| 0 | Planung und Setup | ◐ Geprüfte Laufzeit und Lizenzinventar dokumentiert; persönliche Freigabe am Ende, Verteilung in B5 |
| 1 | Datenbank | ✅ Verbindung, Schema, Migrationen und Integritätsregeln |
| 2 | Projekte und Dateien | ✅ Projektlebenszyklus, sichere Pfade und geprüfte Backups |
| 3 | Bewerbungsdomain | ✅ Kernobjekte, Beziehungen und Statusregeln |
| 4 | Dokumente | ◐ implementiert; echte LibreOffice-Konvertierung und vier persönliche PDF-Seiten geprüft; eigene Dokumentabnahme offen |
| 5 | CSV/XLSX | ✅ Importkern sowie CSV/XLSX-Export, Filter/Auswahl, Quellprofile und Datenlisten |
| 6 | Gmail | ◐ vier echte Testmails samt PDFs/Termin und Empfang geprüft; native Bedienabnahme am Ende |
| 7 | Oberfläche | ◐ Arbeitsbereich, Bulk, Word Replace, Export, Hotkeys, visueller Builder und DE/EN-Apptexte implementiert; praktische Windows-/UI-Abnahme offen |
| 8 | Hardening und Release | ◐ Restore/Recovery, Diagnose und Aufbewahrung technisch geprüft; eigenes Projekt/nativer Langlauf am Ende, Verteilung in B5 |

## 1. Projekte, Datenbank und Dateien

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| P01 | Projekt mit Namen und eigenem Ordner erstellen | ✅ | Dialog mit Name, neuem Ordnernamen und Ordnerauswahl |
| P02 | Bestehendes Projekt öffnen und schließen | ✅ | Toolbar; fehlgeschlagenes Öffnen behält das bisherige Projekt |
| P03 | Projekt direkt beim Programmstart öffnen | ✅ | Startparameter `--project` |
| P04 | Eine SQLite-Datenbank und lokale Dateien je Projekt | ✅ | Projektname und Ordner werden angezeigt |
| P05 | Projektmanifest, Format- und Schema-Version prüfen | ✅ | Fehler werden verständlich angezeigt |
| P06 | Nummerierte Migrationen inklusive Wiederholung und Rollback | ✅ | Automatisch beim Öffnen; Schema 13, einschließlich Builder-Arbeitsstand, Verwaltung und Bereinigungsbelegen |
| P07 | Fremdschlüssel, UUIDs und UTC-Zeitstempel | ✅ | Intern; keine SQL-Eingaben in der Oberfläche |
| P08 | Sichere Projektpfade und Schutz vor Pfadausbruch | ✅ | Dateien bleiben in den vorgesehenen Projektpfaden |
| P09 | Temporäre Vorschauen und Aufräumen nach Fehlern | ✅ | Vorschaufenster schließt Arbeitskopien kontrolliert |
| P10 | Manuelles geprüftes ZIP-Backup mit Datenbank-Snapshot | ✅ | Backup-Aktion und Anzeige des gespeicherten Pfads |
| P11 | Projektordner im Dateimanager öffnen | ✅ | Toolbar-Aktion |
| P12 | Backup wiederherstellen | ✅ | Archiv-/Integritätsprüfung, Abbruch und Dialog; neuer Zielordner, deaktivierte Konten und erneute Versandprüfung |
| P13 | Backup-Verschlüsselung und Schlüsselverwaltung | 🔮 | Aktuelle lokale ZIPs sind unverschlüsselt; Schutz/Hinweis in A6 dokumentieren, Verschlüsselung ist ein separater Ausbau |
| P14 | Recovery verwaister Dateien nach Prozessabbruch | ◐ | Persistierte Arbeitsstände und Bereinigungsbelege, verwaiste temporäre Dateien und Wiederanlauf technisch geprüft; eigenes Projekt am Ende abnehmen |
| P15 | Flexible JSON-Felder | ✅ | Typisierter Zusatzfeldeditor mit Validierung; strukturierte unveränderte Altwerte bleiben erhalten |
| P16 | Archivieren, Löschen, Papierkorb und Aufbewahrung | ✅ | Verwaltung mit Restore, Referenz-/Prüfsummenschutz und nachholbarer Dateibereinigung; externe Originale/Backups erhalten |
| P17 | Projektanlage mit Modus und Projektziel | ✅ | Im Projekt gespeichert; alte Projekte starten im Bewerbungsmodus |
| P18 | Erweiterter Projektassistent | ✅ | Drei Schritte; Profil/Signatur, vorhandenes Profil/DOCX/Liste übernehmen, Konto/Format; Ziel/Vorgaben später bearbeiten und für neue Vorgänge verwenden; praktische Abnahme offen |

## 2. Bewerbungen und Stammdaten

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| B01 | Unternehmen anlegen und bearbeiten | ✅ | Name, Website, Branche und mehrzeilige Notizen |
| B02 | Zentrale Kontakte anlegen und bearbeiten | ✅ | Anzeigename, Vor-/Nachname, E-Mail, Telefon, Position und Notizen |
| B03 | Bewerberprofile anlegen und bearbeiten | ✅ | Eigene Seite; Name, E-Mail und Telefon |
| B04 | Adressen und individuelle Zusatzfelder bearbeiten | ✅ | Adressfelder und typisierter Editor; unveränderte strukturierte Altwerte bleiben erhalten |
| B05 | Stellen anlegen und bearbeiten | ✅ | Unternehmen, Titel, Referenz, Ort, URL, Beschreibung, Beschäftigungsart und Frist |
| B06 | Stellenbeginn bearbeiten | ✅ | Formularfeld mit Datumsprüfung |
| B07 | Bewerbungen anlegen und bearbeiten | ✅ | Titel, Unternehmen, Stelle, Profil, Datum, Nachfasszeit, Quelle und Notizen |
| B08 | Stellen und Bewerbungen konsistent mit Unternehmen verknüpfen | ✅ | Unpassende Unternehmen werden abgewiesen; Stelle kann ihr Unternehmen übernehmen |
| B09 | Kontakte einem Unternehmen zuordnen | ✅ | Zuordnungsdialog mit Rolle und Hauptkontakt |
| B10 | Einen Hauptkontakt je Unternehmen auswählen | ✅ | Neue Markierung ersetzt die bisherige atomar |
| B11 | Kontakte einer Bewerbung zuordnen | ✅ | Zuordnungsdialog mit Kontaktrolle |
| B12 | Kontaktzuordnungen bearbeiten und lösen | ✅ | Kontakt bleibt beim Entfernen der Verbindung bestehen |
| B13 | Standardstatus und Statuswechsel | ✅ | Statusdialog; abgeschlossene Status sperren weitere Übergänge |
| B14 | Eigene Statuscodes/-bezeichnungen konfigurieren | ✅ | Verwaltungseditor; System-/verwendete Statusregeln geschützt |
| B15 | Status- und Änderungsverlauf protokollieren | ✅ | Sichtbare Verwaltungsansicht mit Datensatzbezug und Änderungsdetails |
| B16 | Konflikte bei gleichzeitigem Bearbeiten erkennen | ✅ | Speichern weist zwischenzeitliche Änderungen ab |
| B17 | Unveränderte lange Importfelder und Archivbezüge erhalten | ✅ | Bearbeitung ändert ausschließlich angepasste Felder |
| B18 | Änderungen und Aktivitätslog gemeinsam bestätigen | ✅ | Fehler führen zum Rollback |

## 3. Nachfassen und Erinnerungen

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| R01 | Nachfasstermine aus Bewerbungen anzeigen | ✅ | Eigene Seite; keine zusätzlich erzeugten Reminder-Dubletten |
| R02 | Eigene Erinnerungen mit Titel und Beschreibung | ✅ | Kalenderdialog mit optionalem Bewerbungsbezug |
| R03 | Fällige, heutige, zukünftige und alle offenen Termine filtern | ✅ | Filterauswahl, Suche und Seitenwechsel |
| R04 | Termine bearbeiten und verschieben | ✅ | Datum, Uhrzeit und Zeitzone; Eingaben bleiben bei Fehlern erhalten |
| R05 | Erinnerungen erledigen oder verwerfen | ✅ | Aktionen in der Nachfassliste |
| R06 | Abgeschlossene eigene Erinnerungen anzeigen | ✅ | Filter „Abgeschlossene“; erneutes Abschließen gesperrt |
| R07 | Nachfassen einer Bewerbung abschließen | ✅ | Termin wird geleert; Abschluss im Aktivitätslog gespeichert |
| R08 | Endstatus und archivierte Bewerbungen berücksichtigen | ✅ | Automatische Nachfasstermine werden ausgeblendet; eigene Erinnerungen bleiben unabhängig |
| R09 | Zeitzonen und Sommerzeitwechsel korrekt behandeln | ✅ | UTC-Speicherung; Auswahl des ersten/zweiten Vorkommens einer doppelten Uhrzeit |
| R10 | Ungültige ältere Termine zur Korrektur anzeigen | ✅ | Prüfhinweis in der fälligen Liste |
| R11 | Fälligkeit im Hauptfenster sichtbar machen | ✅ | Kennzahl auf Übersicht und Anzahl in Navigation; Prüfung jede Minute bei geöffneter App |
| R12 | Zugehörige Bewerbung direkt öffnen | ✅ | Aktion aus der Nachfassliste |
| R13 | Systembenachrichtigungen, Tray oder Betrieb bei geschlossener App | 🔮 | Nicht Teil der aktuellen Erinnerungsfunktion; eigener Scope nötig |
| R14 | Wiederkehrende Erinnerungen | 🔮 | Nicht Teil des bisherigen MVP-Plans |
| R15 | Lokale Toasts in der laufenden App | ✅ | Speichern, Backup, Versandstatus und steigende Fälligkeit; Einblendung, Schließen, Timeout |
| R16 | Benachrichtigungsoptionen | ✅ | Kategorien, Dauer und reduzierte Bewegung konfigurierbar |

## 4. Vorlagen, DOCX und PDF

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| D01 | DOCX-Vorlagen importieren und neue Versionen anlegen | ✅ | Import-/Versionsdialog und Vorlagenliste |
| D02 | Platzhalter `{{NAME}}` erkennen | ✅ | Auch über Word-Text-Runs sowie in Tabellen, Kopf-/Fußzeilen, Fuß-/Endnoten und Kommentaren |
| D03 | Platzhalter zu Feldern zuordnen und Pflichtwerte festlegen | ✅ | Mapping-Dialog mit manuellen Werten als Alternative |
| D04 | Werte aus Bewerbung, Profil, Unternehmen und Kontakt übernehmen | ✅ | Dokumentdialog; automatische Kontaktwerte bei genau einem verknüpften Kontakt |
| D05 | Fehlende Pflichtwerte und offene optionale Platzhalter melden | ✅ | Validierung vor Erzeugung und Ergebnisnachricht |
| D06 | DOCX erzeugen und einer Bewerbung zuordnen | ✅ | Konkrete Vorlagenversion wird verwendet |
| D07 | Originalvorlage und Versionsbezug schützen | ✅ | Kopien, unveränderliche Versionen und Hashprüfung |
| D08 | Dokumentensätze und Herkunft speichern | ✅ | Eigene Verwaltung mit Varianten/Herkunft und Dateiöffnung |
| D09 | Vorher-/Nachher-Textvorschau | ✅ | Temporär, ohne gespeicherten Dokument-Datensatz |
| D10 | PDF über LibreOffice erzeugen | ✅ | Echte LibreOffice-Konvertierung und persönliche PDFs mit Seitenumbrüchen geprüft; Fehler/Zeitlimits und Originalschutz |
| D11 | PDF in der App anzeigen | ✅ | PDF-Viewer; Speicherpuffer vermeidet Windows-Dateisperren |
| D12 | DOCX extern öffnen | ✅ | Dokumentliste öffnet zugeordnetes Windows-Programm |
| D13 | PDF als abgeleitete Dokumentversion speichern | ✅ | Herkunft und Dateimetadaten werden gespeichert |
| D14 | Komplexe Word-Layouts praktisch prüfen | ◐ | Echte zweitseitige Vorlagen mit Bildern/Tabellen/Kopf-/Fußzeilen technisch geprüft; eigene komplexe Layouts am Ende abnehmen |
| D15 | Globale, erweiterte Vorlagenbibliothek | 🔮 | Noch kein Bibliotheksservice oder Bibliotheksdialog |
| D16 | E-Mail-/Workflow-Vorlagen verwalten | ✅ | E-Mail-Bibliothek und Builder-Graphvorlagen mit Versionen, Duplikaten, Vorschau und Transfer |
| D17 | Persönliche Bewerbungsanhänge aus Zeilendaten | ✅ | Gleiche Excel-/Listenwerte erzeugen persönliche Mail, DOCX und echte PDFs; zwei unterschiedliche PDFs tatsächlich über Gmail geprüft |
| D18 | Gemeinsame Vorlagensuche und DOCX-Duplikate | ✅ | Typfilter/Versionen, genaue Mailfassung bearbeiten; unabhängige DOCX-Kopie mit Mapping/Pflichtwerten/Beschreibung und Änderungsprüfung |
| D19 | Gerenderte Mailvorlagen | ✅ | Live-HTML im Editor, persönliche Nachricht/Quelltext als Vorschau-Tabs, geänderte Werte sperren Übernahme; externe Ressourcen blockiert |
| D20 | Dokumentensätze als ZIP exportieren | ✅ | DOCX/PDF nach Filter/Auswahl/Formaten, Dateiprüfung, fehlende PDFs bestätigen, Manifest/Bericht, Abbruch und atomare Ausgabe |

## 5. CSV-/XLSX-Import

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| I01 | CSV und XLSX einlesen | ✅ | Dateiauswahl und Quellvorschau |
| I02 | Unternehmen, Kontakte und Bewerbungen importieren | ✅ | Zielauswahl im Importdialog |
| I03 | Spaltenmapping und Zuordnungsvorschläge | ✅ | Zuordnungsoberfläche |
| I04 | CSV-Zeichensatz/Trennzeichen und Excel-Blatt wählen | ✅ | Importoptionen und erneute Vorschau |
| I05 | Importprofile speichern und wiederverwenden | ✅ | Profilauswahl |
| I06 | Werte validieren und Fehler je Zeile anzeigen | ✅ | Zeilenprotokoll mit Original- und Zielwerten |
| I07 | Duplikate prüfen | ✅ | Überspringen, korrigieren oder ausdrücklich neu anlegen |
| I08 | Fehlerhafte Zeilen korrigieren und erneut prüfen | ✅ | Editor erhält auch lange mehrzeilige Texte |
| I09 | Import pausieren und nach Neustart fortsetzen | ✅ | Pause zwischen Zeilen; bereits importierte Zeilen bleiben abgeschlossen |
| I10 | Quelldatei und Laufkonfiguration festhalten | ✅ | Kopie, Hash und eigenständiger Konfigurationssnapshot |
| I11 | Datensatz und Importbeleg atomar speichern | ✅ | Fehler einer Zeile blockieren andere gültige Zeilen nicht |
| I12 | Importhistorie und Seitenwechsel | ✅ | Eigene Importseite |
| I13 | Profile/Stellen als weitere Importziele | 🔮 | Aktueller Import unterstützt nur die drei genannten Ziele |
| I14 | Allgemeiner CSV-/XLSX-Datenexport | ✅ | Unternehmen/Kontakte/Profile/Stellen/Bewerbungen/Versandberichte; Filter/Auswahl, Spalten, Ziel, Datumstypen, Formelzeichen und atomare Ausgabe; bis 10000 Zeilen |
| I15 | Importzeilen als gemeinsame Datenquelle | ✅ | Lauf/Blatt wählen, alle Quellspalten zuordnen, Korrekturen nutzen; gültige Vorschau-/importierte Zeilen, mehrseitige Auswahl und Herkunftssnapshot |
| I16 | Manuelle Liste und Excel-Zellen einfügen | ✅ | Editierbare Tabelle mit Anrede/Name/E-Mail/Firma/Stelle/Anschreiben, eigenen Feldern und Strg+V; DOCX-Text gezielt in eine Zelle übernehmen |
| I17 | Strukturierte Dokumentquellen | ✅ | DOCX-Tabellen/PDF-Linien oder Textspalten; Kopfzeile, Zeilenauswahl, ausdrückliche Feldzuordnung/Bestätigung, Quellwerte und Datei-/Tabellenherkunft in gemeinsamer Liste; Scans benötigen vorher OCR |
| I18 | Wiederverwendbare Quellprofile und Standardwerte | ✅ | Projektweit speichern/laden; Leerwerte auffüllen oder erhalten, persönliche Überschreibungen danach |
| I19 | Gespeicherte Datenlisten | ✅ | Bearbeiten, wiederverwenden und eigene Kopie speichern; stabile Zeilenkennungen und Konflikterkennung; Bulk/Word Replace |

## 6. E-Mail und Gmail

| ID | Feature | Stand | UI / offene Arbeit |
|---|---|---|---|
| M01 | Gmail mit Google-Desktop-OAuth verbinden | ✅ | Echte Google-Desktop-Anmeldung und verbundene Konten geprüft; erneute Anmeldung über Neustarts wird in B4 weiter ausgebaut |
| M02 | Tokens im Windows Credential Manager speichern | ✅ | Automatische Erneuerung; nativer Vault separat geprüft |
| M03 | Verbundenes Konto auswählen und trennen | ✅ | E-Mail-Seite mit Kontowahl |
| M04 | Lokale Nachrichtenentwürfe anlegen/bearbeiten | ✅ | Empfänger, CC/BCC, Betreff, Text/HTML und Bewerbungsbezug |
| M05 | Entwürfe zu Gmail synchronisieren | ✅ | TEST 3 tatsächlich zu Gmail synchronisiert und zurückverglichen; anschließend einmal gesendet |
| M06 | Signaturen anlegen und auswählen | ✅ | Signaturdialog und Auswahl im Editor |
| M07 | Externe Dateien und Projektdokumente anhängen | ✅ | Auswahl, Kopie und Validierung vor Auftragsvorbereitung |
| M08 | Feste Versandaufträge inklusive MIME und Anhängen | ✅ | Empfänger, Inhalt und Dateien bleiben als Snapshot erhalten |
| M09 | Auftrag prüfen und ausdrücklich freigeben | ✅ | Separater Freigabedialog |
| M10 | Sofortiger oder geplanter Versand | ✅ | TEST 3 sofort und TEST 4 über Terminlauf tatsächlich gesendet; Empfang und PDF-Anhänge bestätigt |
| M11 | UTC-Zeitplanung mit lokaler Zeitzone | ✅ | Zeit-/Zoneneingabe mit Sommerzeitvalidierung |
| M12 | Versandplanung in laufender App aktivieren | ✅ | Pro Sitzung einschaltbar; Prüfung alle 15 Sekunden |
| M13 | Überfällige Aufträge nach Neustart/Standby sperren | ✅ | Neue Freigabe vor Nachversand erforderlich |
| M14 | Versandversuche, Fehler und Historie anzeigen | ✅ | Auftragsliste und Detaildialog |
| M15 | Unklare Ergebnisse vor Wiederholung abgleichen | ✅ | Message-ID und SENT-Label; kein automatischer erneuter Send-Aufruf |
| M16 | Rate Limits, HTTP-Fehler und Zeitlimits behandeln | ✅ | 429/5xx/Timeout beim Senden gelten als unklar |
| M17 | Auftrag abbrechen und sicher gescheiterte Aufträge erneut vorbereiten | ✅ | Zustandsabhängige Aktionen |
| M18 | Reale Google-Anmeldung, Entwürfe, Anhänge und Testversand abnehmen | ✅ | TEST 1–4 konkret freigegeben, gesendet und vom Benutzer als angekommen bestätigt; TEST 3/4 samt PDF-Layout und Gmail-Hashvergleich |
| M19 | Öffentliche Google-OAuth-Verifikation / Verteilung | ⏳ | Öffentliche OAuth-Verifikation und Verteilungsbedingungen in B5 prüfen |
| M20 | Weitere E-Mail-Provider | 🔮 | Providerabstraktion als Basis vorhanden; andere Provider fehlen |
| M21 | Bulk-E-Mail-Aufträge | ✅ | Gemeinsame Freigabe, Direkt-/Planversand, Pause/Abgleich/Neustartschutz, Budget/Fenster und Hintergrund in offener App; echte Gmail-Testläufe bestanden, native Bedienabnahme am Ende |
| M34 | Bulk-Bewerbungen aus Excel/Listen | ✅ | Excel-/Listenwerte, persönliche echte PDFs und optionale Domain-Bewerbungen mit Versandbelegen; durchgehende lokale Kette geprüft, eigene Daten am Ende abnehmen |
| M24 | Einzelauftrag im Arbeitsbereich | ✅ | Auswahl/Bearbeitung → vorbereiten → prüfen/freigeben → manuell senden; Termin, Status, Storno und Abgleich; reale Gmail-Abnahme separat |
| M27 | Nachrichten aus Bewerbungs-/Kontaktkontext | ✅ | Arbeitsbereich/Bewerbungs-/Kontaktliste; Empfängerwahl, Betreff/Texteinstieg, Dokumentvorschläge mit ausdrücklicher Auswahl; Bestätigung vor Überschreiben |
| M28 | Absender nach Anmeldung für alte Entwürfe wählen | ✅ | Im Vorbereitungsdialog; ein Konto vorgeschlagen, mehrere ausdrücklich wählen; atomare Zuordnung |
| M29 | Sofortversand auch vor geplantem Termin | ✅ | Freigeben & jetzt senden / Jetzt senden nach Bestätigung; Scheduler hält Termin ein; Protokoll |
| M30 | Konto und Scheduler direkt im Arbeitsbereich | ✅ | Verbundene Adresse, Gmail verbinden, gemeinsame Scheduler-Auswahl mit E-Mail-Seite |
| M31 | Gestaltete OAuth-Abschlussseite und Schließen-Button | ✅ | Responsive Hell/Dunkel-Seite mit Pixelart-Logo, ehrlichem App-Status, Tastaturfokus und Schließen-Fallback; State/PKCE/Loopback und Rückmeldungen geprüft, echter Browserablauf manuell offen |
| M32 | Versandaktionen passend zum Modus beschriften | ✅ | Ohne Termin „Senden“, mit Termin „Versand planen“; Prüfung/Bestätigung bleibt |
| M33 | Bulk-Aufträge im Builder erstellen und planen | ✅ | Konto, Sofortvorbereitung oder Termin, Zeitzone und Abstand; atomare Entwürfe/Planung, feste Aufträge im Worker und anschließende Prüfung/Freigabe |
| M25 | Wiederverwendbare E-Mail-Vorlagen | ✅ | Betreff/Text/Format, Versionen, Duplikate, Namenssuche, Projekt-/eigene Werte, Pflichtwertprüfung; Einzelentwürfe und persönliche Bulk-Entwurfsgruppen |
| M26 | Newsletter-Kampagnenverwaltung | 🔮 | Eigener Kampagnenablauf noch nicht konkret geplant |
| M22 | Bestehende Signaturen bearbeiten | ✅ | Verwaltungseditor mit Konfliktprüfung und eindeutiger Standardsignatur |
| M23 | Standardkonto und Standardsignatur verwalten | ✅ | Bevorzugtes Konto/Format, Projektvorgaben, Signaturbearbeitung und eindeutige Standardsignatur |

## 7. Alle vorhandenen UI-Bereiche und Änderungen

| Bereich | Vorhanden | Noch umzusetzen / abzunehmen |
|---|---|---|
| Start und Navigation | ✅ Vierzehn Seiten; ohne Projekt nur Projekte/Einstellungen, Öffnen führt in Arbeitsbereich | ⏳ Manuelle Windows-/DPI-Abnahme |
| Übersicht / Projekte | ✅ Projektassistent mit drei Schritten, Profil/Signatur und Zusammenfassung; nach Öffnen Arbeitsbereich | ✅ DE/EN, Konto-/Vorlagenvorgaben und spätere Projektvorgabenverwaltung |
| Arbeitsbereich | ✅ Modi, Ziel, direkte Editoren/Vorlagen, Einzel-/Bulk-Aufträge; neue Export- und Word-Replace-Aktionen | ✅ Globale/Projektvorgaben, Kontobudget, Versandfenster und Hintergrund in offener App |
| Toasts | ✅ Lokale Hinweise mit Einblendung, automatischem Ausblenden und Schließen | ✅ Kategorien, Dauer und reduzierte Bewegung; native Systemhinweise sind kein beauftragter Abschlussumfang |
| Projektleiste | ✅ Neu, Öffnen, Schließen, Backup, Ordner, Aktualisieren, dauerhaftes Hell/Dunkel und Einstellungen | ✅ geprüfte Wiederherstellung in neuen Projektordner |
| Bewerbungen | ✅ Suche, Liste, Erfassung, Bearbeitung, Statuswechsel, Kontaktzuordnung | ✅ Sichtbare Historie und eigene Statusverwaltung |
| Unternehmen | ✅ Erfassung, Bearbeitung, Suche, Kontakte und Hauptkontakt | ✅ Adressen/Zusatzfelder und Archiv/Papierkorb |
| Kontakte | ✅ Erfassung, Bearbeitung, Suche und mehrzeilige Notizen | ✅ Zusatzfelder und Archiv/Papierkorb |
| Bewerberprofile | ✅ Eigene Verwaltungsseite | ✅ Adressen und Zusatzfelder |
| Stellen | ✅ Eigene Verwaltungsseite mit Unternehmen, Ort, Referenz und Frist | ✅ Stellenbeginn und Zusatzfelder |
| Vorlagen | ✅ Gemeinsame Suche/Typfilter/Versionen, DOCX-Import/Mapping/Duplizieren und gerenderte HTML-Mailvorschau; Einzel-/Bulk-Entwürfe | ⏳ Gemeinsame manuelle Abnahme und globale Bibliothek |
| Dokumente | ✅ Liste, externes DOCX-Öffnen, PDF-Erzeugung und PDF-Anzeige | ⏳ Eigene Dokumentensatzverwaltung und reale Layout-Abnahme |
| Nachfassen | ✅ Filter, Termine, Abschluss/Historie; konfigurierbare Info-Toasts | ⏳ Native Systemhinweise separat |
| Datenimport | ✅ Mapping, Profile, Optionen, Vorschau, Historie, Fehlerkorrektur, Duplikate und Pause | 🔮 Weitere Importziele nur bei späterer Erweiterung |
| E-Mail | ✅ Konten/Entwürfe/Freigabe/Versandhistorie; persönliche Gruppen, Budget/Fenster/Quotensperren und Hintergrund in offener App | ⏳ Reale Gmail-Abnahme; 🔮 weitere Provider/Kampagnen |
| Word Replace | ✅ Eigene Seite/Builder, Regeln/Fundstellen, persönliche DOCX/PDF-Kopien, Formatierung/Muster und gespeicherte fortsetzbare Läufe | ⏳ Echte PDF-/Layout-Abnahme |
| E-Mail-Builder | ✅ 26 Bausteinarten inkl. Textbedingungen/Zusammenführen, Quellen, Stecker, Renderer/Medien, Versionen/Autosicherung/Graphtransfer, Hotkeys/Panels und Bulk-Planung | ✅ Inline-Bilder, Gruppen und DOCX/PDF-Seitenlayout; ◐ native praktische Abnahme |
| Export | ✅ CSV/XLSX sowie DOCX/PDF-Dokumentpakete als ZIP mit Filter/Auswahl/Formaten, Manifest und Fehlstellenbericht; Hash-/Änderungsprüfung, Überschreibbestätigung und Abbruch | ✅ Exporthistorie; ◐ manuelle Excel-/ZIP-Abnahme |
| Gemeinsame Listen | ✅ Suche mit Enter, wörtliche `%`/`_`, 10–200 Zeilen je Datensatzseite, Ansichtsoptionen und Auswahlaktionen | ⏳ Vollständige Tastatur-/DPI-Abnahme |
| Gemeinsame Formulare | ✅ Pflichtfelder, Scrollbereich, mehrzeilige Texte und vorhandene Zuordnungen | ✅ DE/EN-Beschriftungen, Adressen und typisierte Zusatzfelder |
| Asynchrone Dialoge | ✅ Eingaben bei Speicherfehlern erhalten; laufende Speicherung gegen Schließen gesperrt | ⏳ Manuelle Prüfung aller Fehlerabläufe |
| Hintergrundarbeit | ✅ Qt-Worker für DB, Dateien, Imports und Netzwerk; Fortschrittsanzeige | ⏳ Durchgängige Release-/End-to-End-Abnahme |
| Tastatur | ✅ App-/Canvas-Belegungen, Speichern/Suchen/Navigation, Baustein-/Stecker-/Kantenwahl und Verbindung ohne Maus | ⏳ Praktische Fokus-/Tab-/Windows-Abnahme |
| Design | ✅ Acht Themes, responsive Aktionen/Formulare, kurze Übergänge, reduzierte Bewegung, konfigurierbare Toasts und Builder-Panels | ⏳ Native Windows-/DPI-/Tastatur-Abnahme |
| Sprache | ✅ DE/EN-Apptexte und Dialoge | Gespeicherte Sprache/Neustart, dynamische Anzeigen und Inhaltsschutz geprüft; native Bedienabnahme offen |
| Einstellungen | ✅ Design/Zeitzone, Benachrichtigungen/Bewegung, Export, Word Replace, Hotkeys, Builder/Autosicherung/Panels; projektbezogene Vorgaben | ✅ globaler Startmodus, Mail-/Listen-/Backup-Vorgaben; ✅ DE/EN-Apptexte und Dialoge |
| Protokolle/Diagnose | ✅ Aktivitäts-, Import- und Versandhistorie | ✅ Allgemeine Historienansicht, lokale Abläufe und bereinigter Diagnoseexport |

### Builder-Ausbau – neu beauftragte Funktionen

| Feature / UI | Stand | Verhalten / Restarbeit |
|---|---|---|
| Mehr Textarten | ✅ | Betreff, Beschreibung/Anschreiben, Absatz, Überschrift, HTML, Anrede, Gruß und Trennlinie zusätzlich zum universellen Text |
| Eigene Stecker | ✅ | Betreff an subject, HTML an body; erforderliche Datenfelder und passende Ausgabe prüfen |
| Text-/Mail-Vorschau | ✅ | Fertiger Renderer direkt im E-Mail-Baustein/Mail-Tab mit Empfänger, Betreff, Signatur und Anhängen; HTML standardmäßig, Mail-/Text-Miniaturen auf der Zeichenfläche; ungeprüfte Live-Skizze markiert |
| Bild / Video / PDF | ◐ | Autoload nach Zeilenprüfung im Eigenschaftenbereich; Bild-Miniaturen auf der Zeichenfläche, Zeilenwechsel und begrenzter Hintergrundcache; Video ohne Autoplay; echte Codecs manuell offen |
| DOCX-Vorschau | ✅ | Persönliche Textvorschau und echte PDF-Seitenlayoutvorschau im Editor; eigene Layouts am Ende abnehmen |
| Bulk-Erstellung / Planung | ✅ | Lokale Entwürfe oder feste Aufträge mit Start, Zeitzone und Abstand; Freigabe und Versandstart im Gruppenfenster |
| Reaktivität | ✅ | Direkte Vorschauen, aktualisierte Kanten, Autoload ohne gesperrten Editor, gemeinsame Vorschauzeile; veraltete Antworten verwerfen und geänderte Mediendateien erkennen |
| Navigation | ◐ | Bausteinsuche, Zoom, mittlere Maustaste, Anordnen/Undo, Tastaturstecker und einstellbare Panels; praktische Abnahme offen |
| Themevielfalt | ✅ | Acht dauerhafte Paletten mit vier passenden Hell-/Dunkel-Paaren und eigener Akzentfarbe |
| Arbeitsstandsicherung | ✅ | Unfertige Graphen/Regeln, Name, Basisversion, Planung und Ansicht im Hintergrund sichern/wiederherstellen; vor Wechsel/Backup/Schließen nachsichern, Konflikte pausieren |
| Links / Buttons / Listen | ✅ | Persönliche Beschriftung/URL, Aufzählung oder Nummerierung; HTML- oder Textausgabe und Live-Vorschau |
| Graphtransfer | ✅ | Portable JSON-Vorlagen, Format-/Graphprüfung, atomarer Export; beim Import Quellen/Dateien neu zuordnen, Konto/Signatur/Planung neu wählen, als eigene Version speichern |
| Weitere Bausteine / UI | ◐ | Textbedingungen, Zusammenführen, flexible Panels und kurze Übergänge fertig; Bausteingruppen/Inline-Bilder und PDF-Seitenlayout fertig; native Abnahme offen |

### Dauerhafte Einstellungen

| ID | Feature | Stand | UI / Verhalten |
|---|---|---|---|
| S01 | Projektunabhängige Benutzereinstellungen | ✅ | Eigene Seite und Aktion in der oberen Leiste |
| S02 | Acht Designs dauerhaft speichern | ✅ | Klar/Nacht, Elfenbein/Graphit, Minze/Wald, Rosé/Pflaume; Toolbar schaltet innerhalb des gewählten Paares um |
| S03 | Akzentfarbe wählen | ✅ | Vier Vorgaben und eigener Farbdialog; lesbare schwarze/weiße Beschriftung |
| S04 | Anzeigezeitzone dauerhaft speichern | ✅ | Bewerbungstermine/Heute verwenden die Zone; neue Erinnerungen übernehmen die Vorgabe |
| S05 | Verwerfen und Standardwerte | ✅ | Änderungen bleiben bis zum ausdrücklichen Speichern im Formular |
| S06 | Einstellungsdatei sicher ersetzen | ✅ | Temporäre Datei, Validierung, begrenzte Dateigröße und Erhalt bei Schreibfehlern |
| S07 | Beschädigte oder fremde Einstellungen behandeln | ✅ | Gültige Werte/Standardwerte laden; unbekannte Formate nicht überschreiben; Neu laden verfügbar |
| S08 | Sprache dauerhaft wählen | ✅ | DE/EN-Apptexte, Dialoge und Fach-/Fehlertexte ergänzt; Neustart, Rückwechsel und Daten-/Eingabeschutz geprüft |
| S09 | Toasts und reduzierte Bewegung | ✅ | Erfolg/Info/Hinweis/Fehler, Dauer 2–30 s, Info/Erfolg abschalten, anhaltende Fehler; reduzierte Bewegung für Übergänge/Toasts |
| S10 | Arbeitsbereich und Startvorgaben | ✅ | Standardmodus neuer Projekte und Startansicht dauerhaft wählen |
| S11 | E-Mail-Vorgaben | ✅ | Konto/Signatur/Format/Zeitzone und Versandvorgaben dauerhaft; Signaturverwaltung und Standardsignatur |
| S12 | Listen-, Export- und Backup-Optionen | ✅ | Listen-Seitengröße/Ansicht, Exportvorgaben sowie Backup-Ziel und Aufbewahrung dauerhaft |
| S13 | Word-Replace-Einstellungen | ✅ | Suchoptionen, fehlende Werte, Ersatzformatierung, Dateinamensmuster, Format/Ziel, LibreOffice-Pfad und Zeitlimit |
| S14 | Builder-Einstellungen | ✅ | Raster/Zoom/Einrasten, Autosicherung, Panels/Breiten, Standardbausteine/Reihenfolge und dauerhafte Undo-/Redo-Historie |
| S15 | Hotkeys | ✅ | App- und Canvas-Belegungen ändern/deaktivieren/zurücksetzen; Konflikte/Reservierungen und Hilfe, Tastaturverbindungen bei Canvas-Fokus; Versand/Freigabe separat |

## 8. Release und spätere Programmfunktionen

| ID | Feature | Stand | Restarbeit |
|---|---|---|---|
| H01 | Reproduzierbare automatisierte Tests | ✅ | Datenbank, Dateien, Domain, Dokumente, Import, Gmail, Bearbeitung, Erinnerungen und Qt |
| H02 | Manuelle Windows-End-to-End-Abnahme | ⏳ | Benutzer nimmt eigene Dateien, Windows-DPI/Tastatur/Browser und nativen Langlauf gesammelt am Ende selbst ab |
| H03 | Portable Build und Installer | ⏳ | Anschlussphase B5: Installer, Start ohne Entwicklungsumgebung und sauberes Nutzerkonto |
| H04 | Manueller Updateprozess | 🔮 | Release-/Upgradeablauf festlegen und prüfen |
| H05 | Backup-/Recovery-Abnahme | ◐ | Echtes Restore mit Dateihashes, beschädigten Archiven, Abbruch und langen Windows-Staging-Pfaden geprüft; eigenes Projekt am Ende abnehmen |
| H06 | Lizenzprüfung | ◐ | 34 Laufzeitpakete inventarisiert und 56 Notice-/Lizenzdateien gesammelt; Verteilungsprüfung und Installer in B5 |
| H07 | Datenschutz und Aufbewahrung | ◐ | Lösch-/Referenzschutz, Aufbewahrung und bereinigte Diagnose umgesetzt; eigene Aufbewahrung am Ende festlegen, Verteilungsinformationen in B5 |
| H08 | Diagnoseexport ohne sensible Inhalte | ✅ | Expliziter lokaler JSON-Export mit Runtime-/Integritäts-/Statusdaten; keine Nachrichten, Adressen, Pfade oder Tokens |
| H09 | Lokale Verarbeitung ohne notwendiges Cloud-Backend | ✅ | Gmail benötigt Netzwerk; Projektdaten bleiben lokal |
| F01 | Rechnungen und Angebote | 🔮 | Geschäftsmodell, Vorlagen und Benutzerabläufe noch nicht umgesetzt |
| F02 | Visueller E-Mail-/Workflow-Builder | ◐ | 26 Bausteinarten; Quellen, Dokumente, Layout, Inline-Bilder, Gruppen, Versionen/Autosicherung/Graphtransfer, Hotkeys und Bulk; native Sammelabnahme offen |
| F04 | Eigener Word-Replace-Bereich | ✅ | Eigener Bereich mit Regeln/Vorschau, festen persönlichen Kopien, Pause/Fortsetzen/Abbruch; echte PDF-/Layoutprüfung und Excel-Werte bestehen |
| F03 | Weitere Geschäftsprozesse | 🔮 | Erst nach Bewerbungs-MVP konkret planen |

## Nächste Umsetzung

Verbindlich: [Finale TODO](34_Final_TODO.md), A1–A7:

1. Dokumente/Word Replace und echtes Layout.
2. Builder-Gruppen, Inline-Bilder, Anhänge und vollständige Kette.
3. Verwaltungsfelder, Status/Signaturen, Historien, Dokumentensätze und Archivabläufe.
4. Vier reale Testmails samt PDFs/Termin und Empfang geprüft; native Bedienung am Ende selbst abnehmen.
5. DE/EN-Apptexte implementiert; praktische UI-/Windows-Abnahme abschließen.
6. Daten-/Backup-/Recovery-Abschluss.
7. Versions-/Lizenzabschluss, Gesamtlauf und gemeinsame Abnahme.

Danach B1–B5: eigene fertige Vorlagen, Dokumentation/Tooltips mit Settings,
geführte Projektmodi, Anmeldung über Neustarts, Installer und Nutzeranleitung.

Alle beauftragten Punkte mit Checklisten und Abnahmekriterien:
[Arbeitsbereich-TODO](14_Workspace_TODO.md).

Die als „später“ markierten Erweiterungen sind keine zusätzlichen Zusagen für den MVP.
Aktueller Teststand: [Technischer Abschluss](40_Technical_Completion.md). Historische reale lokale Nachweise: [A1–A3-Prüfbericht](36_Completion_Test_Report.txt).
40 zusätzliche Fälle für Verwaltung, Builder, Projektpublikation, UI und Migration.
Historischer Endspurt: 561 Tests, 560 bestanden und ein opt-in Windows-Vault-Test
in dieser Suite absichtlich übersprungen. Das vorherige Paket enthielt 165 Qt-Tests, 42 Builder-/Arbeitsstands-, 8 Bulk-Entwurfs-, 20 Gruppenversand-, 10 Datenquellen-/Anschreiben-, 13 Reminder-,
14 Einstellungs-, 36 neue Bibliotheks-/Export-/Word-Replace- und 10 Datenverwaltungstests. Der native Vault wurde in einem früheren Schritt separat geprüft.
33 neue Paketprüfungen (23 Kern/10 Qt): OAuth-Rückmeldung/Loopback, gemeinsame
Vorlagen, DOCX-Duplikate, echte DOCX-/PDF-Tabellen, Dokumentpakete, Canvas-Tastatur,
alte Belegungen, Graphtransfer sowie Fehler-/Abbruch-/Änderungsfälle.
Logo256.png ist als Fenster-/Appicon, Seitenleistenmarke und Browserlogo eingebunden.
Die Rastergrafik wird für die sichtbare Marke ohne Glättung skaliert.
Anleitungen: [GUI](07_Desktop_GUI.txt), [Datensätze](10_Record_Management.txt),
[Nachfassen](11_Reminders.txt), [Dokumente](06_Document_Workflow.txt),
[Import](08_Import_Workflow.txt), [Gmail](09_Gmail_Workflow.txt),
[Einstellungen](13_Settings.txt).
Einzelaufträge: [Arbeitsbereich](15_Mail_Workspace.txt).
Projektanlage: [Projektassistent](16_Project_Wizard.txt).
Kontextübernahme: [Bewerbung / Kontakt](17_Mail_Context.txt).
Nachrichtenvorlagen: [E-Mail-Vorlagen](18_Mail_Templates.txt).
Persönliche Entwurfsgruppen: [Bulk-Ablauf](19_Bulk_Drafts.txt).
Excel-/Listenwerte und persönliche Anschreiben: [Datenquellen](20_Bulk_Data_Sources.txt).
Gemeinsame Freigabe und steuerbarer Versand: [Gruppenversand](21_Bulk_Delivery.txt).
Neue Anleitungen: [Datenbibliothek](22_Data_Source_Library.txt), [Export](23_Data_Export.txt),
[Word Replace](24_Word_Replace.txt). [Gebündelte manuelle Abnahme](25_Bundled_Acceptance.md).
Tastaturhilfe und eigene Belegungen: [Hotkeys](26_Hotkeys.txt); acht Backend- und fünf Qt-Tests.
Visueller Ablauf mit Daten, Dokumenten und lokalen Entwürfen: [E-Mail-Builder](27_Email_Builder.txt).

Aktueller Ausbau: [Projekt/Bulk/Word Replace/UI und Builder-Textwahl](29_Sprint_7_Expansion.md).

Vorheriges Paket: 48 zusätzliche Prüfungen (31 Kern/Migration, 17 Qt); damaliger Stand 530 Tests / 529 bestanden / 1 optional übersprungen.

Endspurt: [neue Funktionen und Grenzen](31_Endspurt.md),
[Prüfbericht](32_Endspurt_Test_Report.txt). Backup-/Recovery-Kern und lokale
Diagnose sind implementiert; praktische Abnahme und Release bleiben offen.
31 zusätzliche Endspurt-Tests: 20 Kern / 11 Qt; Gesamtlauf 561 / 560 bestanden / 1 optional übersprungen.

Realer Gmail-Test am 12.10.2026 erfolgreich: Anmeldung, exakt zwei freigegebene
Testnachrichten ohne Anhänge, zwei Versandversuche und zwei Sent-Aufträge mit
Gmail-Nachrichtenkennungen. Fenster ohne Versuch, Hintergrundabschluss und
erreichtes Budget geprüft. TEST 3/4 ergänzen PDF-/Terminprüfung; alle vier Mails
sind bestätigt angekommen. Native Gruppenbedienung bleibt zur Endabnahme offen. [Nachweis](abnahme/gmail_live_result.json).
