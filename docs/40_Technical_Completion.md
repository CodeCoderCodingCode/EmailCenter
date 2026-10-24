# Technischer Abschluss bis zur Benutzerabnahme

Stand: 13.10.2026 · Schema 13 · **Technisch abnahmebereit (A1–A7)**.

Dieser Nachweis dokumentiert den damaligen Code. Der anschließende Benutzerauftrag
zum Excel-Bewerbungsablauf und Schema 14 hat einen eigenen aktuellen
[Nachweis samt Anleitung](41_Builder_Excel_Workflow.md). Die damaligen Archiv- und
Prüfsummen gelten nicht für die anschließend geänderten Quellen.

Der Benutzer führt die praktische Abnahme mit eigenen Daten am Ende selbst durch.
Die lokalen Abschlussprüfungen und die Codesicherung werden davor abgeschlossen.
[Verbindliche Restliste](34_Final_TODO.md).

## Behobene Fehler

1. **Builder-Ressourcen:** Eine nie geöffnete Builder-Seite ließ 14 Buttons und
   zwei Menüs nach dem Schließen zurück. Die Controls erhalten jetzt sofort einen
   Qt-Parent. Vier neue UI-Regressionen prüfen Besitz, Zerstörung, Navigation/Resize
   und Sprachwechsel ohne ausgelöste Aktionen.
2. **Wiederherstellung unter Windows:** Tiefe persönliche PDF-Pfade passten in den
   endgültigen Projektordner, überschritten jedoch im längeren temporären Ordner
   MAX_PATH. Validierte Staging-Zugriffe und deren Bereinigung verwenden jetzt
   Windows-Extended-Paths. Zwei echte Windows-Dateisystemtests prüfen Restore und
   Abbruch ohne Änderungen am Original. Dies ist keine Zusage für beliebig lange
   endgültige Projektpfade.
3. **Builder-Menüs:** Menüaktionen bewahren jetzt ihre explizite Beschriftungsquelle
   und folgen einem DE/EN-Wechsel; Graphdaten und Aktionsverbindungen bleiben erhalten.

## Durchgehender lokaler Ablauf

Nachweis: [Workflow-Ergebnis](abnahme/A7_Workflow/Workflow_Final/Workflow_Result.json).

Alle neun Workflow-Prüfschritte bestehen in 75,368 Sekunden; 17 wiederhergestellte
Projektdateien stimmen mit ihren SHA-256-Hashes überein. Quellcode unverändert.

- Echtes XLSX mit zwei erfundenen Kontakten importieren; zusätzliche Quellspalten
  in einer gemeinsamen Datenliste erhalten und wiederverwenden.
- DOCX aus unverändertem Original personalisieren; LibreOffice erstellt zwei
  PDFs mit je zwei Seiten. Textwerte, Seitenzahl und offene Platzhalter prüfen.
- Zwei Bewerbungen mit persönlichen Nachrichten und PDFs anlegen; Testprovider:
  prüfen/freigeben → einmal ausführen → pausieren → Projekt erneut öffnen → erneut
  prüfen/freigeben → verbleibenden Auftrag einmal ausführen. Sent und
  Bewerbungsbelege bleiben konsistent.
- Dieselbe Datenliste im Builder mit echten persönlichen PDFs, benannten Anhängen,
  Inline-Logo und dauerhaftem Graph-/Undo-Arbeitsstand nutzen.
- CSV-/XLSX-Export samt persönlichen Werten, Versandstatus und Historie prüfen.
- Geprüftes Backup in einen neuen Ordner wiederherstellen; alle Projektdateihashes,
  Beziehungen und Arbeitsstand vergleichen. Konten bleiben deaktiviert,
  Versandfreigaben werden zurückgesetzt, Hintergrundläufe nicht aktiviert.
- Diagnose ohne Namen, Adressen, Nachrichten, Pfade oder Tokens; Original-DOCX
  und Original-XLSX bleiben unverändert.

Hier wurden ausschließlich ein Testprovider und synthetische Daten verwendet.
Echte Gmail-Aufrufe sind im lokalen Langlauf ausdrücklich gesperrt.
Die früher freigegebenen TEST 1–4 wurden nicht erneut versendet; Empfang und
PDFs sind bereits vom Benutzer bestätigt: [Gmail-Nachweis](39_Gmail_Attachment_Review.md).

## Abschlussprüfungen

Die endgültige Gesamtsuite besteht: **644 Tests, 643 bestanden, ein optionaler
nativer Windows-Vault-Test übersprungen**, 514,935 Sekunden. Keine Codeänderung
während des Laufs. [Gesamtausgabe](40_Workflow_Release_Test_Output.txt),
[Quellprüfsummen und Ergebnis](abnahme/A7_Workflow/Release_Test_Result.json).

Der endgültige UI-Lauf besteht: **540 Prüfungen in sechs Runden desselben
Qt-Prozesses**, 518,345 Sekunden (8 Minuten 38 Sekunden), keine Fehler/Skips,
keine Codeänderung, kein realer Gmail-Aufruf. Nach jeder Runde bleiben **null
Widgets und null Fenster** zurück. [Ergebnis und Ressourcen](abnahme/A7_Workflow/UI_Soak_Final_Frozen/UI_Soak_Result.json).
Ein zusätzlicher vollständiger UI-Diagnoselauf mit 90 Prüfungen besteht ebenfalls:
[Nachweis](abnahme/A7_Workflow/Soak_Diagnosis/UI_Soak_Result.json).

| Runde | Prüfungen | Private Prozessspeicher (MiB) | Handles | Widgets / Fenster nach Bereinigung |
| --- | --- | --- | --- | --- |


| 1 | 90 | 156.1 | 281 | 0 / 0 |
| 2 | 90 | 188.8 | 273 | 0 / 0 |
| 3 | 90 | 204.8 | 273 | 0 / 0 |
| 4 | 90 | 220.7 | 273 | 0 / 0 |
| 5 | 90 | 223.0 | 273 | 0 / 0 |
| 6 | 90 | 225.2 | 273 | 0 / 0 |

Der Prozessspeicher steigt während der Aufwärmphase; die letzten beiden
Zunahmen betragen jeweils rund 2,2 MiB. Dies belegt die behobene Widget-Retention
und erfolgreiche Abläufe, nicht die Abwesenheit jedes möglichen Speicherlecks.
Die zeitgesteuerten Faulthandler-Stackdumps waren Diagnosesnapshots während
laufender Tests, keine fehlgeschlagenen Tests oder Konvertierungszeitlimits.

- 43 gezielte Prüfungen für Sprachwechsel, Widget-Lebensdauer und lange
  Windows-Staging-Pfade bestehen.
- Vier frische Qt-Prozesse bei 100/125/150/200 %: je 502 Beschriftungsquellen,
  keine fehlende Katalogquelle, persönliche Werte unverändert, DE/EN-Neustart
  und Rückwechsel korrekt. Bilder: [Render-Ergebnisse](abnahme/A7_Workflow/Rendering/Render_200.json).
- Englische Settings bei 200 % und Projektzusammenfassung bei 100 % visuell
  betrachtet; Beschriftungen und Abschlussaktionen erreichbar.

### Einordnung der Zwischenläufe

Frühere Gesamtläufe mit 641 bzw. 643 Tests bestanden als Tests, sind wegen
nachfolgender Codeänderungen ausdrücklich kein Abschlussnachweis. Dasselbe gilt
für die ersten wiederholten UI-Läufe: Die Metadaten melden Codeänderungen und
bewahren die Ergebnisse unverändert. Der ursprüngliche Lauf zeigt wachsende
verwaiste Builder-Widgets; nach der Besitzkorrektur bleiben in zehn Zwischenrunden
jeweils null Widgets zurück. Maßgeblich ist der letzte Lauf mit unveränderten
Quellprüfsummen.

Ein Neuversuch der Workflow-Prüfung ohne die benötigten Sandbox-TEMP-Vorgaben
scheiterte im LibreOffice-Tempordner. Der endgültige Workflow mit den korrekten
Arbeitsverzeichnissen besteht. Ein blockierter UI-Prüfprozess wurde abgebrochen;
der abschließende Lauf verwendet dieselben Prüfschritte mit vollständigen
Startvorgaben. Solche Zwischenversuche werden nicht als bestanden ausgewiesen.

## Prüfgrenzen und persönliche Endabnahme

Qt läuft für die lokalen UI-Prüfungen mit `offscreen`. Echte Windows-DPI,
physische Tastatur/Maus, Browser-Tab-Schließen, eigene Codecs und ein nativer
Langlauf werden vom Benutzer am Ende abgenommen. Der früher sporadisch gemeldete
Qt-MemoryError bleibt dort zu beobachten; der hier nachgewiesene Widget-Leak ist
behoben, ohne daraus eine vollständige Ursachenklärung für jeden MemoryError
abzuleiten. Die persönliche Endfreigabe und Installer-Verteilung sind noch offen.

Der Windows-Tresor ist in der Gesamtsuite ein optionaler Test. Seine früheren
nativen Prüfungen sind separat dokumentiert. Lokale ZIP-Backups sind
unverschlüsselt; Tokenablage erfolgt getrennt im Windows-Tresor.

## Codesicherung

Der unveränderte Abschlussstand ist in einem neuen CRC-/SHA-geprüften
Codearchiv gesichert; alle archivierten Quellprüfsummen stimmen mit der
Gesamtsuite, dem UI-Lauf und dem Workflow überein. Es enthält Code, Tests, Migrationsdateien, Logo und
Dokumentation; keine Benutzerprojekte, OAuth-Dateien, Tokens oder Laufzeitpakete.
Damals: [Schema-13-Codearchiv](abnahme/Code_Completion_20261013T031629143347Z.zip),
[gebündeltes damaliges Abschlussresultat](abnahme/A7_Workflow/Technical_Completion_Result.json).
`Code_Snapshot.json` zeigt inzwischen das nachfolgende aktuelle Paket.

## Anschlussaufträge

B1 fertige eigene Vorlagen · B2 anschauliche Dokumentation und steuerbare Tooltips ·
B3 geführter Prozess pro Projektmodus · B4 Anmeldung über Neustarts und Kontostatus ·
B5 Installer/Anleitung für weitere Nutzer. Die Detailpunkte bleiben vollständig
in der [finalen TODO](34_Final_TODO.md).
