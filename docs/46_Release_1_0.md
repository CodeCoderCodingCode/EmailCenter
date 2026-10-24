# EmailCenter 1.0.0 – bereit zur Endabnahme

Stand: 14.10.2026. Der Kern wurde zuvor vom Benutzer bestätigt; der beauftragte
Anschlussausbau ist implementiert und lokal geprüft.

## Lieferung

- [Windows-Installer](../dist/release/EmailCenter-Setup-1.0.0-Windows-x64.exe) – 384.3 MiB, x64, Installation je Windows-Nutzer, optionale Startmenü-/Desktop-Verknüpfungen.
- [Bebilderter Offline-Guide](../guide/EmailCenter_Guide.html) – alle Bereiche, alle Bausteine, neun Settings-Tabs, Sprungmarken und Bewerbungsablauf 1–10.
- [Quellen und Build-Dateien](../dist/release/EmailCenter-1.0.0-Source.zip) – SHA-/CRC-geprüft; ohne Nutzerprojekte und Anmeldetokens.
- [Betreiber: Google-Testnutzer](45_Release_Operator.md).

## Erledigt

- Datum: aktuell/fest/Excel, fünf Formate, Zeitzone und Tagesversatz.
- Uhrzeit: aktuell/fest/Excel und drei Formate. Eine Vorschauzeit bleibt für alle Zeilen und Erstellung fest.
- Variable / Festwert: eigene Felder, Platzhalterwerte, bewusste Überschreibung; values weiterreichen und mit {{Name}} verwenden.
- Text bereinigen: Ränder, Mehrfach-Leerzeichen, optionale Leerzeilen und Schreibweise.
- 14 Designs; wählbare Fade-/Slide-/Zoom-Übergänge, Hover/Fokus, Dauer und Medien-Reaktionszeit; reduzierte Bewegung.
- Drei bearbeitbare DOCX-Vorlagen, drei E-Mail-Vorlagen und vier Builder-Vorlagen. Auswahl importiert eigene Versionen bzw. einen überprüfbaren Graph.
- Hilfe / Guide und F1 springen zum Bereich, ausgewählten Baustein oder Settings-Tab. Tooltips sind schaltbar.
- Geführter Arbeitsbereich mit aus Projektdaten abgeleiteten Schritten und nächster Aktion; in Settings abschaltbar.
- Gemeinsamer Desktop-OAuth-Client: eigener Gmail-Login direkt über Gmail verbinden; keine JSON-Auswahl für ausgelieferte Nutzer.
- PDF-Konverter, Python/Qt-Laufzeit, Logo und Lizenzhinweise im Installer. DLL-Suchpfade und inkompatible ICU aus der Werkzeugumgebung bei Paketierung korrigiert.
- Lange Speicherpfade: interne Ordner verkürzen, Originaldateinamen erhalten. Wenn auch der kompakte Pfad Windows-Grenzen überschreitet, klaren Fehler zeigen und keinen anderen Dateinamen erfinden.

## Tatsächlich geprüft

| Prüfung | Ergebnis |
| --- | --- |
| Vollständige Suite | 753 Prüfungen: 752 bestanden, 1 optionaler nativer Tresor-Test übersprungen |
| Quellstand | Gesamtsuite, echter Workflow und UI stimmen mit aktuellen SHA-Prüfsummen überein |
| Excel / Builder | 20 Zeilen auswählbar, Originalspalten und Regeln, persönliche Vorschau, Wiederimport |
| Dokumente / Planung | 20 echte PDFs mit je zwei Seiten, 20 gespeicherte DOCX, drei Anhänge je Nachricht; persönliche Dateinamen auch auf Disk |
| Testversand | 20 passende MIME-Nachrichten über Fake-Provider; Termin, Abstand, Pause, Wiederöffnen, Fortsetzung; keine doppelten Sendungen |
| Finaler Installer | regulär in Testordner installiert, installierte EXE gestartet, echte PDF und lokale Entwürfe erstellt, deinstalliert; Registrierung entfernt und externes Projekt erhalten |
| Guide / Vorlagen | drei DOCX visuell geprüft; alle Kontextanker und Settings-Anker geprüft; installierter Guide bytegleich |
| Reale Gmail-Aufrufe in diesem Ausbau | 0 |

Maschinenlesbar: [Release-Ergebnis](abnahme/B_Release/Shipment_Result.json),
[Tests](abnahme/B_Release/Shipment_Full_Test_Result.json),
[Workflow](abnahme/B_Release/Shipment_Workflow/Workflow_Result.json),
[UI](abnahme/B_Release/Shipment_UI/UI_Result.json),
[Installer](abnahme/B_Release/Shipment_Installer_Result.json).

## Deine verbleibende Endabnahme

- Gewünschte Google-Kontoadressen selbst als Testnutzer freischalten; Einträge wurden hier nicht in der Cloud geändert.
- Auf dem Rechner eines weiteren Nutzers installieren und dessen eigenes Gmail anmelden.
- Native Windows-Skalierung/Tastatur und eigene Dokumente/Videos abschließend prüfen. Der Prozessstart wurde ohne sichtbare native UI getestet; das ersetzt diese Abnahme nicht.
- Öffentliche OAuth-Verifikation ist kein Bestandteil der privaten Testnutzer-Freigabe. Im Google-Testmodus kann nach sieben Tagen erneute Anmeldung nötig sein; gültige Tokens werden gespeichert/erneuert.
- Hintergrundversand braucht eine geöffnete App und aktiven Rechner. Installer ist ohne eigenes Codesignatur-Zertifikat gebaut.

**Technisch abnahmebereit; persönliche Endfreigabe bleibt beim Benutzer.**
