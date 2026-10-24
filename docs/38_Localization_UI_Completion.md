# A5 – Sprache und Oberflächenprüfung

Stand: 13.10.2026. Technischer Ausbau von Sprint 7B; praktische Windows-Abnahme
bleibt offen. Verbindlicher Abschlussumfang: [Finale TODO](34_Final_TODO.md).

## Umgesetzt

- Englische App-Beschriftungen, Fach-/Validierungsmeldungen und Dialogtexte für
  Projekte, Verwaltung, Import/Export, Dokumente, Word Replace, Einzel-/Bulk-Mail,
  Builder, Arbeitsbereich, Wiederherstellung und Einstellungen ergänzt.
- Projektassistent inklusive Zusammenfassung, Pflichtfeldbeschriftungen,
  Seitentiteln und Zurück/Weiter/Erstellen/Abbrechen übersetzt.
- Dynamische Versand-/Importzustände, Empfängerlisten, Budgetanzeigen und
  Fortschrittsformate behalten ihre ursprüngliche App-Beschriftung für den
  Wechsel DE → EN → DE. Kalender und zugängliche Kontrollnamen folgen der Sprache.
- Sprachwahl ist gespeichert und wird vor dem Aufbau eines neuen Fensters geladen;
  Neustart sowie Rückwechsel nach englischem Start geprüft.
- OAuth-Abschlussseite zeigt DE/EN, Logo, Schließen und einen verständlichen
  Fallback, wenn der Browser das Tab-Schließen verhindert. Die Google-Antwort
  bestätigt noch keine gespeicherte Kontoverbindung; diese wird in der App geprüft.
- Explizite Beschriftungsmetadaten schützen eigene Namen, Zusatzfeldnamen,
  Excel-Werte, Betreffzeilen, Nachrichtentexte, HTML und Platzhalter vor Übersetzung.
  Auswahl-IDs, ungespeicherte Eingaben, vollständige Emoji-Markierungen und
  Kalenderzeitpunkte bleiben erhalten.
- Toast-Kategorien und App-Meldungen sind übersetzt. Sichtbare Benachrichtigungen
  folgen dem Sprachwechsel; persönliche Inhalte werden als wörtlicher Text angezeigt.
- Erinnerungen erkennen doppelte Uhrzeiten am Fehlertyp. Beide Vorkommen bei der
  Zeitumstellung sind auch auf Englisch auswählbar; UTC-Werte bleiben korrekt.
  Eine zusätzliche Quellenprüfung sichert direkt formulierte deutsche Formularfehler ab.
- Übersetzte Vorschautexte lassen sich kopieren, tief kopieren und intern
  serialisieren; gerenderter Text und Sprachmetadaten bleiben erhalten. Die drei
  dadurch zunächst fehlgeschlagenen Builder-Prüfungen und betroffenen Teilpakete
  bestehen nach der Korrektur.
- Leere Mailvorschauen stellen nach einem Sprachwechsel keine alten Inhalte mehr
  her. HTML-Ausgabe entfernt vorherige Platzhaltermetadaten. Theme-Aktionsnamen
  speichern ihre neue Beschriftung beim Umschalten.

## Prüfungen und Nachweise

- 37 neue Sprachprüfungen; zusammen mit elf bestehenden Endspurt-Prüfungen
  kontrollieren sie Sprachwechsel, Neustart, Dialoge, Inhalts-/ID-Schutz,
  Fortschritt, Vorschau, Datenfelder und Toasts. Aktuell bestehen die 48 kombinierten Prüfungen.
- Wiederholungsprüfung: drei aufeinanderfolgende Durchgänge im selben Qt-Prozess,
  jeweils 48 Prüfungen ohne Fehler (144 insgesamt). Die Kontextprüfung kontrolliert
  englische Hinweise bei unveränderten vorgeschlagenen Mailinhalten, Empfängern und
  Kontakt-IDs. Zwei Prüfungen kontrollieren Toast-Beschriftungen und unveränderte
  persönliche Nachrichten. Quellen-, Zeitumstellungs-, Kopier- und Emoji-Prüfungen
  sind enthalten; der aktuelle kombinierte Lauf umfasst 48 Prüfungen.
- Vier Qt-Skalierungen 100/125/150/200 %, jeweils frischer Prozess. 492 verwendete
  App-Quellen aus Hauptfenster, Einstellungen, Datensatzdialog, Projektassistent
  und sichtbarer Benachrichtigung sind im Katalog vorhanden. Die Zusammenfassung
  und Rückkehr zu Deutsch stimmen.
- 1.938 einfache Texte und 221 Formatvorlagen sind im geprüften Katalog enthalten.
  Das ist ein Quellenkatalog einschließlich technischer/historischer Fragmente;
  nicht jeder Eintrag ist ein einzelnes sichtbares UI-Element.
- Abgleich der Formatargumente, Schutz vor beschädigter Zeichencodierung sowie
  statische und dynamische Kataloggrenzen werden automatisiert geprüft.
- Der finale Gesamtlauf besteht: 638 Tests, 637 erfolgreich, ein optionaler nativer
  Vault-Test übersprungen; geprüfte Quellen unverändert. Ergebnisse stehen im [Prüfbericht](38_Localization_Test_Report.txt)
  und [vollständigen Testprotokoll](38_Localization_Full_Test_Output.txt).
  Der Lauf zeichnet die geprüften Quellprüfsummen auf und meldet Änderungen
  während der Prüfung als nicht erfolgreich.

Ansichten: [kleines Fenster bei 200 %](abnahme/A5_Localization/English_Compact_200.png),
[Datensatzdialog](abnahme/A5_Localization/English_Record_125.png),
[Projektassistent](abnahme/A5_Localization/English_Project_150.png),
[Zusammenfassung](abnahme/A5_Localization/English_Project_Summary_150.png),
[Benachrichtigung](abnahme/A5_Localization/English_Toast_150.png).
JSON-Ergebnisse und sämtliche Größen: `docs/abnahme/A5_Localization/`.

Ein kombinierter Zwischenlauf brach beim Anwenden des Themes mit einer nativen
Qt-Zugriffsverletzung ab. Die neuen Dialogtests verarbeiteten verzögertes Löschen
nicht ausdrücklich; ihre Aufräumfolge wurde korrigiert. Nachfolgende kombinierte
Prüfungen bestehen. Dies erklärt noch nicht den früheren sporadischen
Qt-MemoryError; die native Langlaufabnahme bleibt A7.

Ein weiterer Zwischenlauf lief noch, als die erweiterte Renderprüfung sieben
zusätzliche Projektassistent-Texte fand. Sein bereits importierter Katalog war
dadurch veraltet; die Katalogprüfung schlug erwartbar fehl (630 Prüfungen,
ein Fehler, ein optionaler Skip). Dieser Lauf gilt nicht als finaler Nachweis.
Der abschließende 638-Test-Gesamtlauf bestand mit dem fertigen Katalog und
unveränderten Quellen; seine Prüfsummen stehen in `Full_Test_Result.json`.
Ein 632-Test-Zwischenlauf bestand mit einem optionalen Skip. Die Quellprüfung
erkannte die währenddessen ergänzten Toasts; er wurde deshalb nicht als finaler
Prüfstand übernommen. Ergebnis: `Intermediate_Source_Changed_Result.json`.

## Gebündelte praktische Abnahme

1. App starten, Einstellungen → Sprache → English speichern, schließen und neu
   starten. Ein eigenes Projekt öffnen; Namen, Betreff, Platzhalter und Texte prüfen.
2. Projektassistent, Importzuordnung, Word Replace, Buildervorschau und
   Verwaltungsdialog öffnen. Danach zurück auf Deutsch wechseln. Eigene Eingaben
   und Auswahl erhalten; App-Beschriftungen und Schaltflächen folgen der Sprache.
3. Bei Windows-Skalierung 100/125/150/200 % kleine Fenster prüfen: Scrollbereiche,
   Fokus, Tab-Reihenfolge, Hotkeys, Middle-Mouse-Pan und Themewechsel.
4. Lange lokale Aufgaben starten; Toasts, reduzierte Bewegung, Reaktivität und
   Abbruch bedienen. Anschließend Vorschauen schließen und erneut öffnen.
5. Bei einer regulären Google-Anmeldung Abschlussseite und Schließen-Fallback
   mit Tastatur prüfen. Weitere echte Nachrichten erst mit konkreter Freigabe.

## Grenzen und nächste Arbeit

Qt-Renderings und automatisierte Bedienprüfungen ersetzen keine tatsächliche
Windows-DPI-/Tastaturabnahme. Bereits gespeicherte Detailmeldungen/Historien und fremde
Provider-/Systemmeldungen behalten ihre ursprüngliche Sprache. Vorhandene
technische Datenbank-/XML-/Konvertierungsdetails behalten ebenfalls ihren Text. Vorgeschlagene
Mailtexte und Dokumentvorlagen sind Inhalte und werden beim UI-Sprachwechsel
nicht umgeschrieben; eigene fertige Vorlagen folgen in B1.

Die A5-Sprachprüfungen und Renderings senden keine echten E-Mails. Im separat
freigegebenen [A4-Lauf](39_Gmail_Attachment_Review.md) wurden TEST 3/4 mit
unterschiedlichen persönlichen PDFs tatsächlich gesendet und aus Gmail
zurückgelesen; Inhalt und Anhanghashes stimmen. Weiter offen sind die
praktischen Punkte A4/A5/A6/A7 und die Sammelabnahme A1–A3. B1–B5 folgen danach:
eigene Vorlagen, Dokumentation/Tooltips, geführte Projektmodi, Anmeldung über
Neustarts und Installer/Nutzeranleitung.
