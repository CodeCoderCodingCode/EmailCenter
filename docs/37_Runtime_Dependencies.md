## Release 1.0.0 – aktueller Stand (14.10.2026)

Installer inklusive Python/Qt und LibreOffice ist gebaut und kontrolliert installiert, gestartet und deinstalliert. Schema 14; 753 Prüfungen (752 bestanden / 1 optionaler Skip), aktueller Quellstand unverändert. Paketierung verhindert inkompatible DLLs aus der Werkzeugumgebung; Lizenztexte und Inventar liegen im Paket unter _internal/licenses. Details und Prüfgrenzen: [Release-Nachweis](46_Release_1_0.md). Der folgende A7-Stand bleibt historischer Nachweis.

# Geprüfte Laufzeit, Grenzen und Lizenzinventar

Stand: 12.10.2026. Abschluss A7; Verpackung und Verteilung folgen gemäß Auftrag
in B5. Dies ist eine Bestandsaufnahme der lokal verwendeten Abhängigkeiten.

## Tatsächlich geprüft

| Bestandteil | Lokaler Prüfstand |
| --- | --- |
| Betriebssystem | Windows 11, Build 26200, 64 Bit |
| Python | 3.13.3 |
| SQLite | 3.49.1; Schema 13, Fremdschlüssel und Integritätsprüfungen |
| Qt / PySide6 | 6.12.0; PDF-Modul 6.12.0.140 |
| LibreOffice | 26.2.6.3 für echte DOCX/PDF-Konvertierung |
| Excel | openpyxl 3.1.5; echte XLSX und CSV-Import-/Exporttests |

Der optionale Windows-Tresor-Roundtrip wurde zusätzlich separat mit zufälliger
synthetischer Identität geprüft; Lesen/Schreiben/Löschen erfolgreich.
Er griff nicht auf bestehende Gmail-Identitäten zu.

Andere Windows-/Python-/SQLite-/LibreOffice-Versionen wurden in diesem Paket
nicht praktisch geprüft. Anforderungen an Python je Paket stehen im Inventar;
sie ersetzen keine Prüfung der gesamten Anwendung auf diesen Versionen.
Start und Installation der vorhandenen Entwicklungsumgebung beschreibt
`README_START_HERE.txt`; ein Installer wird erst in B5 erstellt.

## Abhängigkeiten und Hinweise

- Die neun direkten Versionen in `requirements.txt` und ihre transitiven
  Abhängigkeiten wurden gegen die installierten Paketmetadaten geprüft.
- 34 Laufzeitpakete passen zu den deklarierten Versionsanforderungen.
- 56 mitgelieferte Lizenz-/Notice-Dateien wurden unverändert mit SHA-256 in
  `docs/third_party` gesammelt. Auch LibreOffice-Lizenztext, HTML-Lizenzsammlung
  und NOTICE sind enthalten.
- PySide6/Qt führen LGPL-/GPL-Alternativen; PDFium und weitere native Komponenten
  enthalten eigene Abhängigkeitshinweise. Für den späteren Installer müssen die
  tatsächlich gebündelten Binärkomponenten, ihre Notices und die Verteilungsform
  nochmals überprüft werden. Diese Inventur bestätigt keine fertige Paketierung.
- Python-/Windows-/SQLite-Komponenten außerhalb der Python-Paketabhängigkeiten
  werden in B5 zusammen mit der gewählten Laufzeitverteilung berücksichtigt.

Maschinenlesbarer Nachweis: [Runtime-Inventar](Runtime_Inventory.json).
Reproduzierbar mit `.venv\Scripts\python.exe tools\collect_runtime_inventory.py`.
Der Helfer liest installierte Metadaten und Notice-Dateien; er verwendet kein Netz.

## Grenzen des aktuellen Programms

- Hintergrundversand und Terminläufe benötigen eine geöffnete App.
- Weitere reale Nachrichten brauchen eine konkrete Freigabe; unklare Ergebnisse
  werden abgeglichen und nicht blind erneut gesendet.
- Gmail-Zugangstokens liegen im Windows-Tresor, nicht in der Projekt-Datenbank.
  Wiederherstellung deaktiviert Konten/Automatik und setzt offene Freigaben zurück.
- Projektbackups sind unverschlüsselte ZIP-Dateien mit persönlichen Projektdaten,
  Nachrichten und Dokumenten. Dies wird in Settings/Wiederherstellung angezeigt.
- DOCX-Layout wird durch LibreOffice gerendert; Word-, Schrift- und Layout-
  Unterschiede müssen mit den eigenen Dokumenten abgenommen werden.
- Video-Wiedergabe hängt von Datei/Codec ab. Ein echtes MJPEG-AVI ist geprüft;
  weitere eigene Formate bleiben in der Sammelabnahme.
- 100 Builder-Bausteine, 400 Verbindungen und 2 MB Graphtext sind die bestehenden
  Eingabegrenzen. Der persönliche Inhalt und die Anhangkopien werden vor der
  Ausgabe geprüft; der Editor sendet selbst keine Nachrichten.
- Endgültiges Löschen schützt Referenzen und geänderte Dateien. Externe Originale,
  unbekannte Dateien und Backups bleiben erhalten; reguläres Löschen ist kein
  garantiertes Überschreiben aller Datenträgerkopien.

Native Windows-DPI-/Tastaturabnahme und die vollständige englische Fachsprache
bleiben A5. Eigene produktive Projekte und die gesamte Schlussabnahme bleiben
A6/A7 in der [finalen TODO](34_Final_TODO.md).
