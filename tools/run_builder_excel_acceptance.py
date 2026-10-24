"""The delivered XLSX through real DOCX/PDF composition and a fake scheduled sender."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT / 'tools')]
import pdfplumber
from emailcenter.project import create_project, open_project
from emailcenter.import_sources import read_source
from emailcenter.import_service import ImportService
from emailcenter.bulk_sources import BulkSourceService
from emailcenter.email_builder import EmailBuilderService, starter_graph, node
from emailcenter.document_service import find_libreoffice
from emailcenter.documents import extract_docx_text
from emailcenter.mail_service import MailService
from emailcenter.bulk_delivery import BulkDeliveryService
from emailcenter.credentials import WindowsTokenStore
from emailcenter.gmail import GmailProvider
from test_mail import MemoryVault, FakeProvider
from run_completion_checks import code_hashes

ALLOWED = {'test1215@example.invalid', 'test1242@example.invalid', 'test1266@example.invalid', 'test1292@example.invalid', 'test1314@example.invalid'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(workbook, target, *, original_column_rules=False, pdf_company_filenames=False):
    workbook, target = workbook.resolve(), target.resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError('Evidence must stay in the workspace.')
    target.mkdir(parents=True, exist_ok=False)
    report = {'status': 'Running', 'checks': {}, 'real_gmail_requests': 0, 'native_ui_acceptance': False}
    before, started = code_hashes(), time.monotonic()
    report_path = target / 'Workflow_Result.json'
    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def checked(name, details=True):
        report['checks'][name] = details
        save()
        print(name + ': OK', flush=True)
    def block_network(*args, **kwargs):
        report['real_gmail_requests'] += 1
        raise AssertionError('Real Gmail disabled during this acceptance run.')
    project = None
    originals = [workbook, ROOT / 'docs/abnahme/A1_Layout/Vorlage.docx', ROOT / 'assets/Logo256.png']
    original_hashes = {str(path): sha(path) for path in originals}
    vault, provider = MemoryVault(), FakeProvider()
    clock = [datetime.now(timezone.utc).replace(microsecond=0)]
    due = clock[0] + timedelta(minutes=5)
    mail_options = {'token_store': WindowsTokenStore('builder-excel-local', backend=vault),
                    'provider_factory': lambda account: provider, 'now': lambda: clock[0]}
    temporary = tempfile.TemporaryDirectory(prefix='builder-excel-', dir=ROOT)
    try:
        with patch.object(GmailProvider, '_request', block_network), \
                patch.object(WindowsTokenStore, 'backend', new=property(lambda store: vault)):
            project = create_project(Path(temporary.name) / 'project', name='Excel-Bewerbungen: lokaler Gesamtablauf', workspace_mode='applications')
            db = project.connection
            run = ImportService(project).prepare_data_source(str(workbook), options={'sheet': 'Bewerbungsziele'})
            rows = BulkSourceService(db).rows(run['id'], limit=100)
            assert len(rows['rows']) == 20 and all(row['eligible'] for row in rows['rows'])
            assert run['counts'] == {'Imported': 20}
            assert db.execute('SELECT COUNT(*) FROM applications').fetchone()[0] == 0
            counts = Counter(row['values']['Email'] for row in rows['rows'])
            assert set(counts) == ALLOWED and set(counts.values()) == {4}
            checked('delivered_xlsx_all_twenty_rows_selectable_only_five_allowed_addresses', dict(counts))
            mapping = {'contact.display_name': 'Ansprechpartner', 'contact.email': 'Email', 'contact.salutation': 'Anrede',
                       'company.name': 'Unternehmen', 'job.title': 'Stelle', 'application.cover_letter': 'Anschreiben'}
            selected = BulkSourceService(db).select([r['id'] for r in rows['rows']], mapping)
            sources = [c['source'] for c in selected['contacts']]
            values = [BulkSourceService(db).resolve(s)['fields'] for s in sources]
            assert all(len(value) == 24 and value['Bewerber_Name'] == 'Timon Huwer' for value in values)
            checked('all_eighteen_original_columns_and_six_standard_fields_available')
            graph = starter_graph()
            data, subject, body, sink = graph['nodes']
            data['config'].update(sources=sources, allow_duplicate_recipients=True)
            subject['config']['text'] = 'EmailCenter TEST {{Bewerbungs_ID}} – Bewerbung als {{Stelle}} bei {{Unternehmen}}'
            body['config']['text'] = '{{Anrede_vollstaendig}}\n\n{{Anschreiben}}\n\nMit freundlichen Grüßen\n{{Bewerber_Name}}'
            doc, replace, convert, rename, image = [node(kind) for kind in ('docx', 'replace', 'convert', 'attachment', 'image')]
            doc['config']['path'] = str(originals[1])
            replace['config']['rules'] = [{'find': '{{' + key + '}}', 'replacement': '', 'field': field}
                for key, field in [('NAME', 'contact.display_name'), ('COMPANY', 'company.name'), ('EMAIL', 'contact.email')]]
            if original_column_rules:
                for rule, field in zip(replace['config']['rules'], ('Ansprechpartner Name', 'Unternehmen', '{{Email}}')):
                    rule['field'] = field
            rename['config']['filename'] = 'Anschreiben_{{Bewerbungs_ID}}.pdf'
            if pdf_company_filenames:
                convert['config']['filename'] = 'Anschreiben{{Unternehmen}}.pdf'
            image['config']['path'] = str(originals[2])
            graph['nodes'].extend([doc, replace, convert, image] + ([] if pdf_company_filenames else [rename]))
            for a, out, b, port in [(doc, 'file', replace, 'docx'), (data, 'values', replace, 'values'),
                (replace, 'file', convert, 'docx'), (image, 'file', sink, 'attachments')] + (
                [(convert, 'file', sink, 'attachments')] if pdf_company_filenames else
                [(convert, 'file', rename, 'file'), (data, 'values', rename, 'values'), (rename, 'file', sink, 'attachments')]):
                graph['edges'].append({'from': a['id'], 'output': out, 'to': b['id'], 'input': port})
            # A real common PDF is supplied as another separate attachment node.
            common = ROOT / 'docs/abnahme/A1_Layout/Original_Render/Vorlage.pdf'
            common_hash = sha(common)
            pdf_node = node('pdf')
            pdf_node['config']['path'] = str(common)
            graph['nodes'].append(pdf_node)
            graph['edges'].append({'from': pdf_node['id'], 'output': 'file', 'to': sink['id'], 'input': 'attachments'})
            mail = MailService(project, **mail_options)
            account = mail.register_account(provider.email, {'refresh_token': 'synthetic-memory-only'})
            builder = EmailBuilderService(project)
            options = {'libreoffice_path': find_libreoffice(), 'provider_account_id': account['id']}
            preview = builder.preview(graph, **options)
            assert preview['ready'], preview['rows']
            assert all('{{' not in r['subject'] + r['body'] for r in preview['rows'])
            checked('all_twenty_subjects_bodies_and_docx_rules_resolved_before_creation')
            if original_column_rules:
                checked('original_excel_header_and_wrapped_word_rule_fields_resolved')
            builder.save('Excel-Gesamtablauf', graph)
            result = builder.create('20 lokale Testbewerbungen', graph, preview['fingerprint'], delivery_plan={
                'interval_seconds': 2, 'scheduled_local': due.isoformat(), 'timezone_id': 'Europe/Berlin',
                'daily_budget': 100, 'window_start': '00:00', 'window_end': '00:00'}, **options)
            batch, group = result['batch'], result['dispatch']
            assert len(batch['items']) == 20 and group['status'] == 'Preparing'
            expected = {}
            pdf_results = []
            for item in batch['items']:
                value = item['source_snapshot']['fields']
                draft = mail.draft(item['draft_id'])
                assert draft['recipients']['to'] == [value['Email']]
                assert value['Bewerbungs_ID'] in draft['subject'] and value['Unternehmen'] in draft['subject']
                assert value['Anschreiben'] in draft['body'] and value['Anrede_vollstaendig'] in draft['body']
                attached = draft['configuration']['attachments']
                assert len(attached) == 3
                filename = ('Anschreiben' + value['Unternehmen'] if pdf_company_filenames else 'Anschreiben_' + value['Bewerbungs_ID']) + '.pdf'
                personal = next(e for e in attached if e['filename'] == filename)
                assert project.file_path(personal['path']).name == filename
                assert db.execute('SELECT original_filename FROM documents WHERE id=?', (personal['document_id'],)).fetchone()[0] == filename
                with pdfplumber.open(project.file_path(personal['path'])) as pdf:
                    text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
                    assert len(pdf.pages) == 2
                    assert all(value[k] in text for k in ('contact.display_name', 'contact.email', 'company.name'))
                    assert '{{' not in text
                pdf_results.append({'id': value['Bewerbungs_ID'], 'filename': filename, 'pages': 2, 'sha256': personal['hash']})
                expected[draft['subject']] = (value['Email'], value['Anschreiben'], personal['hash'], filename)
            documents = db.execute("SELECT * FROM documents WHERE format='docx'").fetchall()
            assert len(documents) == 20
            for document in documents:
                assert '{{' not in extract_docx_text(project.file_path(document['file_path']))
            assert db.execute("SELECT COUNT(*) FROM documents WHERE format='pdf'").fetchone()[0] == 20
            checked('twenty_real_two_page_personal_pdfs_and_twenty_retained_docx_three_attachments_each', pdf_results)
            if pdf_company_filenames:
                checked('direct_convert_pattern_preserved_in_twenty_saved_pdf_paths_and_document_names')
            delivery = BulkDeliveryService(project, mail=mail)
            for _ in batch['items']:
                group = delivery.prepare_next(group['id'])
            assert group['status'] == 'Ready' and group['allow_duplicate_recipients']
            assert provider.sent == []
            group = delivery.approve(group['id'], group['fingerprint'])
            group = delivery.start(group['id'], group['fingerprint'], background=True)
            group = delivery.next(group['id'])
            assert group['counts']['sent'] == 0 and 'wait_until' in group
            checked('planning_and_review_send_nothing_before_five_minute_due_time')
            clock[0] = due
            group = delivery.next(group['id'])
            assert group['counts']['sent'] == 1
            delivery.pause(group['id'])
            project_path = project.path
            project.close()
            project = open_project(project_path)
            mail = MailService(project, **mail_options)
            mail.recover()
            delivery = BulkDeliveryService(project, mail=mail)
            group = delivery.snapshot(group['id'])
            assert group['status'] == 'Paused'
            group = delivery.approve(group['id'], group['fingerprint'], confirm_overdue=True)
            group = delivery.start(group['id'], group['fingerprint'], background=True)
            for _ in range(19):
                clock[0] += timedelta(seconds=2)
                group = delivery.next(group['id'])
            assert group['counts']['sent'] == 20 and group['status'] == 'Completed'
            delivery.next(group['id'])
            assert len(provider.sent) == 20
            for raw in provider.sent:
                message = message_from_bytes(raw, policy=policy.default)
                address, body_text, personal_hash, personal_filename = expected[str(message['Subject'])]
                assert str(message['To']) == address
                assert body_text in message.get_body(preferencelist=('plain',)).get_content()
                parts = list(message.iter_attachments())
                assert len(parts) == 3
                assert any(hashlib.sha256(p.get_payload(decode=True)).hexdigest() == personal_hash and p.get_filename() == personal_filename for p in parts)
            checked('fake_sender_twenty_correct_mime_messages_interval_pause_reopen_resume_no_duplicate_sends')
            assert sha(common) == common_hash and all(sha(path) == digest for path, digest in original_hashes.items())
            checked('workbook_docx_image_and_common_pdf_originals_unchanged')
            after = code_hashes()
            changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
            assert not changed
            report.update(status='Completed', elapsed_seconds=round(time.monotonic() - started, 3),
                          workbook_sha256=sha(workbook), code_changed_during_run=changed, tested_source_hashes=before)
            project.close()
            project = None
            temporary.cleanup()
            checked('test_project_database_closed_before_windows_cleanup')
            save()
    except Exception as error:
        report.update(status='Failed', error_type=type(error).__name__, error_message=str(error))
        save()
        raise
    finally:
        if project is not None:
            project.close()
        temporary.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--original-column-rules', action='store_true')
    parser.add_argument('--pdf-company-filenames', action='store_true')
    args = parser.parse_args()
    run(args.workbook, args.output, original_column_rules=args.original_column_rules, pdf_company_filenames=args.pdf_company_filenames)
