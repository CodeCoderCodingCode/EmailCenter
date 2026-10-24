"""A1/A2/A3 regression coverage; no network or real mail sends."""
import json
from copy import deepcopy
from email import message_from_bytes,policy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_email_builder as fixture
from emailcenter.administration import AdministrationService
from emailcenter.builder_groups import BuilderGroupsService,selection_graph,insert_group
from emailcenter.email_builder import node,validate_graph
from emailcenter.mail_models import build_message,MailError
from emailcenter.mail_service import MailService
from emailcenter.record_service import fingerprint

ROOT=Path(__file__).resolve().parents[1]


class CompletionTests(unittest.TestCase):
    setUp=fixture.BuilderTests.setUp
    tearDown=fixture.BuilderTests.tearDown
    document_chain=fixture.BuilderTests.document_chain

    def test_structured_records_create_edit_and_dates(self):
        company=self.workspace.create_record('companies',{'name':'Firma','address_json':json.dumps({'street':'Testweg 1','city':'Berlin'}),'custom_fields_json':json.dumps({'branche':'IT','priority':3})})
        self.assertEqual(json.loads(company['address_json'])['city'],'Berlin')
        job=self.workspace.create_record('jobs',{'title':'Job','company_id':company['id'],'start_date':'2027-01-01','custom_fields_json':'{"remote":true}'})
        self.assertEqual(job['start_date'],'2027-01-01')
        contact=self.workspace.create_record('contacts',{'display_name':'Person','address_json':'{"country":"DE"}'})
        self.assertEqual(json.loads(contact['address_json'])['country'],'DE')
        self.workspace.update_record('contacts',contact['id'],{'custom_fields_json':'{"number":2}'},fingerprint(contact))
        with self.assertRaises(ValueError):self.workspace.create_record('jobs',{'title':'Invalid','company_id':company['id'],'start_date':'not a date'})

    def test_structured_validation_rejects_invalid_without_record(self):
        for content in ('[]','{"bad name":"x"}','{"x":NaN}','{"x":"\\u0000"}'):
            with self.subTest(content=content),self.assertRaises(ValueError):self.workspace.create_record('contacts',{'display_name':'Bad','custom_fields_json':content})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM contacts WHERE display_name='Bad'").fetchone()[0],0)

    def test_archive_trash_restore_and_purge(self):
        record=self.workspace.create_record('contacts',{'display_name':'Person'})
        admin=AdministrationService(self.project)
        admin.lifecycle('contacts',record['id'],'archive',fingerprint(record))
        self.assertEqual(self.workspace.list_records('contacts')['total'],0)
        row=admin.list('records','contacts','archived')['rows'][0]
        admin.lifecycle('contacts',record['id'],'trash',row['version'])
        row=admin.list('records','contacts','trash')['rows'][0]
        admin.lifecycle('contacts',record['id'],'restore',row['version'])
        self.assertEqual(self.workspace.list_records('contacts')['total'],1)
        row=admin.list('records','contacts')['rows'][0]
        admin.lifecycle('contacts',record['id'],'trash',row['version'])
        row=admin.list('records','contacts','trash')['rows'][0]
        with self.assertRaises(ValueError):admin.lifecycle('contacts',record['id'],'purge',row['version'])
        admin.lifecycle('contacts',record['id'],'purge',row['version'],True)
        self.assertEqual(admin.list('records','contacts','trash')['total'],0)

    def test_archive_requires_fresh_version(self):
        record=self.workspace.create_record('contacts',{'display_name':'Person'})
        self.workspace.update_record('contacts',record['id'],{'phone':'123'},fingerprint(record))
        with self.assertRaises(ValueError):AdministrationService(self.project).lifecycle('contacts',record['id'],'archive',fingerprint(record))

    def test_used_records_not_permanently_deleted(self):
        record=self.workspace.create_record('companies',{'name':'Firma'})
        job=self.workspace.create_record('jobs',{'company_id':record['id'],'title':'Job'})
        admin=AdministrationService(self.project)
        admin.lifecycle('companies',record['id'],'trash',fingerprint(record))
        row=admin.list('records','companies','trash')['rows'][0]
        with self.assertRaisesRegex(ValueError,'verwendet'):admin.lifecycle('companies',record['id'],'purge',row['version'],True)
        self.assertIsNotNone(self.db.execute('SELECT id FROM job_postings WHERE id=?',(job['id'],)).fetchone())

    def test_statuses_custom_and_system_rules(self):
        admin=AdministrationService(self.project)
        created=admin.save_status({'code':'review','label':'Prüfung','sort_order':50,'is_terminal':False})
        custom=next(r for r in admin.list('statuses')['rows'] if r['id']==created['id'])
        admin.save_status({'code':'reviewed','label':'Geprüft','sort_order':51,'is_terminal':True},created['id'],custom['version'])
        system=next(r for r in admin.list('statuses')['rows'] if r['is_system'])
        with self.assertRaises(ValueError):admin.save_status({'code':'changed','label':'Test','is_terminal':False},system['id'],system['version'])
        with self.assertRaises(ValueError):admin.delete_status(system['id'],system['version'])

    def test_signature_cas_and_history(self):
        identifier=MailService(self.project).save_signature('Name','Alt')
        admin=AdministrationService(self.project);row=admin.list('signatures')['rows'][0]
        self.workspace.administration_signature_save({'name':'Neu','content_text':'Text','content_html':'<b>Text</b>'},identifier,row['version'])
        with self.assertRaises(MailError):self.workspace.administration_signature_save({'name':'Konflikt','content_text':'Text'},identifier,row['version'])
        self.workspace.create_record('contacts',{'display_name':'Person'})
        self.assertTrue(admin.list('activity')['rows'])

    def test_export_history_hash(self):
        target=self.root/'result.csv';target.write_text('Name\nPerson',encoding='utf-8')
        admin=AdministrationService(self.project)
        admin.log_export('records',{'path':str(target),'count':1},{'entity':'contacts'})
        row=admin.list('exports')['rows'][0]
        self.assertEqual(row['row_count'],1);self.assertEqual(len(row['file_hash']),64)

    def test_group_saved_reopened_inserted_and_edges_preserved(self):
        selected=[n['id'] for n in self.graph['nodes'][1:3]]
        groups=BuilderGroupsService(self.project);rows=groups.save('Texte',self.graph,selected)
        fragment=json.loads(rows[0]['graph_json']);merged,ids=insert_group(self.graph,fragment)
        self.assertEqual(len(ids),2);self.assertEqual(len(merged['nodes']),6)
        self.assertEqual(len(set(n['id'] for n in merged['nodes'])),6)
        self.assertEqual(merged['edges'],self.graph['edges'])
        self.assertGreater(min(n['x'] for n in merged['nodes'][-2:]),max(n['x'] for n in self.graph['nodes']))
        self.assertEqual(groups.list(),rows)

    def test_group_sources_cleared_and_delete_cas(self):
        groups=BuilderGroupsService(self.project)
        rows=groups.save('Quelle',self.graph,[self.graph['nodes'][0]['id']])
        self.assertEqual(json.loads(rows[0]['graph_json'])['nodes'][0]['config']['sources'],[])
        with self.assertRaises(ValueError):groups.delete(rows[0]['id'],'stale')
        self.assertEqual(groups.delete(rows[0]['id'],rows[0]['version']),[])

    def inline_graph(self):
        image=node('inline_image');image['config']['path']=str(ROOT/'assets/Logo256.png')
        sink=self.graph['nodes'][3];sink['config']['body_format']='html'
        self.graph['nodes'].append(image);self.graph['edges'].append(fixture.edge(image,'text',sink,'body'))
        return image

    def test_inline_personal_preview_and_captured_draft(self):
        image=self.inline_graph();preview=self.service.preview(self.graph)
        self.assertTrue(preview['ready'],preview['rows'])
        self.assertIn('cid:ec-',preview['rows'][0]['body'])
        batch=self.service.create('Inline',self.graph,preview['fingerprint'])['batch']
        draft=MailService(self.project).draft(batch['items'][0]['draft_id'])
        self.assertTrue(draft['configuration']['attachments'][0]['cid'])
        data=MailService(self.project)._attachment_bytes(draft['configuration']['attachments'])
        raw=build_message('sender@example.test',{'to':['recipient@example.test'],'cc':[],'bcc':[]},draft['subject'],draft['body'],'html','<test@example.test>','2026-10-12T10:00:00Z',data)
        message=message_from_bytes(raw,policy=policy.default)
        parts=[p for p in message.walk() if p.get_content_maintype()=='image']
        self.assertEqual(len(parts),1);self.assertEqual(parts[0].get_content_disposition(),'inline')
        self.assertEqual(parts[0]['Content-ID'],'<'+data[0][3]+'>')

    def test_inline_requires_html_and_valid_file(self):
        image=self.inline_graph();self.graph['nodes'][3]['config']['body_format']='plain'
        self.assertFalse(self.service.preview(self.graph)['ready'])
        self.graph['nodes'][3]['config']['body_format']='html';image['config']['path']=str(self.root/'bad.png');Path(image['config']['path']).write_bytes(b'not an image')
        self.assertFalse(self.service.preview(self.graph)['ready'])

    def test_attachment_rename_and_edge_order(self):
        first=node('image');first['config']['path']=str(ROOT/'assets/Logo256.png')
        rename=node('attachment');rename['config']['filename']='{{company.name}}.png'
        self.graph['nodes'].extend([first,rename]);source,sink=self.graph['nodes'][0],self.graph['nodes'][3]
        self.graph['edges'].extend([fixture.edge(first,'file',rename,'file'),fixture.edge(source,'values',rename,'values'),fixture.edge(rename,'file',sink,'attachments')])
        preview=self.service.preview(self.graph);self.assertTrue(preview['ready'],preview['rows'])
        self.assertEqual(preview['rows'][0]['attachments'][0]['filename'],'Ada GmbH.png')
        rename['config']['filename']='../wrong.png';self.assertFalse(self.service.preview(self.graph)['ready'])
        rename['config']['filename']='wrong.pdf';self.assertFalse(self.service.preview(self.graph)['ready'])

    def test_layout_before_group_with_converter_double(self):
        self.document_chain();replacement=next(n for n in self.graph['nodes'] if n['kind']=='replace')
        def convert(source,target,**options):
            Path(target).write_bytes(b'%PDF-test');return Path(target)
        with patch('emailcenter.email_builder.convert_docx_to_pdf',side_effect=convert):
            value=self.service.asset_preview(self.graph,replacement['id'],layout=True)
        self.assertEqual(value['format'],'pdf');self.assertEqual(value['content'],b'%PDF-test')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0],0)

    def test_invalid_inline_width_and_group_selection(self):
        image=self.inline_graph();image['config']['width']=0
        with self.assertRaises(MailError):validate_graph(self.graph)
        with self.assertRaises(ValueError):selection_graph(self.graph,['unknown'])

    def document_for_purge(self):
        import hashlib
        from emailcenter.database import DocumentRepository
        target=self.project.file_path('documents/purge.pdf',create_parent=True);target.write_bytes(b'%PDF-test')
        row=DocumentRepository(self.db).create(file_path='documents/purge.pdf',original_filename='purge.pdf',file_format='pdf',document_type='test',file_size_bytes=target.stat().st_size,template_version_id=None,file_hash=hashlib.sha256(target.read_bytes()).hexdigest())
        admin=AdministrationService(self.project);admin.lifecycle('documents',row['id'],'trash',fingerprint(row))
        return admin,admin.list('records','documents','trash')['rows'][0],target

    def test_owned_unreferenced_file_is_purged_with_receipt(self):
        admin,row,path=self.document_for_purge()
        result=admin.lifecycle('documents',row['id'],'purge',row['version'],True)
        self.assertFalse(path.exists());self.assertEqual(result['cleanup'][0]['status'],'Deleted')

    def test_changed_document_blocks_purge(self):
        admin,row,path=self.document_for_purge();path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'verändert'):admin.lifecycle('documents',row['id'],'purge',row['version'],True)
        self.assertTrue(path.exists());self.assertEqual(admin.list('records','documents','trash')['total'],1)

    def test_json_reference_blocks_purge(self):
        admin,row,path=self.document_for_purge()
        self.workspace.create_record('contacts',{'display_name':'Linked','custom_fields_json':json.dumps({'document':row['id']})})
        with self.assertRaisesRegex(ValueError,'verwendet'):admin.lifecycle('documents',row['id'],'purge',row['version'],True)
        self.assertTrue(path.exists())

    def test_locked_file_cleanup_can_resume_after_restart(self):
        admin,row,path=self.document_for_purge();original=Path.unlink
        def locked(target,*args,**kwargs):
            if target==path:raise PermissionError('gesperrt')
            return original(target,*args,**kwargs)
        with patch.object(Path,'unlink',locked):result=admin.lifecycle('documents',row['id'],'purge',row['version'],True)
        self.assertTrue(path.exists());self.assertEqual(result['cleanup'][0]['status'],'Blocked')
        receipt=AdministrationService(self.project).list('cleanup')['rows'][0]
        recovered=AdministrationService(self.project).cleanup(receipt['id'],receipt['version'])
        self.assertEqual(recovered['status'],'Deleted');self.assertFalse(path.exists())

    def test_signature_default_is_unique_and_stale_edit_preserves_it(self):
        mail=MailService(self.project);first=mail.save_signature('Erste','Text',is_default=True)
        old=AdministrationService(self.project).list('signatures')['rows'][0]
        second=mail.save_signature('Zweite','Text',is_default=True)
        self.assertEqual(self.db.execute('SELECT id FROM email_signatures WHERE is_default=1').fetchone()[0],second)
        with self.assertRaises(MailError):mail.save_signature('Alt','Text',signature_id=first,expected_version=old['version'],is_default=True)
        self.assertEqual(self.db.execute('SELECT id FROM email_signatures WHERE is_default=1').fetchone()[0],second)

    def test_archived_records_hidden_in_new_choices(self):
        contact=self.workspace.create_record('contacts',{'display_name':'Archive','email':'archive@example.test'})
        AdministrationService(self.project).lifecycle('contacts',contact['id'],'archive',fingerprint(contact))
        self.assertNotIn(contact['id'],[r['id'] for r in self.workspace.snapshot()['choices']['contacts']])
        from emailcenter.mail_bulk import BulkMailService
        self.assertNotIn(contact['id'],[r['id'] for r in BulkMailService(self.project).details()['contacts']])

    def test_cleanup_path_normalization_protects_project_metadata(self):
        from uuid import uuid4
        admin=AdministrationService(self.project);identifier=str(uuid4());metadata=self.project.path/'emailcenter.json';before=metadata.read_bytes()
        self.db.execute("INSERT INTO file_cleanup VALUES(?,?,?,'Pending',NULL,'2026-01-01','2026-01-01')",(identifier,'documents/../emailcenter.json',admin._file_hash(metadata)))
        row=admin.cleanup(identifier);self.assertEqual(row['status'],'Blocked');self.assertEqual(metadata.read_bytes(),before)

    def test_activity_shows_record_and_searches_its_name(self):
        self.workspace.create_record('companies',{'name':'Findable GmbH'})
        rows=AdministrationService(self.project).list('activity',search='Findable')['rows']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['entity_name'],'Findable GmbH');self.assertIn('Datensatz erstellt',rows[0]['label'])
