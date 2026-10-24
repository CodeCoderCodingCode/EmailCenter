# Builder: Fehler beim Übernehmen der Excel-Daten

Stand: 13.10.2026 · Schema 14 · Nachbesserung zur Benutzerabnahme.

Dieses Dokument beschreibt das abgeschlossene A9-Importpaket. Die anschließenden
Regel-/Bausteinfehlermeldungen, Restplatzhalterprüfungen und Versand-Schritthinweise
stehen im [aktuellen A10-Paket](43_Builder_Feedback_And_Review.md).

## Ursache und Korrektur

Die Meldung **„Ansprechpartner/E-Mail und gültige Quellspalten zuordnen.“**
war eine Sammelmeldung für mehrere verschiedene Zuordnungsfehler.
Der Fehler lässt sich mit bereits angelegten Word-Replace-Regeln reproduzieren:
ein Datenfeld `Bewerber Name` wurde zusätzlich in die Importzuordnung übernommen
und automatisch mit der gleichnamigen Excel-Spalte verbunden. Der Backend-Test
verlangte für den Zielfeldnamen jedoch `Bewerber_Name`. Deshalb wurde die gesamte
Übernahme abgewiesen, obwohl die beiden Pflichtzuordnungen korrekt waren.
Der bisherige UI-Nachweis verwendete einen neuen Startergraph ohne solche Regeln
und erfasste diese Situation nicht.

- Der Zuordnungsdialog übersetzt ursprüngliche Excel-Spaltennamen nun in ihre
  tatsächlich gültigen, eindeutigen Platzhalternamen. Unfertige Editorfeldnamen
  gelangen nicht als ungültige zusätzliche Zuordnung in den Importauftrag.
- Der Platzhalterwähler im Builder bietet nur gültige Namen für Mailtext und
  Betreff an. Alle originalen Excel-Werte bleiben verfügbar.
- Word Replace erkennt ursprüngliche Excel-Namen mit Leerzeichen/Umlauten sowie
  Feldangaben mit `{{...}}`. Die Übersetzung erfolgt anhand genau der ausgewählten
  Quelle; Namenskollisionen wie `Bewerber Name` und `Bewerber_Name` bleiben korrekt
  getrennt. Suchtexte und gespeicherte Regeln werden nicht verändert.
- Gespeicherte Word-Replace-Läufe verwenden dafür ihre festgehaltenen
  Quellspalten; Vorschau, direkte Ausgabe und spätere Laufverarbeitung stimmen
  überein. Vorhandene Datenbanken benötigen dafür keine zusätzliche Migration.
- Fehlende Pflichtfelder, ungültige Datenfeldnamen und fehlende Quellspalten
  erhalten unterschiedliche Meldungen mit dem konkreten problematischen Namen.
  Die Prüfung wird nicht abgeschaltet.

## So weiter testen

1. **EmailCenter vollständig schließen und neu starten**, damit der laufende
   Prozess die geänderten Python-Module lädt.
2. Bestehendes Projekt und Builder öffnen. Der vorhandene Datensatz bleibt nutzbar.
3. Datenbaustein → **Excel / CSV auswählen** → passenden vorhandenen Importlauf
   auswählen. Bei Bedarf stattdessen **Excel / CSV laden** für einen neuen Import.
4. Zuordnungen prüfen: **Ansprechpartner → Ansprechpartner**, **E-Mail → Email**.
   Die Spalte **Bewerber Email** ist keine Empfängerspalte.
5. Zeilen wählen → **Gewählte Zeilen übernehmen** → alle Zeilen vorschauen.

Du musst die XLSX nicht ändern oder erneut herunterladen. Für die 20 Testziele
mit nur fünf Postfächern bleibt die ausdrückliche Auswahl **Mehrere Bewerbungsziele
an dieselbe E-Mail-Adresse zulassen** erforderlich.

Bei Mailtext und Betreff weiterhin `{{Bewerber_Name}}` bzw.
`{{Ansprechpartner_Name}}` verwenden. In der Datenfeldzelle einer Word-Replace-Regel
funktionieren jetzt auch die ursprünglichen Spaltennamen `Bewerber Name` bzw.
`Ansprechpartner Name`. Die genaue Schreibweise muss zur ausgewählten Quelle
passen; unbekannte oder leere Werte werden weiterhin gemeldet.

[Anleitung für den gesamten Ablauf](41_Builder_Excel_Workflow.md).

## Prüfung

- Regression vor dem Fix: Übernahme mit bestehender Word-Replace-Regel schlägt
  mit genau der gemeldeten Sammelmeldung fehl. Nach dem Fix besteht sie.
- 29 gezielte Prüfungen des endgültigen Stands bestanden: Builder-Excel und
  Übersetzungskatalog. Die neue Regression prüft auch echte gespeicherte DOCX im
  Builder, im eigenen Word-Replace-Bereich und in gespeicherten Läufen, Umlaute,
  geklammerte Feldangaben und kollidierende Spaltennamen.
- Der erste Gesamtlauf fand einen Katalogfehler bei den drei neuen formatierten
  Fehlermeldungen. Sie sind nun im DE/EN-Vorlagenkatalog eingetragen; die
  Katalogprüfungen und der wiederholte Gesamtlauf bestehen nach dieser Korrektur.
- Dieselbe bereitgestellte 20-Zeilen-XLSX im UI mit vorher angelegter DOCX-/Word-
  Replace-Kette, ursprünglichen Spaltennamen und anschließendem erneuten Import
  geprüft: alle 20 Zeilen übernommen und alle Mail-/Dokumentvorschauen bereit;
  [UI-Ergebnis des endgültigen Stands](abnahme/A9_Builder_Mapping/UI3/UI_Result.json).
- Echter 20-Zeilen-Ablauf des endgültigen Stands bestanden: ursprüngliche
  Excel-Feldnamen in Word Replace, 20 gespeicherte DOCX, 20 persönliche zweiseitige
  PDFs, drei Anhänge je Nachricht sowie geplanter Testversand mit Pause,
  Neuöffnung und Fortsetzen. Originaldateien unverändert;
  [Workflow-Ergebnis des endgültigen Stands](abnahme/A9_Builder_Mapping/Workflow3/Workflow_Result.json).
- Abschließende Gesamtsuite: **658 Tests, 657 bestanden, ein optionaler nativer
  Vault-Test übersprungen**, keine Fehler; 434,514 Sekunden. Geprüfte Quellen
  während des Laufs unverändert;
  [Gesamtergebnis](abnahme/A9_Builder_Mapping/Full_Test_Result.json) und
  [vollständiges Protokoll](42_Builder_Mapping_Full_Test_Output_Final2.txt).
- Gesamtsuite, UI und echter Workflow verwenden identische Prüfsummen des
  endgültigen Codes. Das neue Schema-14-Archiv wird mit CRC und SHA geprüft und
  gegen diese Quellen abgeglichen;
  [Abschlusspaket](abnahme/A9_Builder_Mapping/Completion_Result.json).
  Die A8-Berichte dokumentieren den vorherigen Code, nicht diese Nachbesserung.
- Kein echter Gmail-Aufruf und keine zusätzliche echte Nachricht.

## Aktuelle TODO

- [x] Importfehler mit vorhandener Word-Replace-Regel reproduzieren und beheben.
- [x] Übersetzung von Excel-Namen, Formularzuordnung und konkrete Fehlermeldungen.
- [x] Übernahme aller 20 Zeilen einschließlich wiederholter Übernahme im UI prüfen.
- [x] 20 persönliche DOCX/PDF und geplanten Testprovider-Ablauf prüfen.
- [x] Gesamtsuite mit 658 Tests abschließen und geprüfte Quellen sichern.
- [ ] Vollständigen eigenen Bewerbungsworkflow weiter abnehmen.
- [ ] Anschließend übrige Sammelabnahme und danach B1–B5 wie beauftragt.

[Vollständige Sprintliste](34_Final_TODO.md).
