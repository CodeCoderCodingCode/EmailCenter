# Builder: Vorschau, Entwurfsgruppe und Versand verstehen

Stand: 13.10.2026 · Schema 14 · Nachbesserung aus der Benutzerabnahme.

Dieses Dokument beschreibt A10. Der Benutzer bestätigt anschließend den
funktionierenden Kernworkflow; die letzte Ergänzung und aktuelle Prüfung der
[persönlichen PDF-Dateinamen stehen in A11](44_Builder_PDF_Names.md).

## Der gezeigte Aufbau

Die Screenshots 281/282 zeigen einen grundsätzlich passenden Ablauf:

1. Excel-/Datenliste → `values` an Betreff, Mailtext und Word Replace.
2. Excel-/Datenliste → `email` an `recipient` der E-Mail-Ausgabe.
3. DOCX → Word Replace → DOCX → PDF → `attachments` der E-Mail-Ausgabe.
4. Zusätzliche feste PDFs → jeweils direkt an `attachments`.

Statische DOCX/PDF-Dateien benötigen keinen `values`-Anschluss. Dieser ist für
persönliche Dateipfade mit Platzhaltern gedacht. Mehrere feste Anhänge pro Mail
sind zulässig, innerhalb der Gesamtgrenze von 20 MiB je Nachricht.
Die sichtbaren Verbindungen ersetzen keine Prüfung der tatsächlichen Dateien,
Excel-Zuordnungen und Inhalte. Diese übernimmt **Alle Zeilen vorschauen**.

## Welche Meldung was bedeutet

Im ersten Screenshot sind sieben Word-Replace-Regeln und die Sammelmeldung
„Suchtexte müssen eindeutig, nicht leer und höchstens 200 Zeichen lang sein.“
sichtbar. Ohne die Regeln lässt sich die konkrete betroffene Zeile nicht bestimmen.

Im zweiten Screenshot sind drei Regeln mit den Suchtexten `Anrede`,
`Ansprechpartner Name` und `Bewerber Name` sichtbar. Diese sind nicht leer oder
doppelt. Die ursprüngliche siebenzeilige Konfiguration ist damit nicht belegt.
„Erst die Datenzeile und Verbindungen prüfen.“ war eine ungenaue Meldung, wenn
die Bausteinvorschau während der Zeilenverarbeitung keinen Wert erhalten konnte.
Sie konnte beispielsweise fehlende Daten oder offene DOCX-Platzhalter verdecken.

**Suchen** ist immer der exakte Text im DOCX. Bei `{{Anrede}}` im Anschreiben muss
die Suche ebenfalls `{{Anrede}}` heißen. Eine Suche nur nach `Anrede` ersetzt
auch den Text innerhalb der Klammern; danach könnte `{{Herr}}` übrig bleiben und
als offener Platzhalter blockieren. Das Programm ergänzt keine Klammern automatisch.
**Datenfeld** bezeichnet die Quelle, z. B. `Anrede` oder `Ansprechpartner Name`.
Bei Datenfeld ist ein leeres **Ersatz** korrekt. Ohne Datenfeld ist Ersatz fester
Text; ein leerer fester Ersatz entfernt den Suchtext.

## Reihenfolge bis zum Versand

1. Excel zuordnen und auswählen. Bei den 20 Testzielen mit fünf Postfächern die
   wiederholten Empfänger im Datenbaustein ausdrücklich erlauben.
2. Im Tab **Plan** den Modus, gegebenenfalls Termin/Zeitzone und Versandvorgaben
   einstellen. Unten Gmail-Konto und gegebenenfalls Signatur auswählen.
3. **Alle Zeilen vorschauen**. Für jede Zeile Empfänger, Betreff, Text und Anhänge
   prüfen. Alle Zeilen müssen bereit sein; bei Fehlern den Ablauf korrigieren und
   erneut vorschauen.
4. **Alle Zeilen, Texte und Anhänge geprüft** bestätigen. Dieser Haken wird erst
   nach erfolgreicher Vorschau verfügbar.
   Geänderte Versandvorgaben verlangen eine erneute Bestätigung; ein geändertes
   Konto, eine Signatur oder ein geänderter Graph auch eine neue Vorschau.
5. **Lokale Entwurfsgruppe erstellen** oder **Entwürfe & Planung erstellen**.
   Bei der Gruppenanlage werden die persönlichen PDFs tatsächlich konvertiert.
6. **Gruppe prüfen / senden** öffnet die zuletzt erstellte Gruppe. Dort die
   vorbereiteten Versandkopien prüfen, freigeben und den Lauf starten. Dieser
   Button wird erst verfügbar, wenn eine Gruppe gespeichert ist.

Die lokale Erstellung sendet keine Nachricht. Der bestehende Gruppenprozess
behält seine Freigabe. Geplante Hintergrundläufe setzen eine geöffnete App voraus.

## Änderungen am Programm

- Word-Replace-Fehler nennen Regelnummer, Fehlerart und bei Duplikaten beide
  Zeilen. Groß-/Kleinschreibung bleibt berücksichtigt.
- Fehlende/duplizierte Regeln werden im Editor markiert und erläutert. Unfertige
  Eingaben bleiben erhalten; es werden keine Regeln still entfernt.
- Bei solchen Vorschaufehlern springt der Builder zum betroffenen Baustein und
  zur Regelzeile. Die Hintergrundverarbeitung startet dafür nicht.
- Bausteinvorschauen zeigen den tatsächlichen Zeilenfehler statt der früheren
  Sammelmeldung.
- Nach Word Replace werden auch Restplatzhalter mit Leerzeichen, Umlauten oder
  leerem Inhalt erkannt. Eine versehentliche Suche nach `NAME` in `{{NAME}}`
  darf beispielsweise `{{Max Mustermann}}` nicht als bereites Ergebnis durchlassen.
  Reproduktion vor der Ergänzung: ein solcher einzelner Datensatz wurde als bereit
  bewertet; nach der Ergänzung wird er blockiert und konkret gemeldet.
- Ein sichtbarer Schritthinweis und Button-Tooltips erklären Vorschau,
  Bestätigung, Gruppenanlage und Versandfreigabe.

## Aufbau zur Fehlersuche teilen

- **Screenshot:** gut für Verbindungen, Auswahl, Meldung und UI. Bei Word Replace
  zusätzlich die Regel-Tabelle zeigen.
- **Graph / Optionen … → Graphvorlage exportieren …:** JSON für präzise Prüfung
  von Verbindungen, Texten und Regeln. Excel-Zeilen und aktive Dateipfade werden
  beim Export entfernt; Mailtexte und Regeln bleiben enthalten.
- Für konkrete Daten-/Dokumentfehler zusätzlich die relevante XLSX/DOCX oder den
  Projektordner und den vollständigen Fehlermeldungstext nennen.

## Prüfung und aktuelle TODO

Die Nachweise dieses Pakets werden unter `docs/abnahme/A10_Builder_Feedback/`
gespeichert. Die A9-Prüfungen dokumentieren den vorherigen Code und bleiben
historische Nachweise für den Importfix.

- Zehn neue Prüfungen für leere/duplizierte Regeln, Baustein-/Zeilennummer,
  verdeckte Datenfehler, Restklammern bei `Ada`, `Max Mustermann` und `Éva Müller`,
  Markierung/Fokus, Groß-/Kleinschreibung, Schritthinweise, Gruppenanlage und
  erreichbare Buttons im kleinen Fenster bestanden. Zusammen mit dem DE/EN-
  Katalog bestehen 26 gezielte Prüfungen des endgültigen Codes.
- Dieselbe unveränderte XLSX mit 20 Zeilen, vorhandener Word-Replace-Kette und
  erneuter Übernahme im UI geprüft: alle persönlichen Vorschauen bereit;
  [UI-Ergebnis](abnahme/A10_Builder_Feedback/UI2/UI_Result.json).
- Zusätzlicher UI-Ablauf: doppelte Regeln markieren und fokussieren, danach
  erfolgreicher Vorschau-/Bestätigungs-/Gruppenanlageprozess und Öffnen der
  bestehenden Gruppenprüfung. Keine Versandplanung angelegt oder Nachricht
  gesendet; [Feedback-UI-Nachweis](abnahme/A10_Builder_Feedback/Feedback_UI/Feedback_UI_Result.json).
- Erneuter echter 20-Zeilen-Ablauf des endgültigen Codes bestanden: 20 dauerhaft
  gespeicherte persönliche DOCX, 20 zweiseitige PDFs, drei Anhänge je Nachricht,
  geplanter Testversand mit Pause, Neuöffnung und Fortsetzen; Originale unverändert.
  [Workflow-Nachweis](abnahme/A10_Builder_Feedback/Workflow2/Workflow_Result.json).
- Abschließende Gesamtsuite: **668 Tests, 667 bestanden, ein optionaler nativer
  Vault-Test übersprungen**, keine Fehler; Laufzeit 470,735 Sekunden. Code während
  des Laufs unverändert; [Ergebnis](abnahme/A10_Builder_Feedback/Full_Test_Result.json)
  und [vollständiges Protokoll](43_Builder_Feedback_Full_Test_Output_Final.txt).
  Der erste A10-Gesamtlauf wurde für die
  Ergänzung der Restklammer-Prüfung angehalten und ist kein Abschlussnachweis.
- Gesamtsuite, 20-Zeilen-Workflow, Excel-UI und Feedback-UI verwenden identische
  Prüfsummen aller 140 Quell-/Test-/Migrations-/Anforderungsdateien. Das Codearchiv
  wird per CRC/SHA und gegen genau diese Quellen geprüft;
  [Abschlusspaket](abnahme/A10_Builder_Feedback/Completion_Result.json).
  Keine echten Gmail-Aufrufe oder zusätzlichen echten Nachrichten.

- [x] Regelnummern, Editor-Markierung, konkrete Bausteinvorschaufehler.
- [x] Sichtbare Anleitung für gesperrte Buttons und Bestätigung erst nach Vorschau.
- [x] Abschließende Regressionen, echte DOCX/PDF und UI-Nachweise ergänzen; geprüfte Quellen sichern.
- [ ] Eigenen vollständigen Bewerbungsablauf und restliche Endabnahmen durchführen.
- [ ] Danach B1–B5 wie beauftragt.

[Gesamtliste](34_Final_TODO.md) · [Excel-Gesamtablauf](41_Builder_Excel_Workflow.md).
