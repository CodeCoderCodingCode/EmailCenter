"""Create the offline handbook and real Qt screenshots using fictional data."""
import base64
from copy import deepcopy
import html
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from emailcenter.email_builder import NODE_TYPES, node
from emailcenter.builtin_templates import builder_graph

OUT = ROOT/'guide'
IMAGES = OUT/'images'
IMAGES.mkdir(parents=True, exist_ok=True)


def capture():
    from test_ui import DesktopTests
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    from unittest.mock import patch
    DesktopTests.setUpClass()
    case = DesktopTests('test_window_starts_without_project_and_pages_can_be_extended')
    case.setUp()
    try:
        case.window.resize(1480, 950)
        case.open_test_project()
        for key in case.window.page_order:
            case.window.navigate(key)
            case.wait_idle()
            case.window.page_transition.stop()
            QTest.qWait(40)
            case.window.grab().save(str(IMAGES/(key+'.png')))
        page = case.window.pages['builder']
        case.window.navigate('builder'); case.wait_idle()
        graph = builder_graph('pdf')
        fields = {'contact.display_name':'Max Mustermann', 'contact.email':'max@example.test', 'contact.salutation':'Sehr geehrter Herr',
                  'company.name':'Musterfirma', 'company.address':'Musterstraße 12\n12345 Musterstadt', 'job.title':'Fachinformatiker für Anwendungsentwicklung',
                  'applicant.display_name':'Erika Beispiel', 'applicant.email':'erika@example.test', 'applicant.phone':'01234 000000', 'applicant.address':'Beispielweg 2\n12345 Musterstadt',
                  'application.date':'01.02.2027', 'application.cover_letter':'Ich interessiere mich für die Ausbildung und möchte meine Fähigkeiten in Ihrem Team weiterentwickeln. Dies ist ein Beispieltext; Motivation und Kenntnisse bitte selbst ergänzen.'}
        graph['nodes'][0]['config']['sources'] = [{'kind':'manual','fields':fields}]
        page.commit(graph)
        page.request_preview(); case.wait_idle(); QTest.qWait(80)
        case.window.page_transition.stop()
        page.fit()
        case.window.grab().save(str(IMAGES/'workflow.png'))
        base = deepcopy(graph)
        for kind in NODE_TYPES:
            graph = deepcopy(base)
            item = next((n for n in graph['nodes'] if n['kind']==kind), None)
            if item is None:
                item = node(kind, 340, 570)
                graph['nodes'].append(item)
            page.commit(graph, item['id'])
            case.window.page_transition.stop()
            QTest.qWait(20)
            page.inspector_pane.grab().save(str(IMAGES/('node-'+kind+'.png')))
        for index in range(case.window.pages['settings'].tabs.count()):
            case.window.navigate('settings'); case.wait_idle()
            case.window.pages['settings'].tabs.setCurrentIndex(index)
            case.window.page_transition.stop(); QTest.qWait(20)
            case.window.pages['settings'].grab().save(str(IMAGES/('settings-'+str(index)+'.png')))
    finally:
        case.tearDown()


NODE_HELP = {
    'data': ('Wähle Excel / CSV laden oder eine importierte bzw. manuelle Liste. Ordne Ansprechpartner und E-Mail zu, markiere gewünschte Zeilen und übernimm sie. Andere Spalten bleiben als persönliche Werte erhalten.', 'values → Texte, Dateipfade, Bedingungen oder Word Replace; email → recipient am E-Mail-Ausgang. Wiederholte Adressen nur bewusst zulassen.'),
    'subject': ('Schreibe den Betreff, z. B. Bewerbung bei {{Unternehmen}} als {{Stelle}}. Ein Betreff muss nach dem Ersetzen eine einzelne nichtleere Zeile sein.', 'values von Excel oder Variablen; text → subject am E-Mail-Ausgang.'),
    'text': ('Freier Nachrichtentext mit Absätzen und {{Spaltennamen}}. Excel-Spalten mit Leerzeichen und Umlauten können im Builder wörtlich verwendet werden, z. B. {{Ansprechpartner Name}}.', 'values → persönliche Daten; text → body oder Text bereinigen.'),
    'description': ('Ausführlicher E-Mail-Text oder Motivation. Dieser Baustein schreibt keinen DOCX-Anhang; für Dokumente DOCX und Word Replace verwenden.', 'values → persönliche Daten; text → body.'),
    'paragraph': ('Ein Absatz der Nachricht. Mehrere Absätze separat verbinden, wenn Reihenfolge und Bearbeitung übersichtlich bleiben sollen.', 'values → persönliche Daten; text → body oder parts an Texte zusammenführen.'),
    'heading': ('Eine Überschrift. In HTML fett dargestellt; in Textmails als normale Textzeile.', 'values → persönliche Daten; text → body.'),
    'html': ('Eigenes HTML für den Nachrichtentext. HTML am E-Mail-Ausgang wählen. Eingesetzte Datenwerte werden escaped; dein eigenes HTML bleibt Markup.', 'values → Daten; text → body. Im Mail-Tab die fertige Darstellung prüfen.'),
    'greeting': ('Eigener Anredetext, z. B. {{Anrede}} {{Ansprechpartner Name}},. Schreibe genau das, was in der Nachricht stehen soll; eine Anrede wird nicht automatisch grammatisch ergänzt.', 'values → Daten; text → body vor Haupttext.'),
    'closing': ('Gruß und eigener Signaturtext. Eine zusätzliche Kontosignatur unten nur wählen, wenn der Gruß nicht doppelt erscheinen soll.', 'values → Daten; text → body nach Haupttext.'),
    'separator': ('Trennung zwischen Nachrichtenteilen. HTML zeigt eine Linie; Text zeigt den eingetragenen Trenntext.', 'text → body.'),
    'link': ('Beschriftung und HTTP(S)- oder mailto-Ziel eintragen. URLs können Datenplatzhalter verwenden.', 'values → Daten; text → body. In Textmails wird die Adresse sichtbar.'),
    'button': ('Handlungslink als HTML-Schaltfläche; in Textmails erscheint der Link als lesbarer Text. Kein Programmcode wird ausgeführt.', 'values → Daten; text → body; Format HTML für Schaltfläche.'),
    'list': ('Ein Eintrag je Zeile. Nummerierte oder unnummerierte Liste wählen; leere Zeilen werden ausgelassen.', 'values → Daten; text → body.'),
    'recipient': ('Empfänger aus einem Datenfeld oder festem Text, z. B. {{contact.email}}. In Bulk bevorzugt email direkt aus Excel verbinden.', 'values → Daten; email → recipient. Nur einen Empfänger-Ausgang verbinden.'),
    'condition': ('Datenfeld, Vergleich und Prüfung wählen: gleich, ungleich, enthält, leer oder ausgefüllt. yes/no-Texte verbinden oder Ersatztexte eintragen. Nur der gewählte Zweig wird für die fertige Mail benötigt.', 'values erforderlich; yes/no optional; text → body/subject.'),
    'merge': ('Mehrere Texte in Verbindungsreihenfolge zusammenführen. Trenntext festlegen, z. B. Leerzeichen für Betreff oder Leerzeile für Nachricht.', 'parts mehrfach verbinden; text → body/subject. Ein Betreff darf keinen Zeilenumbruch enthalten.'),
    'docx': ('Lokale DOCX auswählen. Vorschau zeigt Text; Seitenlayout erzeugt eine PDF-Vorschau. Ein values-Eingang ermöglicht persönliche Dateipfade.', 'file → docx an Word Replace oder DOCX → PDF. Noch offene Dokumentplatzhalter vor Erstellung auflösen.'),
    'pdf': ('Vorhandene PDF auswählen. Sie wird unverändert als Anhang übernommen. Zum Personalisieren zuerst DOCX bearbeiten und konvertieren.', 'file → attachments; values nur für einen persönlichen Dateipfad.'),
    'image': ('PNG, JPEG, GIF oder WebP als Anhang wählen. Vorschau zeigt das Bild. Für ein Bild mitten im HTML-Text den Baustein Inline-Bild verwenden.', 'file → attachments. Datei wählen und anschließend bewusst verbinden.'),
    'video': ('Lokales Video als Anhang auswählen. Vorschau hängt von unterstützten Windows-Codecs ab; große Videos besser als Link versenden.', 'file → attachments. Alle Anhänge zusammen dürfen pro Nachricht höchstens 20 MiB haben.'),
    'file': ('Beliebige lokale Datei als Anhang. Ein Baustein je Datei macht die Verbindung und Reihenfolge sichtbar.', 'file → attachments. Maximal 20 Anhänge und zusammen 20 MiB.'),
    'inline_image': ('Lokales Bild, Alternativtext und Breite wählen. Als HTML-Nachricht im Text eingebettet; automatische CID-Verknüpfung.', 'text → body; HTML am E-Mail-Ausgang. Nicht zusätzlich als normaler Anhang verbinden, wenn keine Kopie gewünscht ist.'),
    'attachment': ('Den Namen eines verbundenen Anhangs personalisieren, z. B. Lebenslauf{{company.name}}.pdf. Passende Dateiendung behalten.', 'file vom Dokument/Anhang; values für Namen; file → attachments.'),
    'replace': ('Suchen = exakter Text im DOCX, z. B. {{company.name}} oder Mustermann. Datenfeld = Excel-Spalte / vorhandener Feldname. Bei Datenfeld bleibt Ersatz leer; andernfalls Ersatz als Festtext eintragen. Jede Regel muss einen eindeutigen Suchtext haben.', 'docx vom DOCX-Baustein; values von Excel/Variablen; file → DOCX → PDF. Alle Zeilen und persönliche DOCX-Textvorschau prüfen.'),
    'convert': ('Personalisiertes DOCX in echte PDF konvertieren. PDF-Dateiname ist einstellbar, z. B. Anschreiben{{Unternehmen}}.pdf. Leer übernimmt den ursprünglichen DOCX-Namen. Gespeicherte Datei und Anhang verwenden denselben Namen.', 'docx vom Word-Replace-Ausgang; file → attachments. Seitenlayout prüfen; Konvertierung ist im Installer enthalten.'),
    'email': ('Fertige Nachricht für jede Datenzeile. Text oder HTML wählen und Anhang-Reihenfolge kontrollieren. Der Mail-Tab zeigt Empfänger, Betreff, Text und Anhänge zusammen.', 'recipient + subject + mindestens ein body sind erforderlich. attachments mehrfach möglich. Versand erfolgt erst nach Gruppenanlage und Freigabe.'),
    'date': ('Aktuelles Datum, fester Wert oder Datum aus einer Quellspalte. Format, Zeitzone und Versatz in Tagen wählen. Feste Werte: YYYY-MM-DD oder TT.MM.JJJJ. Ausgabe erhält einen Variablennamen, standardmäßig datum.', 'Excel values → Datum values → nächste Variable oder Texte/Word Replace values. Danach {{datum}} aufrufen; text kann direkt angeschlossen werden. Aktuell bedeutet Zeitpunkt der Vorschau, nicht späterer Versand.'),
    'time': ('Aktuelle Uhrzeit, feste Uhrzeit oder Quellspalte. Formate HH:mm, HH:mm:ss oder 12 Stunden. Feste Werte HH:mm[:ss]. Zeitzone wirkt auf aktuelle Uhrzeit. Standardvariable uhrzeit.', 'values weiterreichen und {{uhrzeit}} verwenden. Für Datum und Uhrzeit in einer Mail Bausteine über values hintereinander verbinden.'),
    'variable': ('Eigenen Namen wie ausbildungsbeginn und Festwert angeben. Der Wert darf vorhandene {{Datenfelder}} enthalten. Namen mit Buchstaben, Zahlen und Unterstrichen verwenden; vorhandene Felder nur bewusst überschreiben.', 'values übernimmt bisherige Daten, ergänzt die Variable und reicht alle Werte weiter. {{ausbildungsbeginn}} wird erst hinter diesem Baustein verfügbar.'),
    'clean': ('Leerzeichen am Zeilenrand entfernen, Mehrfach-Leerzeichen zusammenfassen, optional Leerzeilen entfernen und Schreibweise ändern. Absätze bleiben erhalten, solange Leerzeilen entfernen ausgeschaltet ist.', 'text von einem Textbaustein → Text bereinigen text → body/subject. Eingesetzte Werte werden nicht erneut als Platzhalter interpretiert.'),
}

SECTIONS = [
('first-steps','Erste Schritte', '''<ol><li>Installer starten und Zielordner sowie optionale Verknüpfungen wählen.</li><li>EmailCenter öffnen → Neues Projekt → Projektname, Ordner und Modus Bewerbungen oder E-Mail-Aufträge festlegen.</li><li>Im Arbeitsbereich eigene Angaben ergänzen. Hilfe / Guide oder F1 öffnet die Erklärung zur aktuellen Ansicht.</li><li>Für den Versand unter E-Mail → Gmail verbinden das eigene Google-Konto anmelden. Der Betreiber muss diese Google-Adresse zuvor als Testnutzer freischalten.</li><li>Ein kleines Beispiel vorbereiten, alle Zeilen vorschauen und Ergebnisse prüfen. Erst dann Entwürfe und Versandgruppe erstellen.</li></ol><p>Ein Projekt ist ein eigener Ordner mit Datenbank, Dokumenten, Vorlagen und Exporten. Lege ihn an einem beschreibbaren Ort wie Dokumente an. Einstellungen gelten für deinen Windows-Nutzer; Gmail-Tokens werden im Windows-Tresor gespeichert.</p>'''),
('overview','Übersicht / Projekte','<p>Ohne geöffnetes Projekt ist dies die Startseite. Neues Projekt legt einen Ordner an; Öffnen verwendet einen bestehenden EmailCenter-Projektordner. Schließen beendet die Projektarbeit. Vor größeren Änderungen ein Backup anlegen. Projektordner öffnet den Ordner im Explorer.</p>'),
('workspace','Arbeitsbereich','<p>Hier laufen die nächsten Schritte zum Projekt zusammen. Der Modus Bewerbungen zeigt Bewerbungen, Vorlagen, Dokumente und Nachfassen. E-Mail-Aufträge konzentriert sich auf Entwürfe und Versand. Modus und Startansicht sind einstellbar; der Builder bleibt direkt erreichbar. Die Projekterstellung fragt Ziel, Profil, Signatur und Vorgaben ab, damit sie später verfügbar sind.</p>'),
('applications','Bewerbungen','<p>Neue Bewerbung anlegen: Titel, Unternehmen, Stelle und Profil zuordnen. Kontakte verknüpfen, Status bearbeiten und Nachfassen planen. E-Mail schreiben übernimmt den Bewerbungskontext als Vorschlag. Ändere eigene Inhalte vor der Freigabe. Ein Statuswechsel versendet keine Nachricht.</p>'),
('companies','Unternehmen','<p>Unternehmen mit Name, Branche, Adresse und Website pflegen; Kontakte zuordnen. Ein Unternehmen kann mehrere Stellen und Bewerbungen haben. Importierte Daten bleiben nachvollziehbar; Builder-Quellen können unabhängig von diesen Stammdaten verwendet werden.</p>'),
('contacts','Kontakte','<p>Ansprechpartner mit Name, Anrede, E-Mail, Telefon und Position anlegen und Unternehmen/Bewerbungen zuordnen. E-Mail schreiben übernimmt vorhandene Angaben. Adressen vor dem Versand prüfen; ein Firmenname ersetzt keine Empfängeradresse.</p>'),
('applicants','Bewerberprofile','<p>Eigene Bewerberdaten zentral pflegen. Wähle bei Bewerbungen das richtige Profil. Profilwerte können Vorlagen füllen; Excel- oder manuelle Builder-Quellen müssen die benötigten Werte selbst enthalten oder über Variable ergänzen. Ein Profil wird nicht ungefragt in eine unabhängige Excel-Zeile gemischt.</p>'),
('jobs','Stellen','<p>Stellenbezeichnung, Unternehmen und weitere Angaben erfassen. Bewerbung und Stelle verknüpfen, damit job.title in kontextbezogenen Vorlagen verfügbar ist. Im Builder kann stattdessen direkt {{Stelle}} aus Excel verwendet werden.</p>'),
('templates','Vorlagen','<p>Mitgelieferte Vorlagen öffnet die Auswahl für Ausbildung, Beruf, Lebenslauf und drei E-Mail-Texte. Sie werden als eigene Version in das Projekt kopiert. DOCX importieren analysiert Platzhalter und erlaubt Zuordnung zu Datenfeldern. Neue DOCX-Version und Version duplizieren halten Änderungen nachvollziehbar. E-Mail-Vorlagen haben eigene Versionen; Auswahl und Vorschau übernehmen erst den gewünschten Text.</p><p>Mitgelieferte Vorlagen sind Ausgangspunkte: Motivation, Angaben und Nachweise selbst vervollständigen. DOCX-Platzhalter verwenden kanonische Namen wie applicant.display_name. Im eigenen Builder-Text darfst du auch {{Unternehmen}} und {{Ansprechpartner Name}} aus Excel verwenden. Für separate E-Mail-Vorlagen verwende die dort angebotenen Feldnamen.</p>'),
('documents','Dokumente','<p>Erzeugte DOCX/PDF-Dateien prüfen, im Explorer öffnen und bei Bedarf exportieren. Die echte PDF-Konvertierung erhält Dokumentlayout soweit von LibreOffice unterstützt. Schriftarten, lange Texte und Seitenumbrüche in der Layoutvorschau prüfen. Originalvorlagen werden bei Word Replace nicht überschrieben.</p>'),
('followups','Nachfassen','<p>Erinnerungen mit Termin, Zeitzone und verknüpfter Bewerbung anlegen. Fällige und erledigte Aufgaben filtern. Die Anzeigezeitzone in Einstellungen bestimmt den Heute-Filter. Eine Erinnerung sendet keine E-Mail automatisch.</p>'),
('import','Datenimport','<ol><li>Excel-Datei mit einer Kopfzeile und einer Bewerbung pro Zeile wählen. Keine verbundenen Zellen oder Überschrift über der Kopfzeile; Kontakt und E-Mail müssen lesbar sein.</li><li>Blatt, Spalten und Zuordnung prüfen. Ansprechpartner und E-Mail zuordnen; weitere Spalten bleiben als persönliche Quelldaten erhalten.</li><li>Gewünschte Zeilen markieren. Bei Fehlern die betreffende Zeile bearbeiten oder auslassen.</li><li>Für den Builder Excel / CSV laden direkt am Excel-Baustein verwenden oder einen vorhandenen Import auswählen.</li></ol><p>Beispielspalten: Unternehmen, Stelle, Anrede, Ansprechpartner Name, Email, Anschreiben, Bewerber Name, Anschrift. E-Mail-Spalte enthält eine Adresse je Ziel. Für mehrere Bewerbungen an dieselbe Adresse im Excel-Baustein ausdrücklich Mehrere Bewerbungsziele an dieselbe E-Mail-Adresse zulassen aktivieren.</p>'),
('mail','E-Mail und Gmail','<p>Gmail verbinden öffnet Google im Browser. Wähle dein eigenes Konto und bestätige die angeforderten Rechte. Nach erfolgreichem Abschluss ins Programm zurückkehren; das Konto unten auswählen. Weitere Nutzer brauchen weder Python noch eine eigene Google-Clientdatei im ausgelieferten Installer.</p><p>Lokale Entwürfe bleiben lokal, bis Gmail synchronisieren gewählt wird. Sofort senden und geplanter Versand erzeugen überprüfbare Aufträge. Inhalt, Empfänger und Anhänge werden festgehalten; Änderungen benötigen erneute Vorschau/Freigabe. Beim Trennen wird die lokale Anmeldung dieses Kontos entfernt.</p><p>Gültige Anmeldungen werden gespeichert und automatisch erneuert. Im Google-Testmodus endet die Google-Autorisierung nach sieben Tagen; dann erneut verbinden. Diese Google-Vorgabe kann EmailCenter nicht umgehen. <a href="https://support.google.com/cloud/answer/15549945?hl=en">Google: Testnutzer und Ablauf</a>.</p>'),
('word_replace','Word Replace als eigener Bereich','<p>DOCX wählen, Suchtexte und Ersetzungen definieren, Groß-/Kleinschreibung und ganze Wörter einstellen. Ein Suchtext muss genau im Dokument vorkommen. Eine Regel ersetzt durch Festtext oder ein Datenfeld, nicht durch beides. Suchtexte dürfen nicht leer oder doppelt sein; fehlende Werte und offene {{Platzhalter}} können die Ausgabe sperren. Ergebnisse als DOCX oder PDF in neue Dateien speichern. Für Bulk jede persönliche Zeile vorschauen und passende Regeln verwenden.</p>'),
('builder','E-Mail-Builder: Orientierung','<p>Links befindet sich die Bausteinpalette, in der Mitte die Zeichenfläche und rechts die Eigenschaften sowie Mail-, Medien- und Plan-Vorschau. Baustein per Doppelklick hinzufügen oder auf die Fläche ziehen. Einen Ausgang auf den passenden Eingang ziehen oder beide anklicken. Farben kennzeichnen Typen. Nicht verbundene Anhänge werden nicht versendet.</p><p>Mittlere Maustaste halten und ziehen verschiebt die Fläche. Zoom über + / −; Einpassen zeigt den Graph; Anordnen ordnet ihn. Rückgängig / Wiederholen und Version speichern sichern Bearbeitung. Graph / Optionen bietet Vorlagen, Gruppen, Export und Panel-Einstellungen. Palette und Eigenschaften passen sich der Breite an.</p><p><a href="#workflow">Zum vollständigen Bewerbungsablauf</a> · <a href="#blocks">Alle Bausteine</a> · <a href="#troubleshooting">Fehler beheben</a></p>'),
('workflow','Kompletter Bewerbungsablauf in zehn Schritten','''<ol><li>Neues Projekt im Modus Bewerbungen erstellen.</li><li>E-Mail-Builder öffnen. Optional Graph / Optionen → Mitgelieferte Builder-Vorlagen → Persönliches Anschreiben als PDF laden.</li><li>Jede PDF, jedes Bild und jeden weiteren Anhang als eigenen Baustein hinzufügen und file → attachments verbinden.</li><li>Excel laden, Ansprechpartner und E-Mail zuordnen, Zeilen auswählen. values → Text verbinden. Nachricht z. B. Sehr {{Anrede}} {{Ansprechpartner Name}}, … Achtung: Wenn Anrede bereits Sehr geehrter Herr enthält, kein zweites Sehr davorschreiben.</li><li>values → Betreff verbinden und Bewerbung bei {{Unternehmen}} als {{Stelle}} eintragen; text → subject.</li><li>Anschreiben.docx als DOCX-Baustein wählen.</li><li>DOCX file → Word Replace docx; Excel values → Word Replace values. Regel z. B. Suchen {{Unternehmen}}, Datenfeld Unternehmen, Ersatz leer. Persönliche DOCX-Vorschau prüfen.</li><li>Word Replace file → DOCX → PDF docx; PDF file → attachments. PDF-Dateiname Anschreiben{{Unternehmen}}.pdf einstellen und Seitenlayout prüfen.</li><li>Excel email → recipient; Nachricht text → body. Konto und Signatur unten wählen. Alle Zeilen vorschauen und jeden Empfänger, Betreff, Text und Anhang prüfen.</li><li>Alle Zeilen, Texte und Anhänge geprüft bestätigen. Im Plan-Tab lokale Entwürfe, sofortigen oder geplanten Versand wählen, Abstand/Budget/Fenster festlegen. Entwürfe / Planung erstellen → Gruppe prüfen / senden → Gruppe freigeben und starten.</li></ol><p>Vorschau sendet nichts. Erstellung allein erteilt keine Versandfreigabe. Eine Gruppe muss geprüft, freigegeben und gestartet sein. Nach Text-/Datei-/Datenänderungen neu vorschauen. PDF-Konvertierung und Kopieren laufen bei der Erstellung; bei Fehlern bleibt die Gruppe zur Prüfung gesperrt.</p>'''),
('planning','Versandplanung und Hintergrund','<p>Sofort = nach Freigabe/Start ohne späteren Termin; Geplant = gewählter lokaler Termin mit Zeitzone. Abstand gilt zwischen Nachrichten. Tagesbudget und Versandfenster begrenzen je Konto/Projekt; gleiche Fenstergrenzen bedeuten ganzer Tag. Der Hintergrundversand braucht EmailCenter geöffnet und den Rechner aktiv. Nach Unterbrechung oder überfälligem Termin kann eine erneute Freigabe erforderlich sein.</p><p>Bei unklarem Provider-Ergebnis nicht erneut blind senden: Auftrag abgleichen. Pausieren stoppt weitere Verarbeitung; bereits gesendete Nachrichten lassen sich nicht zurückholen. Neue Freigaben erfolgen für gespeicherte Inhalte.</p>'),
('export','Export','<p>Aus Listen gefilterte oder ausgewählte Einträge als CSV/XLSX exportieren; Spalten und Ziel vorab prüfen. Dokumentpakete können ausgewählte Dokumente zusammenfassen. CSV-Trennzeichen und Zeichensatz in Einstellungen wählen. Dateien werden lokal gespeichert; Export ist keine E-Mail.</p>'),
('administration','Verwaltung','<p>Projektbezogene Listen, Signaturen und Vorlagen prüfen. Archive und Löschaktionen mit ihrer angezeigten Wirkung kontrollieren. Gmail-Zugangstokens sind keine Projektdateien und werden nicht aus einem ZIP-Backup wiederhergestellt. Diagnosebericht enthält Status und Laufzeitdaten, keine Nachrichten oder Zugangstokens.</p>'),
('settings','Einstellungen','<p>Speichern übernimmt die Vorgaben dauerhaft für den Windows-Nutzer. Projektvorgaben können E-Mail-Vorgaben überschreiben. Bestehende Entwürfe werden nicht ungefragt geändert. Bei falschen Werten erscheint eine verständliche Meldung; erst gültige Einstellungen speichern.</p>'),
('backup','Backup und Wiederherstellung','<p>Backup erstellt ein verifiziertes ZIP mit Projektdaten und Dateien. Es ist unverschlüsselt, daher geeigneten Zielordner wählen. Wiederherstellen prüft die Sicherung und legt einen neuen Projektordner an. Originalprojekt bleibt erhalten. Aufbewahrung in Einstellungen: 0 behält alle; automatische Entfernung betrifft nur verifizierte unveränderte Sicherungen dieses Projekts im Ziel. Gmail nach Wiederherstellung neu verbinden.</p>'),
('troubleshooting','Häufige Meldungen und Lösungen','''<table><tr><th>Meldung</th><th>Nächster Schritt</th></tr><tr><td>Ansprechpartner/E-Mail und gültige Quellspalten zuordnen</td><td>Im Datenimport die beiden benötigten Spalten auswählen, Zeilen markieren und ungültige Zuordnungen korrigieren.</td></tr><tr><td>Fehlende Datenfelder</td><td>Spaltennamen und Werte der betreffenden Zeile prüfen. values-Verbindungen bis zum Text/Word Replace verfolgen.</td></tr><tr><td>Offene Dokumentplatzhalter</td><td>Für jeden angezeigten {{Platzhalter}} eine passende Word-Replace-Regel oder einen konkreten Wert ergänzen. Suchtext exakt übernehmen.</td></tr><tr><td>Vorschau enthält Fehler</td><td>Fehlerhafte Zeile auswählen, Meldung korrigieren und Alle Zeilen vorschauen erneut starten.</td></tr><tr><td>Gruppe prüfen / senden grau</td><td>Zuerst fehlerfreie Zeilenvorschau bestätigen und Entwürfe / Planung erstellen. Unten zeigt der Builder den fehlenden Schritt.</td></tr><tr><td>Ein verbundenes Gmail-Konto auswählen</td><td>Anmeldung abschließen, zurück in EmailCenter und das Konto unten wählen. Bei abgelaufener Anmeldung erneut verbinden.</td></tr><tr><td>Google access_denied</td><td>Betreiber muss die tatsächlich verwendete Google-Kontoadresse als Testnutzer freischalten. Ein mail.de/web.de-Postfach allein ist kein Gmail-Konto.</td></tr><tr><td>PDF-Konvertierung fehlgeschlagen</td><td>DOCX öffnen/prüfen, Seitenlayout testen, Schreibrechte und Zeitlimit in Word-Replace-Einstellungen prüfen. Installierte Version enthält den Konverter.</td></tr></table><p>Für Unterstützung einen Screenshot mit sichtbarer Fehlermeldung und ausgewähltem Baustein teilen. Für genaue Reproduktion zusätzlich exportierte Graphvorlage und einen anonymisierten Datensatz bzw. eine Beispiel-DOCX. Keine Anmeldetokens weitergeben.</p>'''),
('operator','Für den Betreiber: private Google-Freigabe','''<ol><li>Das zugehörige Google Cloud-Projekt öffnen → Google Auth Platform → Zielgruppe / Audience.</li><li>Externe App im Testmodus verwenden und die Google-Kontoadressen der Nutzer bei Testnutzer ergänzen.</li><li>Gmail API aktiviert lassen. Der gemeinsame Desktop-OAuth-Client ist im Installer enthalten; Zugangstokens jedes Nutzers entstehen erst bei dessen Anmeldung.</li><li>Ein Nutzer installiert, erstellt/öffnet ein Projekt und klickt Gmail verbinden. Er benötigt keine Rechte auf dein Cloud-Projekt.</li></ol><p>Der Betreiber verwaltet die Testnutzerliste selbst; dieses Paket bestätigt keine Änderung in der Cloud. Bei web.de/mail.de gilt die beim Google-Login tatsächlich verwendete Kontoidentität. EmailCenter versendet über Gmail; fremde Postfächer werden dadurch nicht zu Gmail.</p><p>Im Testmodus bis zu 100 eingetragene Testnutzer, Autorisierungen einschließlich Refresh-Token laufen nach sieben Tagen ab. <a href="https://support.google.com/cloud/answer/15549945?hl=en">Google: Audience</a>. Desktop-Clients verwenden Browser und lokale Rückleitung; der Desktop-Client ist kein vertrauliches Nutzerpasswort. <a href="https://developers.google.com/identity/protocols/oauth2/native-app">Google: Desktop OAuth</a>. Für spätere öffentliche Veröffentlichung die Google-Prüfanforderungen separat erfüllen.</p>'''),
('installation','Installation, Updates und Deinstallation','<p>Windows 10/11 x64: EmailCenter-Setup.exe starten. Standardmäßig Installation für den aktuellen Nutzer ohne Administratorrechte. Startmenü- und Desktop-Verknüpfung nach Wunsch wählen. Python und der PDF-Konverter sind enthalten. Für Gmail braucht es Internet und ein freigeschaltetes Google-Konto. Zum Aktualisieren EmailCenter schließen und neue Version installieren. Projektordner und persönliche Einstellungen bleiben getrennt vom Programmordner.</p><p>Über Windows Installierte Apps oder die Deinstallation im Programmordner entfernen. Eigene Projekte und Sicherungen bleiben erhalten. Vor einem Windows-Nutzerwechsel oder Umzug ein Backup erstellen; persönliche Gmail-Anmeldungen müssen auf dem Zielsystem erneut erfolgen.</p>'),
]

SETTINGS = [
 ('Design / Zeitzone','Deutsch/Englisch, Design, Akzentfarbe und Anzeigezeitzone. Seitenübergang nach Design oder Fade/Slide/Zoom/Aus; Animationsdauer 60–1000 ms. Reduzierte Bewegung deaktiviert sämtliche neuen Effekte. Maus-/Fokus-Reaktion separat schaltbar. Builder-Reaktionszeit 0–2000 ms verzögert das automatische Laden der Medienvorschau.'),
 ('Arbeitsbereich / Listen','Geführten Projektablauf und Tooltips ein-/ausschalten. Fortschritt wird aus gespeicherten Projektdaten neu ermittelt und beim Wiederöffnen fortgesetzt; keine automatische Versandfreigabe. Außerdem Standardmodus für neue Projekte, Startseite, Seitengröße, Zeilenfarben, Umbruch und kompakte Tabellen.'),
 ('E-Mail-Vorgaben','Bevorzugte Kontoadresse und Signatur, Text/HTML, Zeitzone, Entwürfe/sofort/geplant, Abstand, Tagesbudget und Fenster. Konto und Signatur müssen im Projekt existieren. Vorgaben erteilen keine Freigabe.'),
 ('Backup / Wiederherstellung','Zielordner und Anzahl aufbewahrter Sicherungen. Diagnosebericht lokal exportieren. Wiederherstellen im Hauptmenü prüft das ZIP und legt ein neues Projekt an.'),
 ('Export','CSV oder Excel, Standardordner, Trennzeichen und Zeichenkodierung. Filter und Spalten vor jedem Export prüfen.'),
 ('Word Replace','Groß-/Kleinschreibung, ganze Wörter, fehlende Werte, DOCX/PDF-Ausgabe, Verzeichnis, Textstil und Dateinamensmuster. Ein leerer LibreOffice-Pfad nutzt den enthaltenen Konverter; eigener Pfad ist optional. Konvertierungszeitlimit 10–600 Sekunden.'),
 ('Hotkeys','Tastenkombinationen anpassen und Konflikte prüfen. Hotkeys mit Textfeld-Fokus sollen normale Eingabe erhalten. Tastaturhilfe zeigt aktuelle Zuordnungen. F1 öffnet diesen Guide am Kontext.'),
 ('E-Mail-Builder','Raster, Einrasten, Zoom, Autosicherung, Intervall, Panelbreiten, Palette/Eigenschaften und kompakte Werkzeuge. Standard-Textbausteine für neue Graphen auswählen; Canvas-Hotkeys anpassen. Autosicherung ersetzt keine bewusst benannte Version.'),
 ('Benachrichtigungen','Anzeigedauer und Informations-/Erfolgstoasts wählen. Fehler können sichtbar bleiben, bis sie geschlossen werden. Statusmeldungen am unteren Fensterrand ergänzen die Vorschauhinweise.'),
]


def image(name, width=1100):
    path = IMAGES/(name+'.png')
    if not path.exists():
        raise RuntimeError('Missing screenshot: '+name)
    data = base64.b64encode(path.read_bytes()).decode('ascii')
    return '<p><img width="'+str(width)+'" style="max-width:100%;height:auto" alt="'+html.escape(name)+' – EmailCenter Beispielansicht" src="data:image/png;base64,'+data+'"></p>'


def write():
    toc = ''.join('<li><a href="#'+key+'">'+title+'</a></li>' for key,title,_ in SECTIONS)
    blocks = ''.join('<li><a href="#node-'+kind+'">'+html.escape(spec['title'])+'</a></li>' for kind,spec in NODE_TYPES.items())
    content = []
    for key,title,text in SECTIONS:
        content.append('<h2 id="'+key+'">'+title+'</h2>'+text)
        if (IMAGES/(key+'.png')).exists(): content.append(image(key))
        content.append('<p><a href="#contents">Zum Inhaltsverzeichnis ↑</a></p>')
    content.append('<h2 id="blocks">Alle Builder-Bausteine</h2><ul>'+blocks+'</ul>')
    for kind,spec in NODE_TYPES.items():
        text, connection = NODE_HELP[kind]
        content.append('<h3 id="node-'+kind+'">'+html.escape(spec['title'])+'</h3><p>'+html.escape(text)+'</p><p><b>Verbindung:</b> '+html.escape(connection)+'</p>'+image('node-'+kind, 560)+'<p><a href="#blocks">Bausteinübersicht ↑</a> · <a href="#workflow">Bewerbungsablauf</a></p>')
    for i,(title,text) in enumerate(SETTINGS):
        content.append('<h3 id="settings-'+str(i)+'">Einstellungen: '+title+'</h3><p>'+html.escape(text)+'</p>'+image('settings-'+str(i))+'<p><a href="#settings">Einstellungen ↑</a></p>')
    logo = base64.b64encode((ROOT/'assets/Logo256.png').read_bytes()).decode('ascii')
    result = '''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EmailCenter – Guide</title><style>
body{font:17px/1.65 'Segoe UI',Arial,sans-serif;color:#172238;background:#f4f6fa;margin:0}main{max-width:1120px;margin:auto;background:white;padding:36px}h1{font-size:38px}h2{font-size:28px;margin-top:60px;border-bottom:1px solid #dce3ed;padding-bottom:12px}h3{font-size:23px;margin-top:42px}a{color:#1756a8}img{border:1px solid #dce3ed;border-radius:8px;max-width:100%;height:auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #dce3ed;padding:12px;text-align:left;vertical-align:top}th{background:#eaf1fa}li{margin:8px 0}h2,h3{scroll-margin-top:20px}@media(max-width:650px){main{padding:18px}body{font-size:16px}}@media print{body{background:white}h2{page-break-before:always}a{color:black}}
</style></head><body><main><img width="80" style="image-rendering:pixelated;border:0" src="data:image/png;base64,'''+logo+'''" alt="EmailCenter Logo"><h1>EmailCenter – Guide</h1><p>Bewerbungen, Dokumente und E-Mails Schritt für Schritt · Version 1.0.0 · 14. Oktober 2026</p><p>Offline nutzbar. Alle Programmabbildungen enthalten erfundene Beispieldaten. Klicke im Inhaltsverzeichnis auf einen Bereich oder im Builder auf Hilfe / Guide, um direkt dessen Erklärung zu lesen.</p><h2 id="contents">Inhaltsverzeichnis</h2><ul>'''+toc+'''<li><a href="#blocks">Alle Builder-Bausteine</a></li></ul>'''+''.join(content)+'''<hr><p>EmailCenter 1.0.0 · Guide und Vorlagen sind im Installer enthalten.</p></main></body></html>'''
    (OUT/'EmailCenter_Guide.html').write_text(result, encoding='utf-8')
    print('Guide created: '+str(OUT/'EmailCenter_Guide.html'))


if __name__ == '__main__':
    capture()
    write()
