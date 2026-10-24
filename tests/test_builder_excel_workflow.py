"""Raw workflow sources preserve user columns and repeated target choices."""
from copy import deepcopy
from pathlib import Path
import unittest
import json
import sqlite3

import test_email_builder as builder_harness
from emailcenter.bulk_sources import BulkSourceService, column_fields
from emailcenter.import_service import ImportService, ImportServiceError
from emailcenter.email_builder import validate_graph
from emailcenter.bulk_delivery import BulkDeliveryService
from emailcenter.mail_service import MailService
from emailcenter.credentials import WindowsTokenStore
from test_mail import MemoryVault, FakeProvider
from unittest.mock import patch
from emailcenter.documents import extract_docx_text
from emailcenter.word_replace import WordReplaceService
from emailcenter.word_replace_runs import WordReplaceRuns


class BuilderExcelTests(unittest.TestCase):
    setUp = builder_harness.BuilderTests.setUp
    tearDown = builder_harness.BuilderTests.tearDown
    create = builder_harness.BuilderTests.create
    document_chain = builder_harness.BuilderTests.document_chain

    def source(self, text=None):
        path = self.root / 'targets.csv'
        path.write_text(text or 'Bewerber Name;Ansprechpartner;Unternehmen;Email;Status;Anschreiben\nTimon Huwer;Ada;Firma A;test@example.test;offen;Text A\nTimon Huwer;Grace;Firma B;test@example.test;offen;Text B\n', encoding='utf-8-sig')
        run = ImportService(self.project).prepare_data_source(str(path))
        return run, BulkSourceService(self.db).rows(run['id'])

    def select(self, rows):
        return BulkSourceService(self.db).select([r['id'] for r in rows['rows']], {
            'contact.display_name': 'Ansprechpartner', 'contact.email': 'Email',
            'company.name': 'Unternehmen', 'application.cover_letter': 'Anschreiben'})

    def test_raw_import_does_not_require_or_create_application_records(self):
        run, rows = self.source()
        self.assertEqual(run['counts'], {'Imported': 2})
        self.assertTrue(all(r['eligible'] for r in rows['rows']))
        self.assertEqual(ImportService(self.project).process(run['id'])['counts'], run['counts'])
        for table in ('contacts', 'companies', 'applications'):
            self.assertEqual(self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        selected = self.select(rows)
        self.assertEqual(selected['contacts'][0]['source_values']['Bewerber_Name'], 'Timon Huwer')
        self.assertEqual(selected['contacts'][1]['source_values']['Status'], 'offen')
        self.workspace.close()
        self.workspace.open(str(self.root / 'project'))
        self.assertTrue(all(r['eligible'] for r in BulkSourceService(self.workspace.project.connection).rows(run['id'])['rows']))

    def test_changed_source_is_rejected_before_receipt(self):
        path = self.root / 'changed.csv'
        path.write_text('Name\nAda\n', encoding='utf-8')
        service = ImportService(self.project)
        inspection = service.inspect(str(path))
        path.write_text('Name\nGrace\n', encoding='utf-8')
        with self.assertRaises(ImportServiceError):
            service.prepare_data_source(str(path), expected_hash=inspection['source_hash'])
        self.assertEqual(service.list_runs()['total'], 0)

    def test_invalid_raw_row_cannot_bypass_validation_via_empty_domain_editor(self):
        run, rows = self.source('Name\nAda,unexpected-extra\n')
        self.assertFalse(rows['rows'][0]['eligible'])
        self.assertTrue(rows['rows'][0]['errors'])
        with self.assertRaises(ImportServiceError):
            ImportService(self.project).edit_row(rows['rows'][0]['id'], {})
        self.assertEqual(ImportService(self.project).detail(run['id'])['counts'], {'Invalid': 1})

    def test_german_aliases_and_collisions_preserve_every_column(self):
        result = column_fields(['Bewerber Name', 'Bewerber_Name', 'Anschriftstraße', '123 Wert', 'Ansprechpartner Name', 'Ansprechpartner-Name'])
        self.assertEqual(result, {'Bewerber_Name_2': 'Bewerber Name', 'Bewerber_Name': 'Bewerber_Name', 'Anschriftstrasse': 'Anschriftstraße', 'column_123_Wert': '123 Wert', 'Ansprechpartner_Name': 'Ansprechpartner Name', 'Ansprechpartner_Name_2': 'Ansprechpartner-Name'})

    def test_word_replace_original_headers_are_bound_without_alias_collision(self):
        run, rows = self.source('Bewerber Name;Bewerber_Name;Ansprechpartner;Unternehmen;Email;Anschreiben;Anschriftstraße\nCorrect applicant;Other column;Ada;Firma A;test@example.test;Text A;Beispielweg 12\n')
        self.graph['nodes'][0]['config']['sources'] = [c['source'] for c in self.select(rows)['contacts']]
        source = self.document_chain()
        replace = next(n for n in self.graph['nodes'] if n['kind'] == 'replace')
        replace['config']['rules'][0]['field'] = 'Bewerber Name'
        next(r for r in replace['config']['rules'] if r['find'] == '{{ROLE}}').update(field='Anschriftstraße', replacement='')
        preview = self.service.preview(self.graph)
        self.assertTrue(preview['ready'], preview['rows'])
        self.assertIn('Correct applicant', preview['rows'][0]['documents'][0]['text'])
        self.assertNotIn('Other column', preview['rows'][0]['documents'][0]['text'])
        self.assertIn('Beispielweg 12', preview['rows'][0]['documents'][0]['text'])
        rules_before = deepcopy(replace['config']['rules'])
        batch = self.create()
        attached = MailService(self.project).draft(batch['items'][0]['draft_id'])['configuration']['attachments'][0]
        self.assertIn('Correct applicant', extract_docx_text(self.project.file_path(attached['path'])))
        self.assertEqual(replace['config']['rules'], rules_before)
        word = WordReplaceService(self.project)
        rules = [{**r, 'field': '{{Bewerber Name}}' if i == 0 else r['field']} for i, r in enumerate(rules_before)]
        word_preview = word.preview(str(source), rules, sources=self.graph['nodes'][0]['config']['sources'])
        self.assertTrue(word_preview['ready'], word_preview['rows'])
        self.assertIn('Correct applicant', word_preview['rows'][0]['text'])
        self.assertIn('Beispielweg 12', word_preview['rows'][0]['text'])
        word_output = word.create(source_path=str(source), rules=rules, sources=self.graph['nodes'][0]['config']['sources'], expected_fingerprint=word_preview['fingerprint'], output_directory=str(self.root / 'word-output'))
        self.assertTrue(word_output)
        output = next((self.root / 'word-output').glob('*.docx'))
        self.assertIn('Correct applicant', extract_docx_text(output))
        self.assertIn('Beispielweg 12', extract_docx_text(output))
        run_service = WordReplaceRuns(self.project)
        run = run_service.begin(source_path=str(source), rules=rules, sources=self.graph['nodes'][0]['config']['sources'], expected_fingerprint=word_preview['fingerprint'], output_directory=str(self.root / 'run-output'))
        result = run_service.next(run['id'])
        self.assertEqual(result['status'], 'Completed')
        output = next((self.root / 'run-output').glob('*.docx'))
        self.assertIn('Correct applicant', extract_docx_text(output))
        self.assertIn('Beispielweg 12', extract_docx_text(output))

    def test_mapping_error_identifies_the_actual_missing_or_invalid_entry(self):
        run, rows = self.source()
        reference = self.select(rows)['contacts'][0]['source']
        for changes, message in [({'contact.email': None}, 'Pflichtzuordnung fehlt: E-Mail'),
                                 ({'Bad Key': 'Email'}, 'Ungültiger Datenfeldname: Bad Key'),
                                 ({'custom': 'Missing'}, 'Quellspalte fehlt: Missing')]:
            value = deepcopy(reference)
            for key, column in changes.items():
                if column is None:
                    del value['mapping'][key]
                else:
                    value['mapping'][key] = column
            with self.assertRaisesRegex(ValueError, message):
                BulkSourceService(self.db).resolve(value)

    def test_repeated_recipients_require_explicit_builder_choice(self):
        run, rows = self.source()
        data, subject, body, sink = self.graph['nodes']
        data['config']['sources'] = [c['source'] for c in self.select(rows)['contacts']]
        subject['config']['text'] = '{{Unternehmen}} / {{Bewerber_Name}}'
        body['config']['text'] = '{{Anschreiben}}'
        preview = self.service.preview(self.graph)
        self.assertFalse(preview['ready'])
        data['config']['allow_duplicate_recipients'] = True
        preview = self.service.preview(self.graph)
        self.assertTrue(preview['ready'], preview['rows'])
        self.assertEqual([r['subject'] for r in preview['rows']], ['Firma A / Timon Huwer', 'Firma B / Timon Huwer'])
        batch = self.create()
        delivery = BulkDeliveryService(self.project)
        self.assertTrue(delivery.details(batch['id'])['allow_duplicate_recipients'])

    def test_legacy_graph_and_boolean_validation(self):
        legacy = deepcopy(self.graph)
        del legacy['nodes'][0]['config']['allow_duplicate_recipients']
        validate_graph(legacy, complete=True)
        self.graph['nodes'][0]['config']['allow_duplicate_recipients'] = 'true'
        with self.assertRaises(ValueError):
            validate_graph(self.graph)

    def test_repeated_recipient_choice_reaches_review_and_local_dispatch(self):
        run, rows = self.source()
        self.graph['nodes'][0]['config'].update(sources=[c['source'] for c in self.select(rows)['contacts']], allow_duplicate_recipients=True)
        batch = self.create()
        vault, provider = MemoryVault(), FakeProvider()
        mail = MailService(self.project, token_store=WindowsTokenStore('excel-test', backend=vault), provider_factory=lambda account: provider)
        account = mail.register_account(provider.email, {'refresh_token': 'fake'})
        delivery = BulkDeliveryService(self.project, mail=mail)
        group = delivery.begin(batch['id'], account['id'])
        for _ in batch['items']:
            group = delivery.prepare_next(group['id'])
        self.assertEqual(group['status'], 'Ready')
        self.assertTrue(group['allow_duplicate_recipients'])
        approved = delivery.approve(group['id'], group['fingerprint'])
        self.assertEqual(approved['status'], 'Paused')
        self.assertEqual(provider.sent, [])
        item = batch['items'][0]
        snapshot = deepcopy(item['source_snapshot'])
        next(n for n in snapshot['builder_graph']['nodes'] if n['kind'] == 'data')['config']['allow_duplicate_recipients'] = False
        self.db.execute('UPDATE email_draft_batch_items SET source_snapshot_json=? WHERE batch_id=? AND item_key=?', (json.dumps(snapshot), batch['id'], item['item_key']))
        self.assertNotEqual(delivery.snapshot(group['id'])['fingerprint'], approved['fingerprint'])
        with self.assertRaises(ValueError):
            delivery.start(group['id'], approved['fingerprint'])
        self.assertEqual(provider.sent, [])

    def test_normal_groups_keep_database_duplicate_guard(self):
        batch = self.create()
        first, second = batch['items']
        self.assertEqual(first['recipient_reuse_allowed'], 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE email_draft_batch_items SET recipient_snapshot=? WHERE batch_id=? AND item_key=?', (first['recipient_snapshot'].upper(), batch['id'], second['item_key']))

    def test_pdf_attachment_also_retains_personal_docx_without_attaching_it(self):
        self.document_chain(pdf=True)
        converter = self.root / 'fake-converter.exe'
        converter.write_bytes(b'local stub')
        def convert(source, target, **options):
            Path(target).write_bytes(b'%PDF-1.4 local fake converter')
            return str(target)
        with patch('emailcenter.email_builder.convert_docx_to_pdf', side_effect=convert):
            batch = self.create(libreoffice_path=str(converter))
        documents = self.db.execute('SELECT * FROM documents ORDER BY format').fetchall()
        self.assertEqual([d['format'] for d in documents], ['docx', 'docx', 'pdf', 'pdf'])
        for document in documents:
            self.assertTrue(self.project.file_path(document['file_path']).is_file())
        for item in batch['items']:
            attached = MailService(self.project).draft(item['draft_id'])['configuration']['attachments']
            self.assertEqual(len(attached), 1)
            self.assertTrue(attached[0]['filename'].endswith('.pdf'))
