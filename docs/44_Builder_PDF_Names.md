# Persönliche PDF-Dateinamen im Builder

Stand: 13.10.2026 · Schema 14 · letzter Ergänzungswunsch zum Kernworkflow.

Der Benutzer bestätigt, dass der Bewerbungsworkflow funktioniert. Ergänzt wird
ein einstellbarer Name für die PDF nach Word Replace und DOCX→PDF.

## Einstellen

1. Aktuelle Version speichern, EmailCenter schließen und neu starten.
2. Im Builder den **DOCX → PDF**-Baustein auswählen.
3. Im Tab **Baustein** das neue Feld **PDF-Dateiname** ausfüllen, zum Beispiel:

   ```text
   Anschreiben{{Unternehmen}}.pdf
   ```

4. Version speichern und **Alle Zeilen vorschauen** erneut ausführen.
5. Persönliche Namen in den Mailanhängen prüfen, bestätigen und eine neue
   Entwurfsgruppe erstellen. Anschließend die Gruppe wie gewohnt freigeben/starten.

Für die Firma `Musterfirma GmbH` heißt die Datei dann
`AnschreibenMusterfirma GmbH.pdf`. Weitere Beispiele:

```text
Anschreiben_{{Unternehmen}}.pdf
Anschreiben_{{Unternehmen}}_{{Bewerbungs_ID}}.pdf
Anschreiben_{{company.name}}.pdf
Anschreiben_{{Ansprechpartner Name}}.pdf
```

Die PDF-Stufe verwendet die Daten der jeweiligen Excel-/Listen-/manuellen Zeile.
Originale Excel-Spaltennamen mit Leerzeichen/Umlauten werden in diesem
Dateinamensfeld ebenso unterstützt wie vorhandene eindeutige Feldnamen.
Die Endung `.pdf` muss enthalten sein. Das leere Feld bedeutet:
ursprünglicher Dokumentname, also aus `Anschreiben.docx` wird `Anschreiben.pdf`.

## Was gespeichert wird

- Das Muster gehört zum Baustein und bleibt in Graphversion, Arbeitsstand,
  Undo/Redo und exportierter Graphvorlage erhalten.
- Vorschau, gespeicherte PDF-Datei, Dokumentverwaltung und Mailanhang verwenden
  denselben persönlichen Namen. Die Versandkopie übernimmt ihn ebenfalls.
- Word Replace erhält den ursprünglichen DOCX-Namen, statt einen generischen
  `Dokument-014.docx`-Namen an die PDF-Stufe weiterzugeben.
- Bestehende Graphversionen mit leerer Konverterkonfiguration sind weiterhin
  gültig; keine zusätzliche Datenbankmigration ist nötig.
- Schon erstellte Gruppen sind feste Versandkopien. Für das neue Muster wird
  deshalb eine neue Gruppe nach erneuter Vorschau erstellt.

Ungültige Dateizeichen innerhalb eingesetzter Werte, etwa `/` oder `:`, werden
durch `_` ersetzt. Ein Pfad im Muster, Windows-Gerätenamen, eine falsche Endung,
fehlende Daten oder zu lange Ergebnisse erhalten konkrete Fehler. Die Grenze
beträgt 250 Zeichen für Muster und fertigen Dateinamen. Gleiche Namen in
verschiedenen Bewerbungen liegen in getrennten Auftragsordnern; doppelte
Anhangnamen innerhalb einer Nachricht werden weiterhin blockiert.

## Prüfung

- Acht neue Prüfungen für Originalnamen, persönliche Namen, Originalspalten mit
  Leerzeichen, Namenskollisionen, Umlaute, Dateizeichen, ungültige Muster,
  Vorschaupflicht, Speicherung/Neuöffnung und das Editorfeld.
- 39 gezielte Prüfungen des endgültigen Stands bestanden, einschließlich DE/EN,
  Builder-Renderer und Textbedingungen. Ein vorheriger breiter Lauf mit 92
  Prüfungen bestand ebenfalls.
- Dieselbe XLSX mit 20 Zeilen und persönlichem Dateinamen direkt an der
  PDF-Konverterstufe im UI geprüft; alle Zeilen bereit und Namen korrekt;
  [UI-Ergebnis](abnahme/A11_Builder_PDF_Names/UI/UI_Result.json).
- Gesamtsuite: **676 Tests, 675 bestanden, ein optionaler nativer Vault-Test
  übersprungen**, keine Fehler; Laufzeit 452,386 Sekunden. Quellen unverändert;
  [Ergebnis](abnahme/A11_Builder_PDF_Names/Full_Test_Result.json) und
  [vollständiges Protokoll](44_Builder_PDF_Names_Full_Test_Output.txt).
- Echter 20-Zeilen-Ablauf mit dem Muster direkt an DOCX→PDF bestanden:
  gespeicherte PDF-Pfade, Dokumentnamen und MIME-Anhangnamen stimmen mit
  `Anschreiben<Firmenname>.pdf` überein. Je 20 persönliche zweiseitige PDFs und
  dauerhaft gespeicherte DOCX, drei Anhänge je Nachricht, geplanter Testversand
  samt Pause/Neuöffnung/Fortsetzen; Originaldateien unverändert;
  [Workflow-Ergebnis](abnahme/A11_Builder_PDF_Names/Workflow/Workflow_Result.json).
- Gesamtsuite, UI und echter Workflow verwenden identische Prüfsummen aller 142
  Quell-/Test-/Migrations-/Anforderungsdateien. Das Codearchiv wird per CRC/SHA und
  gegen diese geprüften Quellen abgeglichen;
  [Abschlusspaket](abnahme/A11_Builder_PDF_Names/Completion_Result.json).
  Die A10-Nachweise dokumentieren den vorherigen Code.
- Kein zusätzlicher echter Versand; alle Prüfungen verwenden lokale Entwürfe
  oder einen Testprovider.

## Gesamtstand

- [x] Kernworkflow laut Benutzer funktionsfähig.
- [x] Gewünschtes PDF-Dateinamensfeld mit persönlichen Excel-Werten implementiert.
- [x] Abschlussprüfungen und Archivnachweis dieses Pakets ergänzen.
- [ ] Anschlussphase B1–B5: eigene Vorlagen, Dokumentation/Tooltips,
  geführte Projektmodi, dauerhaft angemeldet bleiben, Installer/Nutzeranleitung.

[Gesamtliste](34_Final_TODO.md) · [Builder-Ablauf](43_Builder_Feedback_And_Review.md).
