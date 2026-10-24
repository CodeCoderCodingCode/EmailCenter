# Excel → Bewerbungs-Mail → Word Replace → PDF → geplanter Versand

Stand: 13.10.2026 · Schema 14 · aktuelles Abnahmepaket für den Benutzerauftrag.

**Nachbesserung aus deiner Abnahme:** Fehler beim Übernehmen mit bereits angelegten
Word-Replace-Feldern korrigiert; ursprüngliche Excel-Feldnamen werden übersetzt.
[Importfix (A9)](42_Builder_Mapping_Fix.md). Anschließend wurden Regelhinweise,
Restplatzhalterprüfung und Versand-Schritthinweise ergänzt:
[aktueller Ablauf und Nachweise (A10)](43_Builder_Feedback_And_Review.md).
Die unten aufgeführten A8-Berichte und die A9-Berichte dokumentieren frühere
Codepakete. Anschließend ergänzt: [persönliche PDF-Dateinamen und aktueller
Nachweis (A11)](44_Builder_PDF_Names.md); die A10-Nachweise sind ebenfalls historisch.

## Was behoben wurde

- Der Builder hat jetzt **Excel / CSV laden** im Datenbaustein. Dieser Import
  übernimmt Workflow-Zeilen direkt, ohne vorher Unternehmen, Bewerberprofile oder
  Bewerbungen anzulegen. Domain-Importe können dagegen wegen fehlender Verknüpfungen
  oder eines unbekannten Bewerbungsstatus wie `offen` ungültige Zeilen erzeugen;
  diese sind im Builder absichtlich nicht auswählbar.
- Alle Excel-Spalten stehen als Platzhalter bereit. Leerzeichen werden zu `_`,
  Umlaute zu ASCII, `ß` zu `ss`; Namenskollisionen erhalten einen Nummernzusatz.
  Zusätzlich gibt es die zugeordneten Standardfelder wie `contact.email`.
- Mehrere Zeilen dürfen nach ausdrücklicher Auswahl im Datenbaustein dieselbe
  Empfängeradresse verwenden. Die Auswahl wird mit dem Graphen und der Gruppe
  gespeichert und in der Versandfreigabe angezeigt. Normale Gruppen behalten
  ihre Duplikatsperre; eine alte Freigabe gilt nach Änderung der Auswahl nicht mehr.
- Personalisierte Word-Replace-DOCX werden dauerhaft in der Dokumentverwaltung
  gespeichert, auch wenn ausschließlich die daraus konvertierte PDF mitgesendet
  wird. Ungewählte DOCX werden nicht zusätzlich an die Nachricht angehängt.
- Migration 14 erhält vorhandene Gruppen und setzt die Wiederholungsfreigabe für
  alte Gruppen auf aus. Die Migration läuft beim Projektöffnen automatisch.

## Datensatz

Datei: `outputs/01a12c0f-69bf-71e0-a70f-f1d66a02b353/EmailCenter_Bewerbungsziele.xlsx`

Ein Blatt **Bewerbungsziele**, Überschriften in Zeile 1, **20 Fake-Ziele**.
Die ursprünglichen 16 Spalten bleiben erhalten; `Bewerbungs_ID` und
`Anrede_vollstaendig` ergänzen eindeutige Testkennungen und fertige Anreden.
Keine Formeln. Die Spalte **Email** enthält ausschließlich die fünf gewünschten
Zieladressen, jeweils viermal. **Bewerber Email** ist die Absenderinformation
des Bewerbers und wird nicht als Empfängerspalte zugeordnet.

## Dein Ablauf 1–10

### 1–2. Projekt und Builder

App nach dem Update neu starten. Ein neues Projekt im Modus **Bewerbungen**
anlegen und den **E-Mail-Builder** öffnen. Für echten Versand im neuen Projekt
ein Gmail-Konto verbinden bzw. ein dort bereits verbundenes Konto auswählen.

### 3. Anhänge einzeln

Für jedes gemeinsame Bild oder PDF einen eigenen Bild-/PDF-/Datei-Baustein
anlegen, die Datei wählen und dessen Ausgang **Datei** mit **Anhänge** des
E-Mail-Bausteins verbinden. Ein Bild als Anhang benötigt diese Verbindung;
ein Inline-Bild im Nachrichtentext verwendet dagegen den Textausgang.

### 4–5. Excel, Text und Betreff

1. Datenbaustein auswählen → **Excel / CSV laden** → neue XLSX auswählen.
2. Blatt **Bewerbungsziele** prüfen → **Zeilenvorschau anlegen**.
3. Der neue Importlauf öffnet sich automatisch. Zuordnungen prüfen:

   | Standardfeld | Excel-Spalte |
   |---|---|
   | Ansprechpartner | Ansprechpartner |
   | E-Mail | Email |
   | Anrede | Anrede |
   | Firmenname | Unternehmen |
   | Stelle | Stelle |
   | Anschreiben | Anschreiben |

4. **Sichtbare gültige Zeilen wählen** → **Gewählte Zeilen übernehmen**.
   Bei 20 Zeilen sind alle auf der ersten Seite. Das sind neue Workflow-Daten;
   wähle nicht den alten ungültigen Bewerbungsimport.
5. Im Datenbaustein **Mehrere Bewerbungsziele an dieselbe E-Mail-Adresse zulassen**
   aktivieren, weil diese Testdatei mehrere unterschiedliche Bewerbungen an die
   gleichen fünf Testpostfächer schickt. Jede Zeile erzeugt eine eigene Mail.
6. Ausgang **Werte** mit dem Werte-Eingang von Text und Betreff verbinden.
   Text-/Betreff-Ausgänge mit **Nachricht** bzw. **Betreff** der Mail verbinden.
   Ausgang **E-Mail** des Datenbausteins mit dem Empfänger-Eingang verbinden.
   Der Startergraph enthält diese Grundverbindungen bereits.

Beispiel-Betreff:

```text
EmailCenter TEST {{Bewerbungs_ID}} – Bewerbung als {{Stelle}} bei {{Unternehmen}}
```

Beispiel-Nachricht:

```text
{{Anrede_vollstaendig}}

{{Anschreiben}}

Mit freundlichen Grüßen
{{Bewerber_Name}}
```

Weitere verfügbare Beispiele: `{{Ansprechpartner_Name}}`,
`{{Anschriftstrasse}}`, `{{Anschriftstadt}}`, `{{Anschriftplatz}}`,
`{{Bewerber_Email}}`, `{{Notizen}}`, `{{Datum}}` und `{{Quelle}}`.
Die Excel-Überschrift `Bewerber Name` wird `Bewerber_Name`.

### 6–7. DOCX und Word Replace

DOCX-Baustein anlegen und dein **Anschreiben.docx** auswählen. Dessen Datei-Ausgang
mit dem DOCX-Eingang eines **Word Replace** verbinden. **Werte** des
Datenbausteins mit **Werte** von Word Replace verbinden.

Für jedes tatsächlich im DOCX enthaltene Wort bzw. Token eine Regel anlegen:

| Suchen im DOCX | Ersatz | Datenfeld ohne Klammern |
|---|---|---|
| `{{NAME}}` | leer | `contact.display_name` |
| `{{COMPANY}}` | leer | `company.name` |
| `{{EMAIL}}` | leer | `contact.email` |
| `{{STELLE}}` | leer | `Stelle` |
| `{{ANREDE}}` | leer | `Anrede_vollstaendig` |

**Suchen** muss exakt deinem Dokument entsprechen. Hast du darin beispielsweise
`{{Unternehmen}}`, trage genau diesen Text bei Suchen und `Unternehmen` beim
Datenfeld ein. DOCX-Tokens werden über Regeln ersetzt, nicht allein durch das
Anschließen des Datenbausteins. Für feste Ersetzungen Ersatztext statt Datenfeld
verwenden. Fehlende Daten und übrige DOCX-Platzhalter sperren die Gruppenanlage.

Die persönliche DOCX wird beim Erstellen der Gruppe unter
`documents/builder/<Gruppe>/<Entwurf>/` gespeichert und unter **Dokumente**
registriert. Die Originalvorlage bleibt erhalten. Für eine zusätzliche DOCX
als Mailanhang den Word-Replace-Ausgang separat mit **Anhänge** verbinden.

### 8. Word → PDF

Word-Replace-Dateiausgang → DOCX-Eingang von **DOCX → PDF**.
PDF-Dateiausgang → Anhänge der Mail. Optional dazwischen **Anhang benennen**
einfügen: Dateieingang von PDF, Werte-Eingang vom Datenbaustein und Name
`Anschreiben_{{Bewerbungs_ID}}.pdf`; dessen Dateiausgang an die Mail anschließen.

Unter **Einstellungen → Word Replace** muss der vorhandene LibreOffice-Konverter
eingetragen sein. Die PDF wird bei Gruppenanlage tatsächlich konvertiert,
gespeichert und als Dokument registriert. Vorher kannst du im Editor die
DOCX-Text- und Seitenlayoutvorschau prüfen.

### 9–10. Prüfen, planen und senden

**Alle Zeilen vorschauen** und im Empfängerwähler mehrere unterschiedliche Ziele
kontrollieren: Adresse, persönlicher Betreff, Text, DOCX-Vorschau und Anhänge.
Alle 20 Ergebnisse müssen bereit sein; anschließend Vorschau bestätigen.

Für Planung die Ausgabe **Versandtermin planen** wählen, Gmail-Konto auswählen,
zukünftigen Termin, `Europe/Berlin`, Abstand, Tagesbudget und Versandfenster
prüfen. Gleiche Start-/Endzeit des Fensters bedeutet ganztägig.
**Entwürfe & Planung erstellen** speichert die persönlichen Ergebnisse und
die Planung gemeinsam. Danach Versandkopien im Gruppenfenster prüfen,
**Gruppe freigeben** und **Gruppe senden**. Falls die Vorbereitung unterbrochen
wurde, zuerst die übrigen Kopien vorbereiten.

Sofortiger Versand nutzt **Sofortversand vorbereiten** und dieselbe Prüfung/
Freigabe. Bei reinen lokalen Entwürfen später **Gruppe prüfen / senden** öffnen.
Vorschau und Gruppenanlage senden selbst keine Mail. Hintergrundversand benötigt
die geöffnete App; nach Pause oder Neustart die Gruppe erneut prüfen/freigeben.

## Prüfnachweise

- **Gesamtsuite: 655 Tests, 654 bestanden, ein optionaler nativer Tresor-Test
  übersprungen**, 447,513 Sekunden; keine Quelländerungen während des Laufs.
  Darin zehn neue Import-/Builder-/UI-Prüfungen und eine Migration für ein
  bereits befülltes Schema-13-Projekt. [Ergebnis](abnahme/A8_Builder_Excel/Full_Test_Result.json),
  [vollständige Ausgabe](41_Builder_Excel_Full_Test_Output.txt).
- **Echter 20-Zeilen-Workflow: bestanden**, 240,509 Sekunden. Die bereitgestellte
  XLSX ergibt 20 auswählbare Zeilen, 20 persönliche Betreff-/Nachrichtentexte,
  20 echte zweitseitige LibreOffice-PDFs und 20 dauerhaft gespeicherte DOCX.
  Jede Mail enthält Bild, gemeinsames PDF und ihr persönliches PDF. Der
  Testprovider erhält 20 richtige MIME-Nachrichten; vor dem Termin keine,
  Abstand/Pause/Neuöffnung/Fortsetzen und kein erneuter Versand sind geprüft.
  Quelldateien unverändert. [Ergebnis](abnahme/A8_Builder_Excel/Run2/Workflow_Result.json).
- **UI mit genau dieser XLSX: bestanden.** Direkter Dateidialog, richtiges Blatt,
  automatische Empfängerzuordnung, 20 aktive Häkchen, Übernahme aller Zeilen,
  zusätzliche Spaltentokens und 20 bereite persönliche Mailvorschauen.
  [UI-Ergebnis](abnahme/A8_Builder_Excel/UI4/UI_Result.json),
  [auswählbare Zeilen](abnahme/A8_Builder_Excel/UI4/Selectable_Excel_Rows.png).
- Die Quellen waren bei Gesamtsuite, UI und Workflow identisch und während der
  jeweiligen Prüfung unverändert. Der erste Workflow-Zwischenlauf bestand die
  fachlichen Prüfungen, scheiterte aber an der Bereinigung eines noch geöffneten
  temporären Testprojekts. Das Prüfwerkzeug schließt die Datenbank nun vor der
  Bereinigung; der oben verlinkte zweite Lauf endet ohne Fehler.
- Der frühere [A7-Nachweis](40_Technical_Completion.md) beschreibt den damaligen
  Schema-13-Stand. Das aktuelle Schema-14-Paket ist separat gesichert: CRC- und
  SHA-geprüftes [Codearchiv](abnahme/Code_Snapshot.json), mit den geprüften
  Quellen abgeglichen; [gebündeltes aktuelles Ergebnis](abnahme/A8_Builder_Excel/Completion_Result.json).
- Die gespeicherte XLSX ist zusätzlich auf echte Datumszellen, Postleitzahlen als
  Text, 18 Spalten, 20 Zeilen, keine Formeln und fehlerfreies Einlesen geprüft:
  [Dateiprüfung](abnahme/A8_Builder_Excel/Workbook_Result.json).
- Der lokale Workflow nutzt einen Testprovider und sperrt echte Gmail-Aufrufe.
  Deine praktische Abnahme mit eigenem DOCX und tatsächlichem Mailclient bleibt
  der abschließende Schritt. Es wurden für dieses Paket keine echten Mails gesendet.

## Aktueller Sprint – vollständige kurze Liste

| Sprint | Geschafft | Noch zu schaffen |
|---|---|---|
| 0 | Anforderungen/Architektur | Endfreigabe |
| 1 | Datenbank/Migrationen, jetzt Schema 14 | Benutzerabnahme |
| 2 | Projekte/Dateien | Benutzerabnahme |
| 3 | Bewerbungsverwaltung | Benutzerabnahme |
| 4 | Vorlagen/Word Replace/DOCX/PDF | Eigenes Anschreiben abnehmen |
| 5 | Direkter Builder-Excel-Import, alle Spalten, Export | Deinen XLSX-Ablauf abnehmen |
| 6 | Sofort/Bulk/Planung, wiederholte Testadressen nach Auswahl | Deinen geplanten Versand abnehmen |
| 7 | Builder/UI/Vorschau/Settings/Hotkeys | Native Bedienung und DPI abnehmen |
| 8 | Backup/Restore/Recovery/Diagnose | Eigene Wiederherstellung/Endfreigabe |

Danach bleiben B1–B5 beauftragt: eigene fertige Vorlagen, anschauliche
Dokumentation/Tooltips, geführte Projektmodi, Login über Neustarts und
Installer mit Nutzeranleitung. [Verbindliche Gesamtliste](34_Final_TODO.md).
