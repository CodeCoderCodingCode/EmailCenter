# Finale TODO – Abschluss und anschließender Ausbau

Stand: 14.10.2026. Verbindliche Reihenfolge aus Featurematrix, Workspace-TODO
und Sammelabnahme. Ältere Paketlisten sind Detailnachweise und keine zusätzlichen
Abschlussaufgaben. Neue Wünsche werden als neue Aufgaben ergänzt.

**Aktueller Benutzerauftrag:** Das Programm wird zuerst technisch bis zur
Abnahme fertiggestellt. Eigene Dateien und praktische Windows-/Bedienprüfungen
führt der Benutzer gesammelt am Ende selbst durch. Diese offenen Abnahmepunkte
fordern jetzt weder eigene Dateien noch eine Zwischenfreigabe.
Technischer Abschluss und persönliche Endfreigabe werden getrennt protokolliert.

**Technischer Stand:** A1–A7 und B1–B5 sind technisch abnahmebereit. Persönliche Endabnahme und Google-Testnutzer-Einträge bleiben offen.

**Benutzerrückmeldung zum Kernworkflow:** „Klappt alles perfekt“ mit dem letzten
Ergänzungswunsch für den PDF-Dateinamen. Dieser Wunsch ist umgesetzt und geprüft;
[PDF-Dateinamensfeld und Nachweis (A11)](44_Builder_PDF_Names.md).
Die Anschlussphase B1–B5 ist umgesetzt; Release-Nachweise stehen in docs/46_Release_1_0.md. Einzelne bisher nicht ausdrücklich
bestätigte native/restliche A-Prüfungen bleiben als separate Nachweise aufgeführt.

**Aktueller Schwerpunkt: dein Excel-Bewerbungsablauf 1–10.** Direkter Import im
Builder, alle Spalten als Platzhalter, wiederholte Zieladressen nach ausdrücklicher
Auswahl und dauerhaft gespeicherte persönliche DOCX sind umgesetzt. Neues Paket
mit 20 Fake-Zielen und Anleitung: [Excel-Builder-Gesamtablauf](41_Builder_Excel_Workflow.md).
Die frühere 644er-Suite und der UI-Langlauf gelten für den historischen Schema-13-
Stand; neue Prüfungen und Migration 14 sind im aktuellen Paket dokumentiert.

**Aktuelle Nachbesserung:** PDF-Dateinamen direkt im DOCX→PDF-Baustein einstellen;
Vorschau, gespeicherte Dateien und Mailanhänge verwenden dieselben persönlichen
Namen. Original-DOCX-Namen bleiben für die PDF-Stufe erhalten.
[Aktueller Nachweis (A11)](44_Builder_PDF_Names.md).
[Vorherige Regel-/Feedback-Erweiterung (A10)](43_Builder_Feedback_And_Review.md).
Der [vorherige Importfix (A9)](42_Builder_Mapping_Fix.md) bleibt enthalten.

## Release 1.0.1 – aktueller Abschluss-Sprint

- [x] Builder: Datum, Uhrzeit, Text bereinigen, Variable / Festwert einschließlich Werte-Verkettung und eingefrorener Vorschauzeit.
- [x] 14 Designs, wählbare Fade-/Slide-/Zoom-Übergänge, Hover/Fokus und Reaktionszeit; reduzierte Bewegung.
- [x] Drei DOCX-, drei E-Mail- und vier Builder-Vorlagen.
- [x] Bebilderter Offline-Guide mit Sprungmarken für alle Bereiche, Bausteine und Settings; Hilfe / F1.
- [x] Geführter Arbeitsbereich und schaltbare Tooltips.
- [x] Gemeinsamer Desktop-OAuth-Client: Nutzer brauchen keine JSON-Auswahl; eigene Anmeldung und Windows-Tresor.
- [x] Windows-EXE und Installer mit optionalen Verknüpfungen und enthaltenem PDF-Konverter.
- [x] DLL-/Startpfade: vollständiges Laufzeitpaket prüfen, irreführende Zwischen-EXE entfernen und eindeutigen Installer-/Programmstart ergänzen.
- [ ] Deine finale Abnahme einschließlich Installation/Gmail auf einem weiteren Rechner und nativer Windows-Bedienung.

Nachweise und genaue Prüfgrenzen: [Release 1.0.0](46_Release_1_0.md), [DLL-Korrektur 1.0.1](47_Windows_DLL_Fix.md).
Google-Einträge erledigt der Betreiber selbst: [Anleitung](45_Release_Operator.md).
## Sprint-Gesamtstand

| Sprint | Technisch geschafft | Noch offen |
|---|---|---|
| 0 | Anforderungen, Architektur, Laufzeit-/Lizenzinventar | Finale Freigabe A7 |
| 1 | Datenbank, Schema 14, Migrationen, Integritätsregeln | Gesamtabnahme A7 |
| 2 | Projekte, Dateien und geprüfte Backups | Eigenes Projekt A6 |
| 3 | Bewerbungsdomain, Verwaltung, Adressen, Status, Historien | Sammelabnahme A3 |
| 4 | Vorlagen, echte persönliche DOCX/PDF, Word Replace | Eigene Layouts A1 |
| 5 | Excel/CSV/manuelle Quellen, direkter Builder-Import, alle Spalten und Export | Eigener Gesamtprozess A7 |
| 6 | Einzel/Bulk, Planung, Freigabe, vier echte Gmail-Testmails samt PDFs/Termin | Native Versandbedienung A4 |
| 7 | UI, Builder, Medienvorschau, Themes, Hotkeys, DE/EN und Toasts | Native DPI/Tastatur/Browser A5 |
| 8 | Backup/Restore, Recovery, Diagnose und Regressionen | Eigene Recovery, Langlauf und Freigabe A6/A7 |

## Bereits geschafft

- [x] Projektverwaltung, Datenbank und Bewerbungsdomain.
- [x] Gemeinsame Excel-/CSV-/Dokument-/manuelle Datenquellen und Export.
- [x] Vorlagenverwaltung, persönliche DOCX und eigener Word-Replace-Bereich.
- [x] Einzel-/Bulk-Aufträge mit Vorschau, Freigabe, Planung, Budget und Hintergrundlauf in offener App.
- [x] Echte Gmail-Anmeldung und zwei freigegebene Testmails: 2 Versuche / 2 Sent; Fenster, Budget und Hintergrund geprüft.
- [x] Zusätzlich freigegebene TEST 3/4: echte Gmail-Entwurfssynchronisierung, sofortiger und geplanter Versand mit zwei unterschiedlichen persönlichen PDFs; 2 neue Versuche / 2 Sent, Gmail-Rückvergleich stimmt.
- [x] Builder mit 26 Bausteinarten, Mailrenderer, Medienvorschau, Graphvorlagen, Autosicherung und dauerhafter Undo-/Redo-Historie.
- [x] Themes, Toasts, Hotkeys, globale/Projekt-Einstellungen und gespeicherte Sprachwahl.
- [x] DE/EN-Apptexte, Dialoge, dynamische Anzeigen und Daten-/Eingabeschutz; Neustart und vier Qt-Skalierungen geprüft. [A5-Paket](38_Localization_UI_Completion.md).
- [x] Backup-Aufbewahrung, geprüfte Wiederherstellung und lokaler Diagnoseexport.
- [x] Historischer A7-Gesamtlauf: 644 Tests, 643 bestanden, ein optionaler nativer Vault-Test übersprungen; geprüfte Quellen während des Laufs unverändert.

## Aktueller Fortschritt – Excel / Builder / Bewerbungen 1–10

- [x] Kernworkflow vom Benutzer als funktionsfähig bestätigt; letzten PDF-Dateinamenswunsch ergänzen.
- [x] PDF-Dateiname am Konverter einstellen, Originalname erhalten, persönliche Excel-Spaltenwerte im gespeicherten PDF und MIME-Anhang prüfen.
- [x] Regelnummern, Editor-Markierung/Fokus und tatsächliche Zeilenfehler in Bausteinvorschauen ergänzen.
- [x] Offene DOCX-Restplatzhalter mit Leerzeichen/Umlauten erkennen; Bestätigung erst nach erfolgreicher Vorschau und klare Hinweise bis zur Gruppenfreigabe.
- [x] Übernahmefehler bei vorhandenen Word-Replace-Regeln beheben; Namenskollisionen erhalten und konkrete Zuordnungsfehler anzeigen.
- [x] Dieselbe XLSX mit vorhandener DOCX-/Word-Replace-Kette und erneuter Übernahme aller 20 Zeilen im UI prüfen.

- [x] XLSX mit 20 erfundenen Zielen und genau fünf gewünschten Empfängeradressen, jeweils viermal, bereitstellen.
- [x] Excel-/CSV-Datei direkt im Datenbaustein laden; Workflow-Zeilen ohne erforderliche Domain-Verknüpfungen auswählen.
- [x] Alle Quellspalten für persönliche Mailtexte, Betreff und Word-Replace-Regeln verfügbar machen.
- [x] Wiederholte Adressen nach ausdrücklicher Builder-Auswahl erlauben; normale Duplikatsperre und Freigabeprüfung erhalten.
- [x] Personalisierte DOCX dauerhaft speichern, auch bei ausschließlichem PDF-Mailanhang.
- [x] Zehn gezielte Regressionen und Migration für bestehende Schema-13-Gruppen ergänzen.
- [x] Aktuelle A11-Gesamtsuite mit unveränderten Quellen: 676 Tests / 675 bestanden / ein optionaler nativer Vault-Skip; acht neue Dateinamenprüfungen und DE/EN geprüft.
- [x] Genau diese XLSX im UI prüfen: 20 aktive Häkchen und 20 bereite persönliche Mailvorschauen.
- [x] Alle 20 Ziele mit echter DOCX/PDF-Konvertierung, drei Anhängen je Nachricht und geplantem Testprovider-Versand samt Pause/Neuöffnung/Fortsetzen prüfen; keine echten Mails.
- [x] Neues A11-Schema-14-Codearchiv mit CRC/SHA und denselben Quellen wie Gesamtsuite, Workflow und Excel-UI sichern; [aktuelles Ergebnis](abnahme/A11_Builder_PDF_Names/Completion_Result.json). [Vorheriger A10-Nachweis](abnahme/A10_Builder_Feedback/Completion_Result.json).
- [ ] Anschlussfunktionen B1–B5 umsetzen; die separate native/Recovery-Restprüfung bleibt unten dokumentiert.

## Vorheriger Fortschritt – A7 / technische Fertigstellung

- [x] A1 technisch umgesetzt: echter LibreOffice-Lauf, zwei persönliche PDFs (vier Seiten visuell geprüft), echte XLSX-Werte, Builder-PDF-Layoutvorschau, Pause/Fortsetzen, Abbruch und Schutz geänderter Ziele.
- [x] A2 technisch umgesetzt: Bausteingruppen, Inline-Bilder, persönliche Anhangnamen/Reihenfolge; echte Dokumentkette mit zwei lokalen Entwürfen und null Versandversuchen, MJPEG-Video im Editor dekodiert.
- [x] A3 technisch umgesetzt: strukturierte Adressen/Zusatzfelder, Stellenbeginn, Status-/Signaturverwaltung, Standardsignatur, Historien, Dokumentensätze, Archiv/Papierkorb und nachholbare Dateibereinigung.
- [ ] Benutzerabnahme am Ende: eigene Dokumente und Medien, tatsächliche Windows-Bedienung und Ausgabe im Mailclient. Anleitung: [A1–A3-Abnahmepaket](35_Completion_A1_A3.md).
- [x] Zusätzlich A6: echtes Backup/Restore samt Anhanghashes; native Dateisperre mit Bereinigungs-Retry nach Neuöffnung, beschädigtes Archiv, Abbruch, Aufbewahrung und Diagnoseexport geprüft; Schließen bei laufendem Vorgang korrigiert.
- [x] Bulk-Checkbox: aktives Listenelement bleibt beim Auswählen erhalten; Regression für wiederholtes An-/Abwählen ergänzt.
- [x] A5 technisch: englische Fach-/Fehlertexte, Projektassistent, dynamische Zustände, Sprachwechsel ohne Änderungen persönlicher Inhalte; 502 verwendete Beschriftungsquellen und Qt 100/125/150/200 % geprüft.
- [x] A4: TEST 3 synchronisiert und sofort gesendet; TEST 4 über Bulk-Service geplant, vor Fälligkeit pausiert, Projekt neu geöffnet, erneut geprüft und erst nach Termin gesendet. Native App-Bedienung bleibt offen. [Nachweis](39_Gmail_Attachment_Review.md).
- [x] Versteckte Builder-Buttons und Menüs besitzen ihre Seite bereits vor dem ersten Resize; beim Schließen werden alle zerstört.
- [x] Builder-Menüs folgen DE/EN zur Laufzeit ohne ausgelöste Aktionen oder veränderte Graphdaten.
- [x] Wiederherstellungs-Staging unter Windows unterstützt verlängerte temporäre Pfade; Abbruch entfernt auch solche Dateien und erhält Originale.
- [x] Durchgehende lokale Kette aus echten XLSX-/DOCX-/PDF-Dateien, zwei Bewerbungen, Versandstatus mit Testprovider, Export und Restore geprüft.
- [x] Letzten unveränderten Code vollständig prüfen: 644 Tests, 643 bestanden, ein optionaler Vault-Skip.
- [x] UI-Langlauf abgeschlossen: 540 Prüfungen in sechs Runden, null zurückbleibende Widgets/Fenster; neues Codearchiv CRC-/SHA-geprüft; [Abschlussnachweis](40_Technical_Completion.md).
- [ ] Benutzerabnahme A1–A7 am Ende; Anschlussaufträge B1–B5 bleiben beauftragt.

## A. Finale Abschlussliste – aktuelles Programm

### A1. Dokumente und Word Replace – Sprint 4 / 7

- [x] Echte LibreOffice-Konvertierung verfügbar machen und Konverterpfad prüfen.
- [x] Personalisierte DOCX/PDF aus Excel/manueller Liste prüfen: Werte, Bilder, Tabellen, Kopf-/Fußzeilen, Formatierung und Seitenumbrüche; Fehler beheben.
- [x] DOCX-Seitenlayoutvorschau im Builder über PDF-Konvertierung ergänzen; erzeugte PDFs vor Gruppenanlage prüfbar anzeigen.
- [x] Word-Replace-Pause/Fortsetzen, Abbruch und geänderte Ziele am echten lokalen Service prüfen; Windows-Bedienung am Ende selbst abnehmen.

**Fertig:** persönliche Werte und Layout stimmen; Originale bleiben erhalten.

### A2. Builder – Sprint 7

- [x] Wiederverwendbare Bausteingruppen erstellen, speichern und erneut einsetzen.
- [x] Inline-Bilder mit persönlicher Zuordnung und korrekter Mailausgabe ergänzen.
- [x] Anhangnamen und Reihenfolge bequem bearbeiten; Vorschau und Versandkopie stimmen überein.
- [x] Echte Bild-/PDF-Dateien und ein MJPEG-AVI im Editor prüfen; Decoder liefert echte Videobilder, ohne Autoplay.
- [ ] Weitere eigene Videoformate/Codecs und Ausgabe im tatsächlichen Mailclient abnehmen.
- [x] Datenquelle → Word Replace → echtes PDF/benannter Anhang/Inline-Bild → lokale Zweiergruppe prüfen; Undo/Redo und gespeicherte Gruppen automatisiert prüfen.
- [ ] Vollständige Kette im nativen UI samt Neustart am Ende selbst abnehmen.

**Fertig:** Vorschau und Auftrag passen zusammen; fehlende Eingaben sperren die
Ausgabe. Keine Editoraktion sendet selbstständig.

### A3. Offene Verwaltungsfunktionen – Sprint 3 / 5 / 7

- [x] Adressen und individuelle Zusatzfelder bearbeiten und fachlich validieren; Stellenbeginn im Formular ergänzen.
- [x] Eigene Statuscodes/-bezeichnungen verwalten und Status-/Aktivitätshistorie anzeigen.
- [x] Bestehende Signaturen bearbeiten und Konto-/Signaturauswahl vollständig verwalten.
- [x] Dokumentensätze mit Varianten/Herkunft in einer eigenen Verwaltung anzeigen.
- [x] Exporthistorie mit Dateien und Ergebnissen anzeigen.
- [x] Archivieren, Papierkorb, Wiederherstellen und endgültiges Löschen mit Regeln für Referenzen und Dateien ergänzen.

**Fertig:** Verwaltungsdaten sind bedienbar; Änderungen und Löschungen
beschädigen keine bestehenden Aufträge.

### A4. Versandabnahme – Sprint 6

- [x] Lokale Qt-Prüfungen: Excel/manuelle Liste/Builder, persönliche Versandkopien,
  Pause/Fortsetzen/Abbruch, geschlossenes Gruppenfenster, Neustart, Fehler und
  unklare Antworten mit Testprovider; kein erneuter Versand erledigter Aufträge.

- [x] Empfang der bereits gesendeten Testmails TEST 1 und TEST 2: Benutzer bestätigt am 13.10.2026 „Beide angekommen“.
- [x] TEST 3/4 mit unterschiedlichen persönlichen PDF-Anhängen lokal vorbereiten; MIME-Hashprüfung und Projekt-Neuöffnung bestehen. Inhalte, PDFs und Ablauf am 13.10.2026 konkret freigegeben: [Vorschau und Sammelprüfung](39_Gmail_Attachment_Review.md).
- [x] Gmail-Entwurfssynchronisierung, Terminlauf und persönliche Anhänge am echten Service prüfen: TEST 3/4, genau zwei neue Versuche; Empfänger/Inhalt/PDF-Hashes aus Gmail zurückgelesen und verglichen.
- [x] Empfang von TEST 3/4 und Darstellung beider zweitseitiger persönlicher PDFs: Benutzer bestätigt am 13.10.2026 „Beide angekommen, beide PDFs korrekt“.
- [ ] Benutzerabnahme am Ende – Bulk aus Excel/manueller Liste/Builder im UI prüfen: Empfänger, persönliche Werte, verschiedene Anhänge und Statusrückführung.
- [ ] Pause/Fortsetzen/Abbruch, geschlossenes Gruppenfenster und App-Neustart praktisch prüfen; erledigte Aufträge nicht erneut senden.
- [ ] Fehler/unklare Antworten kontrolliert prüfen; Abgleich statt blindem erneutem Versand.

**Fertig:** Empfänger, Inhalt, Anhänge, Termin und Status stimmen. Weitere reale
Nachrichten brauchen konkrete Freigabe; die bisherigen vier dürfen nicht erneut
versendet werden. Hintergrundversand benötigt eine geöffnete App.

### A5. Sprache und UI – Sprint 7B

- [x] Lokale Qt-Prüfungen für Themes/Vorgaben, Toasts, Tastaturereignisse und
  reaktive Steuerung während laufender Vorgänge; native Prüfung unten am Ende.

- [x] Englische App-Fachtexte, Fehlermeldungen und Dialoge ergänzen; Sprachwahl nach Neustart und Rückwechsel nach englischem Start prüfen. [Nachweis](38_Localization_UI_Completion.md).
- [x] Kleine Qt-Fenster und Projekt-/Datensatzdialoge bei 100/125/150/200 % rendern; Eingaben und Formatargumente erhalten.
- [ ] Kleine Fenster und tatsächliche Windows-Skalierung 100/125/150/200 % abnehmen.
- [ ] Fokus, Tab-Reihenfolge, Hotkeys, Middle-Mouse-Pan, Scrollbereiche und Abschluss-/Abbruchaktionen praktisch prüfen.
- [ ] Themes, reduzierte Bewegung, Toasts und Reaktivität bei langen Aufgaben prüfen; Fehler beheben.
- [x] OAuth-Abschlussseite DE/EN samt Schließen/Fallback automatisiert prüfen; Browserantwort und gespeicherte Kontoverbindung klar unterscheiden.
- [ ] OAuth-Abschlussseite inklusive Tab-Schließen/Fallback und Tastatur praktisch prüfen.

**Fertig:** Kernabläufe bleiben bedienbar; Sprache, Design und Einstellungen
bleiben nach Neustarts erhalten.

### A6. Daten, Backup und Recovery – Sprint 8

- [x] Lange temporäre Windows-Restore-Pfade mit echten Dateien prüfen; erfolgreicher
  Restore und Abbruch entfernen Staging und lassen Originaldateien unverändert.

- [x] Echtes lokales Builder-Testprojekt mit persönlichen PDF-/Bildanhängen sichern, in neuen Ordner wiederherstellen und Entwürfe/Dateien prüfen.
- [ ] Eigenes produktives Projekt sichern/wiederherstellen und Kernabläufe am Ende selbst abnehmen.
- [x] Beschädigte Archive/Abbruch automatisiert und mit echten Testdateien prüfen; echte Windows-Dateisperre, persistierten Bereinigungsnachweis und erneuten Versuch nach Projekt-Neuöffnung prüfen.
- [ ] Recovery-Bedienung und verwaiste Arbeitsdateien am eigenen Projekt am Ende selbst abnehmen.
- [x] Referenz-/Hashschutz, Archiv/Papierkorb und Backup-Aufbewahrung technisch prüfen; geänderte und unbekannte Backups bleiben im echten Lauf erhalten.
- [ ] Gewünschte Aufbewahrung/Löschung für eigene persönliche Daten am Ende selbst festlegen und abnehmen.
- [x] Backup-Schutz in Settings/Wiederherstellung anzeigen und dokumentieren: lokale ZIPs unverschlüsselt; App-Tokens getrennt im Windows-Tresor.
- [x] Diagnoseexport nochmals prüfen: automatisierte Positivliste und echter Workspace-Export; keine persönlichen Testwerte, Nachrichteninhalte, Pfade oder Zugangsdaten. [Nachweis](abnahme/A2_Builder/Diagnose_Ergebnis.json).

**Fertig:** Originalprojekte bleiben erhalten; Wiederherstellung aktiviert weder
Gmail-Konten noch Sendeläufe automatisch. Recovery ist nachvollziehbar.

### A7. Technischer Abschluss und Gesamtabnahme – Sprint 0 / 8

- [x] Tatsächlich geprüfte Windows-/Python-/SQLite-/LibreOffice-Versionen und Grenzen festhalten: [Laufzeit/Abhängigkeiten](37_Runtime_Dependencies.md).
- [x] 34 installierte Laufzeitpakete prüfen und 56 mitgelieferte Lizenz-/Notice-Dateien samt LibreOffice-Hinweisen sammeln; Paketierungsprüfung und öffentliche OAuth-Verteilung folgen in B5.
- [x] Gesamtsuite für A1–A3 ausführen: 601 Tests, 600 bestanden, ein optionaler nativer Tresor-Test übersprungen; weitere Änderungen erneut prüfen.
- [x] Historischen A5-Stand vollständig prüfen: 638 Tests, 637 bestanden / 1 optionaler Skip; unveränderte Quellprüfsummen. Zusätzlich 144 wiederholte UI-Prüfungen bestanden. [Prüfbericht](38_Localization_Test_Report.txt).
- [x] Kurzzeitige Windows-Sperren bei Projektpublikation begrenzt behandeln; dauerhafte Fehler und inzwischen bestehende Zielordner erhalten. Vier Regressionen, betroffene Profil-/UI-Abläufe und echte native Ordnersperre bestehen. [Nachweis](abnahme/A6_Recovery/Publication_Ergebnis.json).
- [ ] Sporadischen Qt-MemoryError aus UI-Zwischenlauf im nativen Langlauf beobachten; Ursache bei Wiederholung klären. Betroffene Einzeltests bestehen auch bei Wiederholung; [Prüfbericht](36_Completion_Test_Report.txt).
- [x] Kompletten lokalen Serviceablauf mit echten Dateien prüfen: Projekt → XLSX/Datenliste → persönliche DOCX/PDF → Vorschau → Bewerbungsaufträge → Testprovider-Status → CSV/XLSX → Backup → Wiederherstellung; zwei Testprovider-Versuche, kein realer Gmail-Aufruf.
- [x] Hidden-Builder-Ressourcenfehler und Windows-Staging-Pfadfehler samt Abbruch beheben; neue Regressionen bestehen.
- [x] Finale unveränderte Gesamtsuite: 644 Tests, 643 bestanden / ein optionaler Vault-Skip.
- [x] Längeren UI-Durchlauf abschließen: 540 Prüfungen in sechs Runden, 8 Minuten 38 Sekunden; Quellen unverändert, null reale Gmail-Aufrufe; [Abschlussnachweis](40_Technical_Completion.md).
- [ ] Benutzerabnahme am Ende: kompletten Ablauf mit eigenen Daten und nativer Bedienung prüfen.
- [x] Lokalen A1–A3-Codeprüfstand mit Schema 13, Prüfbericht und geprüftem Codearchiv sichern.
- [x] Vorherigen Abschlussprüfstand mit Schema 13, Prüfbericht und CRC-/SHA-geprüftem Codearchiv sichern; Metadaten: [Codearchiv](abnahme/Code_Snapshot.json).
- [x] Historischen A7-Abschlussstand abnahmebereit sichern: Schema 13, unveränderte Prüfquellen, Bericht und geprüftes Codearchiv.
- [ ] Benutzer-Gesamtabnahme am Ende protokollieren, dabei gemeldete Fehler beheben und persönliche Endfreigabe festhalten.

**Abschlussregel:** Nach technischer Fertigstellung und dokumentierten lokalen
Prüfungen ist das aktuelle Programm abnahmebereit. Die praktische Benutzerabnahme
am Ende und die persönliche Endfreigabe bleiben ausdrücklich offen. Installer und folgende
Einführungspunkte gehören gemäß Benutzerauftrag zur anschließenden Phase B.
Release 1.0.0 steht jetzt als Installer zur Verfügung. Historische
Sammelpakete werden über A1–A7 abgeschlossen.

## B. Danach – beauftragter Ausbau in dieser Reihenfolge

### B1. Eigene fertige Vorlagen

- [x] Anschreiben, vorformulierte Bewerbungs-/Auftragsmails und Nachfassmails bereitstellen.
- [x] Platzhalter/Pflichtfelder mit Beispieldaten erklären; Vorlagen auswählen, anpassen, duplizieren und versioniert verwenden.

### B2. Anschauliche Dokumentation und Tooltips mit Settings

- [x] Nutzerhandbuch mit Screenshots und Beispielen für beide Projektmodi erstellen.
- [x] Tooltips/Hilfe für Builder, Word Replace, Datenzuordnung, Versand und Einstellungen ergänzen.
- [x] Tooltips über Einstellungen schalten; kontextbezogene Hilfe und DE/EN-Bedienoberfläche. Der bebilderte Guide ist deutsch.

### B3. Geführter Prozess je Projektmodus

- [x] Schrittfolge für Bewerbungen/E-Mail-Aufträge im Arbeitsbereich mit Fortschritt, fehlenden Angaben und nächster Aktion anzeigen.
- [x] Daten/Vorlagen/Dokumente/Prüfung/Versand zusammenführen; geführten Modus aktivieren/deaktivieren und unterbrochene Abläufe wieder aufnehmen.

### B4. Angemeldet bleiben

- [ ] Vorhandene Windows-Tokenablage und automatische Erneuerung über App-/Windows-Neustarts praktisch prüfen.
- [x] Kontostatus klar anzeigen und wiederkehrende Anmeldung bei gültigem Token vermeiden.
- [x] Abmelden, widerrufene/abgelaufene Berechtigungen und erneute Anmeldung verständlich behandeln.
- [x] Nach Backup-Wiederherstellung weiterhin bewusste Verbindung verlangen.

### B5. Installer und Anleitung für andere Nutzer

- [x] Windows-Installer und gegebenenfalls portable Variante mit Logo/Verknüpfungen bauen.
- [x] Finalen Installer kontrolliert installieren, EXE/GUI starten, PDF erzeugen und deinstallieren; externes Projekt erhalten.
- [ ] Installation, eigene Gmail-Anmeldung und Update auf dem Rechner eines weiteren Nutzers praktisch abnehmen.
- [x] Abhängigkeiten/LibreOffice und Google-Client-/Testnutzer-Einrichtung erklären.
- [x] Gemeinsamen Desktop-Client für private Nutzer bündeln, persönliche Tokens ausschließen; Google-Testmodus und Ablauf dokumentieren.
- [ ] Betreiber trägt die gewünschten Google-Kontoadressen selbst als Testnutzer ein. Öffentliche OAuth-Verifikation gehört nicht zur privaten Freigabe.
- [x] Installationsanleitung, Lizenzhinweise und Datenschutzinformationen mitliefern.

**Fertig:** eine andere Person kann die App mit der Anleitung installieren,
einrichten und ohne Entwicklungsumgebung verwenden.

## Sprintübersicht

| Sprint | Stand und Rest |
| --- | --- |
| 0 | Abschlussentscheidungen/Versionen: A7 |
| 1–3 | Kern und A3-Verwaltung implementiert; Benutzerabnahme am Ende |
| 4 | Echte Konvertierung/Layout geprüft; eigene Dokumente am Ende selbst abnehmen: A1 |
| 5 | Import/Export und Exporthistorie fertig; Endabnahme: A3/A7 |
| 6 | Vier reale Testmails samt PDF/Termin geprüft; native Bedienung/Mailclient: A4 |
| 7 | Builder, Verwaltung und Sprache implementiert; native Benutzerabnahme am Ende: A2/A3/A5 |
| 8 | Backup/Diagnose implementiert; Recovery und Abschluss: A6/A7 |
| Anschlussphase | B1–B5 implementiert; Release 1.0.0, praktische Nutzerabnahme offen |

Nachweise: [Featurematrix](12_Feature_Status.md), [Workspace-Details](14_Workspace_TODO.md),
[Sammelabnahme](25_Bundled_Acceptance.md), [Endspurt](31_Endspurt.md),
[Aktueller Prüfbericht](40_Technical_Completion.md), [Historischer A5-Bericht](38_Localization_Test_Report.txt), [A1–A3-Prüfbericht](36_Completion_Test_Report.txt), [A1–A3-Anleitung](35_Completion_A1_A3.md), [Gmail-Ergebnis](abnahme/gmail_live_result.json).
