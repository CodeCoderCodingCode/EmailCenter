"""Prepare two local A4 drafts and review artifacts; never connect or send."""
from email import message_from_bytes, policy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from emailcenter.project import create_project, open_project
from emailcenter.mail_service import MailService
from emailcenter.mail_models import build_message


class NoCredentials:
    def get(self, *args):
        raise RuntimeError('This local review must never access credentials.')
    put = delete = get


def no_provider(*args):
    raise RuntimeError('This local review must never connect to a provider.')


def check_project(project, messages):
    mail = MailService(project, token_store=NoCredentials(), provider_factory=no_provider)
    for message in messages:
        draft = mail.draft(message['draft_id'])
        assert draft['subject'] == message['subject'] and draft['body'] == message['body']
        assert draft['recipients'] == {'to': [message['to']], 'cc': [], 'bcc': []}
        assert draft['provider_account_id'] is None and draft['provider_draft_id'] is None
        files = mail._attachment_bytes(draft['configuration']['attachments'])
        assert len(files) == 1 and files[0][0] == message['attachment']['filename']
        assert hashlib.sha256(files[0][2]).hexdigest() == message['attachment']['sha256']
    counts = {table: project.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
              for table in ('email_attempts', 'email_jobs', 'email_provider_accounts')}
    assert not any(counts.values()), counts
    assert project.connection.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0] == 2
    return counts


def main():
    folder = ROOT / 'docs/abnahme/A4_Attachments'
    report_path = folder / 'Local_Review_Result.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        with open_project(folder / 'Projekt') as project:
            check_project(project, report['messages'])
        print('Existing local review verified; no new drafts or provider actions.')
        return
    # Check both previously rendered synthetic PDFs before creating anything.
    layout = json.loads((ROOT / 'docs/abnahme/A1_Layout/Ergebnis.json').read_text(encoding='utf-8'))
    outputs = layout['outputs']
    assert len(outputs) == 2 and layout['visual_pages_checked'] == 4
    for item in outputs:
        source = Path(item['path']).resolve()
        assert source.is_relative_to(ROOT) and source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256']
        assert item['pages'] == 2 and item['personal_values']
    folder.mkdir(parents=True, exist_ok=True)
    messages = []
    people = [('Max Mustermann', 'Musterfirma', 'test2847@example.invalid'),
              ('Erika Musterfrau', 'Beispielfirma', 'test2930@example.invalid')]
    with create_project(folder / 'Projekt', name='A4: lokale Anhang-Testvorschau', workspace_mode='mail',
                        goal='Zwei lokale Entwürfe; Konto, Synchronisierung und Versand erst nach konkreter Freigabe.') as project:
        mail = MailService(project, token_store=NoCredentials(), provider_factory=no_provider)
        for number, ((name, company, target), output) in enumerate(zip(people, outputs), 3):
            subject = f'EmailCenter TEST {number} – {name} / {company} – PDF-Anhang'
            body = (f'Guten Tag {name},\n\ndies ist Testnachricht {number} zur kontrollierten '
                    f'Anhang- und Versandabnahme von EmailCenter für {company}.\n'
                    'Dies ist keine echte Bewerbung und kein Auftrag. Der PDF-Anhang '
                    'enthält ausschließlich erfundene Beispieldaten.\n\n'
                    'Geprüft werden persönliche Werte, Anhangname, Seitenlayout und Versandstatus.\n\n'
                    'Viele Grüße\nEmailCenter-Test')
            filename = f'EmailCenter-TEST-{number}-Anschreiben-{company}.pdf'
            draft = mail.save_draft(subject=subject, body=body, recipients_value={'to': [target]},
                                    attachments=[{'path': output['path'], 'filename': filename}])
            files = mail._attachment_bytes(draft['configuration']['attachments'])
            raw = build_message('test4370@example.invalid', draft['recipients'], subject, body, 'plain',
                                f'<local-a4-test-{number}@example.test>', '2026-10-13T12:00:00Z', files)
            mime = message_from_bytes(raw, policy=policy.default)
            attached = list(mime.iter_attachments())
            assert len(attached) == 1 and attached[0].get_filename() == filename
            assert hashlib.sha256(attached[0].get_payload(decode=True)).hexdigest() == output['sha256']
            (folder / f'TEST-{number}.eml').write_bytes(raw)
            messages.append({'draft_id': draft['id'], 'to': target, 'subject': subject, 'body': body,
                             'attachment': {'filename': filename, 'sha256': output['sha256'], 'pages': 2,
                                            'stored_path': draft['configuration']['attachments'][0]['path']}})
        counts = check_project(project, messages)
    # Also prove draft and attachment persistence after reopening the project.
    with open_project(folder / 'Projekt') as project:
        assert check_project(project, messages) == counts
    report = {'status': 'local_drafts_only_approval_required', 'local_drafts': 2,
              'gmail_syncs': 0, 'counts': counts, 'reopened_and_mime_hashes_verified': True,
              'messages': messages, 'proposed_timezone': 'Europe/Berlin',
              'proposed_sequence': 'TEST 3: sync then immediate; TEST 4: schedule at least 5 minutes ahead; explicit approval required'}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    text = ['# A4 – nächste Gmail-Abnahme und praktische Sammelprüfung', '',
            'Stand: 13.10.2026. TEST 1 und TEST 2 wurden bereits gesendet; der Benutzer bestätigt den Empfang beider Nachrichten.', '',
            '## Vorbereitet, noch nicht freigegeben', '',
            'Zwei lokale Entwürfe im separaten Projekt `docs/abnahme/A4_Attachments/Projekt`. '
            'Keine Kontoverbindung, Gmail-Synchronisierung oder Versandaufträge. '
            'Die beiden zweitseitigen PDFs enthalten die bereits geprüften erfundenen A1-Beispieldaten. '
            'Lokale MIME-Ausgabe, Anhanghashes und Projekt-Neuöffnung sind geprüft.', '',
            'Die folgenden beiden Nachrichten benötigen eine neue konkrete Freigabe. '
            'Die frühere Freigabe galt ausschließlich für TEST 1 und TEST 2.', '']
    for number, message in enumerate(messages, 3):
        text += [f'## TEST {number}', '', f"**An:** {message['to']}  ", f"**Betreff:** {message['subject']}  ",
                 f"**Anhang:** `{message['attachment']['filename']}` (2 Seiten)  ",
                 f"**SHA-256:** `{message['attachment']['sha256']}`", '', '```text', message['body'], '```', '',
                 f'Lokale Nachrichtenvorschau: [TEST-{number}.eml](abnahme/A4_Attachments/TEST-{number}.eml).', '']
    text += ['## Gemeinsamer Ablauf nach Freigabe', '',
             '1. TEST 3 mit dem bestehenden Gmail-Konto verbinden und als Gmail-Entwurf synchronisieren; Inhalt und PDF im Gmail-Entwurf vergleichen.',
             '2. TEST 3 einmal sofort senden; Empfang, Anhangname, zwei Seiten und persönliche Werte bestätigen.',
             '3. TEST 4 mindestens fünf Minuten in der Zukunft planen (Europe/Berlin); den konkreten Termin vor Start im UI prüfen. Vor Fälligkeit: null Versandversuche.',
             '4. Vor Fälligkeit pausieren und App schließen/neu öffnen. Erneute Prüfung/Freigabe kontrollieren; danach genau einmal fortsetzen und Terminlauf in geöffneter App abwarten.',
             '5. Nach Empfang beide Aufträge und Gmail-Kennungen prüfen. Bei unklarer Antwort erst abgleichen. TEST 1/2 bleiben abgeschlossen; kein erneuter Versand.', '',
             '## Weitere Sammelabnahme ohne Versand', '',
             '- A1–A3: eigene Layouts/Medien, Builderkette und Verwaltung nach docs/35_Completion_A1_A3.md prüfen.',
             '- A5: englischer Neustart/Rückwechsel, Windows-DPI, Tastatur/Pan, Themes/Toasts und OAuth-Abschluss nach docs/38_Localization_UI_Completion.md.',
             '- A6: eigenes Projekt sichern, in neuem Ordner wiederherstellen, Original und Anhänge vergleichen; wiederhergestellte Konten/Sendeläufe bleiben deaktiviert.',
             '- A7: gesamten Ablauf und nativen Langlauf protokollieren; auftretende Fehler vor finaler Freigabe beheben.', '',
             'Ergebnisfelder: Datum, Projekt, beobachtetes Ergebnis, Screenshot/Beleg, bestanden/offen. '
             'Praktische Punkte werden erst nach tatsächlicher Durchführung abgehakt.', '',
             'Lokaler Nachweis: [Local_Review_Result.json](abnahme/A4_Attachments/Local_Review_Result.json). '
             'Verbindliche Restliste: [Finale TODO](34_Final_TODO.md).', '']
    (ROOT / 'docs/39_Gmail_Attachment_Review.md').write_text('\n'.join(text), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'messages'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
