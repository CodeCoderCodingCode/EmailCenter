"""Publish an audited local handoff after source, workflow and installer checks."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile
from run_completion_checks import code_hashes

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/abnahme/B_Release'
OUT=ROOT/'dist/release'
parser=argparse.ArgumentParser()
parser.add_argument('--version', default='1.0.0')
parser.add_argument('--installer-proof', default='Shipment_Installer_Result.json')
parser.add_argument('--installed-check', default='Shipment_Installed_Check.json')
parser.add_argument('--report', default='docs/46_Release_1_0.md')
parser.add_argument('--result', default='Shipment_Result.json')
args=parser.parse_args()
def read(name):return json.loads((EVIDENCE/name).read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

current=code_hashes()
full=read('Shipment_Full_Test_Result.json')
workflow=read('Shipment_Workflow/Workflow_Result.json')
ui=read('Shipment_UI/UI_Result.json')
installer=read(args.installer_proof)
compiled=read(args.installed_check)
assert full['ok'] and full['tested_source_hashes']==current
for proof in (workflow,ui):
    assert proof['status']=='Completed' and proof['real_gmail_requests']==0
    assert not proof['code_changed_during_run'] and proof['tested_source_hashes']==current
assert ui['rows']==20
assert compiled['success'] and compiled['network_calls']==0
assert installer['install_exit_code']==installer['uninstall_exit_code']==installer['compiled_check_exit_code']==0
assert all(installer[key] for key in ('program_started','guide_identical','program_removed','registry_removed','external_project_preserved'))
if 'root_starter_checked' in installer:
    assert all(installer[key] for key in ('root_starter_checked','python_dll_present','installed_executable_matches','intermediate_executable_removed'))
setup=OUT/f'EmailCenter-Setup-{args.version}-Windows-x64.exe'
assert sha(setup)==installer['installer_sha256'].lower()
guide=ROOT/'guide/EmailCenter_Guide.html'
shutil.copy2(guide,OUT/guide.name)

paths={ROOT/name for name in current}
for folder in ('packaging','docs/third_party'):
    paths.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
paths.update((ROOT/'assets/templates').glob('*.docx'))
paths.update(ROOT/name for name in ('assets/Logo256.png','start_emailcenter.py','Start_EmailCenter.cmd','Install_EmailCenter.cmd','README_START_HERE.txt','guide/EmailCenter_Guide.html','docs/Runtime_Inventory.json','docs/localization/Catalog_Audit.json'))
for name in ('build_windows_release.py','windows_release_layout.py','test_windows_release_layout.py','check_windows_installer.ps1','collect_runtime_inventory.py','run_completion_checks.py','create_builtin_documents.py','create_release_guide.py','finalize_windows_release.py'):
    paths.add(ROOT/'tools'/name)
archive=OUT/f'EmailCenter-{args.version}-Source.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as output:
    for path in sorted(paths):
        if path.is_file():output.write(path,path.relative_to(ROOT).as_posix())
    # Same distributable Desktop client as the installer; no authorized users.
    public_client=ROOT/'dist/runtime/EmailCenter/_internal/assets/oauth/desktop_client.json'
    value=json.loads(public_client.read_text())
    assert set(value)=={'installed'}
    output.write(public_client,'assets/oauth/desktop_client.json')
    output.writestr('requirements-build.txt','pyinstaller==6.16.0\n')
    output.writestr('BUILD.txt','Windows x64. Create .venv; install requirements.txt and requirements-build.txt. Place the Inno Setup compiler at .tools/inno/ISCC.exe and portable LibreOffice at .tools/libreoffice. Run .venv/Scripts/python.exe tools/build_windows_release.py. The compiled DLLs remain replaceable under _internal. The Desktop client configuration is intentionally distributable; personal tokens and projects are excluded.\n')
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    for name,digest in current.items():assert hashlib.sha256(check.read(name)).hexdigest()==digest

metadata={'version':args.version,'installer':setup.name,'size':setup.stat().st_size,'sha256':sha(setup),
          'guide':guide.name,'guide_sha256':sha(guide),'source_archive':archive.name,'source_archive_sha256':sha(archive),
          'tests':full['tests'],'passed':full['tests']-full['skipped'],'skipped':full['skipped'],
          'workflow_rows':20,'real_gmail_requests':0,'installer_install_start_pdf_uninstall_checked':True,
          'shared_desktop_client':True,'user_tokens_included':False,'native_other_user_acceptance':False,
          'source_hashes':current}
if 'root_starter_checked' in installer:
    metadata['dll_fix_installer_proof']=args.installer_proof
    metadata['application_source_unchanged_from_1_0_0']=True
    metadata['root_starter_checked']=True
(OUT/'Release.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
(EVIDENCE/args.result).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
report=f'''# EmailCenter {args.version} – bereit zur Endabnahme

Stand: 14.10.2026. Der Kern wurde zuvor vom Benutzer bestätigt; der beauftragte
Anschlussausbau ist implementiert und lokal geprüft.

## Lieferung

- [Windows-Installer](../dist/release/{setup.name}) – {setup.stat().st_size/1024/1024:.1f} MiB, x64, Installation je Windows-Nutzer, optionale Startmenü-/Desktop-Verknüpfungen.
- [Bebilderter Offline-Guide](../guide/EmailCenter_Guide.html) – alle Bereiche, alle Bausteine, neun Settings-Tabs, Sprungmarken und Bewerbungsablauf 1–10.
- [Quellen und Build-Dateien](../dist/release/{archive.name}) – SHA-/CRC-geprüft; ohne Nutzerprojekte und Anmeldetokens.
- [Betreiber: Google-Testnutzer](45_Release_Operator.md).

## Erledigt

- Datum: aktuell/fest/Excel, fünf Formate, Zeitzone und Tagesversatz.
- Uhrzeit: aktuell/fest/Excel und drei Formate. Eine Vorschauzeit bleibt für alle Zeilen und Erstellung fest.
- Variable / Festwert: eigene Felder, Platzhalterwerte, bewusste Überschreibung; values weiterreichen und mit {{{{Name}}}} verwenden.
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
| Vollständige Suite | {full['tests']} Prüfungen: {full['tests']-full['skipped']} bestanden, {full['skipped']} optionaler nativer Tresor-Test übersprungen |
| Quellstand | Gesamtsuite, echter Workflow und UI stimmen mit aktuellen SHA-Prüfsummen überein |
| Excel / Builder | 20 Zeilen auswählbar, Originalspalten und Regeln, persönliche Vorschau, Wiederimport |
| Dokumente / Planung | 20 echte PDFs mit je zwei Seiten, 20 gespeicherte DOCX, drei Anhänge je Nachricht; persönliche Dateinamen auch auf Disk |
| Testversand | 20 passende MIME-Nachrichten über Fake-Provider; Termin, Abstand, Pause, Wiederöffnen, Fortsetzung; keine doppelten Sendungen |
| Finaler Installer | regulär in Testordner installiert, installierte EXE gestartet, echte PDF und lokale Entwürfe erstellt, deinstalliert; Registrierung entfernt und externes Projekt erhalten |
| Guide / Vorlagen | drei DOCX visuell geprüft; alle Kontextanker und Settings-Anker geprüft; installierter Guide bytegleich |
| Reale Gmail-Aufrufe in diesem Ausbau | 0 |

Maschinenlesbar: [Release-Ergebnis](abnahme/B_Release/{args.result}),
[Tests](abnahme/B_Release/Shipment_Full_Test_Result.json),
[Workflow](abnahme/B_Release/Shipment_Workflow/Workflow_Result.json),
[UI](abnahme/B_Release/Shipment_UI/UI_Result.json),
[Installer](abnahme/B_Release/{args.installer_proof}).

## Deine verbleibende Endabnahme

- Gewünschte Google-Kontoadressen selbst als Testnutzer freischalten; Einträge wurden hier nicht in der Cloud geändert.
- Auf dem Rechner eines weiteren Nutzers installieren und dessen eigenes Gmail anmelden.
- Native Windows-Skalierung/Tastatur und eigene Dokumente/Videos abschließend prüfen. Der Prozessstart wurde ohne sichtbare native UI getestet; das ersetzt diese Abnahme nicht.
- Öffentliche OAuth-Verifikation ist kein Bestandteil der privaten Testnutzer-Freigabe. Im Google-Testmodus kann nach sieben Tagen erneute Anmeldung nötig sein; gültige Tokens werden gespeichert/erneuert.
- Hintergrundversand braucht eine geöffnete App und aktiven Rechner. Installer ist ohne eigenes Codesignatur-Zertifikat gebaut.

**Technisch abnahmebereit; persönliche Endfreigabe bleibt beim Benutzer.**
'''
if 'root_starter_checked' in installer:
    report += '''
## DLL-/Startpfad-Korrektur

Die gemeldete EXE lag unter `build/pyinstaller/EmailCenter`. Dieser Ordner
enthielt nur die PyInstaller-Zwischendatei ohne `_internal/python313.dll`;
die komplette Laufzeit liegt unter `dist/runtime/EmailCenter`.

- Neuer Installer und EXE-Version 1.0.1; optionalen Verknüpfungen und Programmstart
  einen expliziten Arbeitsordner mitgeben.
- `Install_EmailCenter.cmd` startet den richtigen Installer.
- `Start_EmailCenter.cmd` nutzt das vollständige Laufzeitpaket und reicht Argumente weiter.
- Build prüft Python, Qt, Plattform-Plugin, Konverter, Guide und OAuth-Konfiguration.
- Unvollständige Zwischen-EXE wird erst nach erfolgreicher Sammlung und Bytevergleich entfernt.
- Fünf zusätzliche Paketierungsprüfungen bestanden, einschließlich fehlender/leerer DLLs,
  falscher ICU und Schutz vor Entfernen einer abweichenden Zwischen-EXE.
- Korrigierten Installer regulär in isolierten Ordner installiert: Python-DLL vorhanden,
  EXE identisch, tatsächlicher Qt-Prozessstart aus anderem Arbeitsordner und echter
  personalisierter PDF-/Entwurfsablauf erfolgreich. Root-Starter separat mit echtem PDF geprüft.
- Testinstallation anschließend deinstalliert; externes Testprojekt blieb erhalten.

Programmquellen und Tests sind bytegleich zum geprüften 1.0.0-Stand. Die 753er-Suite
und 20-Zeilen-Workflow-Nachweise werden deshalb übernommen; Build-/Installerprüfungen
wurden für 1.0.1 neu ausgeführt. Keine echten E-Mails gesendet.

Details: `docs/abnahme/B_Release/DllFix/Installer_Result.json`,
`Installed_Check.json`, `Starter_Check.json`, `Layout_Tests.log` und `Build.log`.
'''
(ROOT/args.report).write_text(report,encoding='utf-8')
print(json.dumps({k:v for k,v in metadata.items() if k!='source_hashes'},ensure_ascii=False,indent=2))
