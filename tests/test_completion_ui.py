"""Offscreen A1/A2/A3 user flows, including worker dispatch and safe rendering."""
import json
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ui as harness
import test_builder_ui as builder_fixture
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument,QImage
from emailcenter.ui.administration_page import AdministrationEditor
from emailcenter.ui.structured_fields import CustomFieldsEditor
from emailcenter.ui.builder_preview import MailRenderer
from emailcenter.ui.record_dialogs import RecordDialog
from emailcenter.email_builder import node
from emailcenter.builder_groups import selection_graph

ROOT=Path(__file__).resolve().parents[1]

class CompletionDesktopTests(unittest.TestCase):
    setUpClass=classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp=harness.DesktopTests.setUp
    tearDown=harness.DesktopTests.tearDown
    wait_for=harness.DesktopTests.wait_for
    wait_idle=harness.DesktopTests.wait_idle
    submit=harness.DesktopTests.submit
    action_result=harness.DesktopTests.action_result
    open_test_project=harness.DesktopTests.open_test_project
    builder=builder_fixture.BuilderDesktopTests.builder
    sources=builder_fixture.BuilderDesktopTests.sources

    def test_administration_requires_project_and_loads_through_worker(self):
        page=self.window.pages['administration'];self.assertFalse(page.isEnabled())
        self.open_test_project();self.window.navigate('administration');self.wait_idle()
        page.section.setCurrentIndex(page.section.findData('statuses'));self.wait_idle()
        self.assertGreater(page.total,0);self.assertEqual(self.errors,[])

    def test_signature_editor_saves_default_through_worker(self):
        self.open_test_project();editor=AdministrationEditor('signatures',parent=self.window)
        self.window.open_record_dialog(editor);editor.fields['name'].setText('Test');editor.fields['content_text'].setPlainText('Viele Grüße')
        editor.fields['is_default'].setCurrentIndex(editor.fields['is_default'].findData(True));editor.validate();self.wait_idle()
        result=self.action_result('administration_list',{'section':'signatures'})
        self.assertEqual(result['rows'][0]['name'],'Test');self.assertEqual(result['rows'][0]['is_default'],1);self.assertEqual(self.errors,[])

    def test_record_address_and_custom_values_form(self):
        self.open_test_project();data=self.action_result('record_details',{'entity':'contacts'})
        editor=RecordDialog(data,self.window);editor.fields['display_name'].setText('Testperson');editor.fields['address_city'].setText('Berlin')
        editor.custom_fields.add('score',3);fields=editor.values()
        self.assertEqual(json.loads(fields['address_json'])['city'],'Berlin');self.assertEqual(json.loads(fields['custom_fields_json'])['score'],3)
        editor.close()

    def test_custom_fields_preserve_nested_and_reject_duplicate(self):
        editor=CustomFieldsEditor();editor.populate({'nested':{'list':[1,True]},'score':2})
        self.assertEqual(editor.values()['nested'],{'list':[1,True]});editor.add('score',4)
        with self.assertRaises(ValueError):editor.values()
        editor.close()

    def test_inline_renderer_only_loads_registered_content_ids(self):
        renderer=MailRenderer();renderer.display({'email':'test@example.test','subject':'Bild','body_format':'html','body':'<p>Hallo</p><img src="cid:local@image">','inline_content':{'local@image':(ROOT/'assets/Logo256.png').read_bytes()}})
        image=renderer.text.loadResource(QTextDocument.ResourceType.ImageResource,QUrl('cid:local@image'))
        self.assertIsInstance(image,QImage);self.assertFalse(image.isNull())
        self.assertEqual(renderer.text.loadResource(QTextDocument.ResourceType.ImageResource,QUrl('https://example.test/tracker')).size(),0)
        renderer.display({'email':'other@example.test','subject':'Ohne','body_format':'plain','body':'Text'})
        self.assertEqual(renderer.text.local_images,{});renderer.close()

    def test_group_insert_undo_and_redo(self):
        page=self.builder();self.sources(page);original=len(page.graph['nodes'])
        fragment=selection_graph(page.graph,[page.graph['nodes'][1]['id'],page.graph['nodes'][2]['id']])
        page._group_action='insert'
        with patch('emailcenter.ui.email_builder_page.QInputDialog.getItem',return_value=('Texte',True)):
            page.display_node_groups([{'id':'test','name':'Texte','graph_json':json.dumps(fragment),'version':'v'}],choose=True)
        self.assertEqual(len(page.graph['nodes']),original+2);page.undo();self.assertEqual(len(page.graph['nodes']),original)
        page.redo();self.assertEqual(len(page.graph['nodes']),original+2)

    def test_attachment_order_moves_and_undo(self):
        import test_email_builder as core
        page=self.builder();graph=deepcopy(page.graph);first=node('image');second=node('pdf');sink=graph['nodes'][3]
        graph['nodes'].extend([first,second]);graph['edges'].extend([core.edge(first,'file',sink,'attachments'),core.edge(second,'file',sink,'attachments')]);page.commit(graph,sink['id'])
        self.assertEqual(page.attachment_order.count(),2);page.attachment_order.setCurrentIndex(0);page.move_attachment(1)
        self.assertEqual([e['from'] for e in page.graph['edges'] if e['input']=='attachments'],[second['id'],first['id']]);page.undo()
        self.assertEqual([e['from'] for e in page.graph['edges'] if e['input']=='attachments'],[first['id'],second['id']])

    def test_human_readable_document_set_details(self):
        page=self.window.pages['administration'];dialog=page.details_dialog({'name':'Satz','variants':[{'id':'doc','original_filename':'Anschreiben.pdf','format':'pdf','file_path':'documents/test.pdf','deleted_at':None}]})
        from PySide6.QtWidgets import QTreeWidget,QComboBox
        tree=dialog.findChild(QTreeWidget);self.assertGreater(tree.topLevelItemCount(),0)
        self.assertEqual(dialog.findChild(QComboBox).currentData(),'doc');dialog.close()

    def test_real_mjpeg_video_decodes_in_editor_without_autoplay(self):
        from media_fixture import make_video
        from emailcenter.ui.builder_preview import BuilderPreview
        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        path=make_video(self.directory/'video.avi');preview=BuilderPreview()
        preview.display({'format':'video','path':str(path),'filename':path.name})
        self.wait_for(lambda:preview.player.hasVideo() or preview.player.error()!=QMediaPlayer.Error.NoError)
        self.assertEqual(preview.player.error(),QMediaPlayer.Error.NoError,preview.player.errorString())
        self.assertEqual(preview.player.playbackState(),QMediaPlayer.PlaybackState.StoppedState)
        frames=[];preview.findChild(QVideoWidget).videoSink().videoFrameChanged.connect(lambda frame:frames.append(frame) if frame.isValid() else None)
        preview.player.play();self.wait_for(lambda:bool(frames));preview.clear()
        self.assertTrue(frames);self.assertTrue(preview.player.source().isEmpty());preview.close()

    def test_close_during_operation_finishes_and_stops_schedulers(self):
        from threading import Event
        from emailcenter.application.workspace import WorkspaceService
        self.open_test_project();started,release=Event(),Event();original=WorkspaceService.snapshot
        def slow(service):
            started.set();release.wait(5);return original(service)
        with patch.object(WorkspaceService,'snapshot',slow):
            self.assertTrue(self.window.controller.submit('snapshot'));self.wait_for(started.is_set)
            self.window.close();self.assertTrue(self.window._close_requested)
            self.assertFalse(self.window.bulk_timer.isActive());self.assertTrue(self.window.controller.thread.isRunning())
            release.set();self.wait_for(lambda:not self.window.controller.thread.isRunning())
        self.assertEqual(self.errors,[])

    def test_failed_operation_cancels_close_and_keeps_app_usable(self):
        from threading import Event
        from emailcenter.application.workspace import WorkspaceService
        self.open_test_project();started,release=Event(),Event()
        def failure(service):
            started.set();release.wait(5);raise ValueError('Test: Speichern fehlgeschlagen')
        with patch.object(WorkspaceService,'snapshot',failure):
            self.assertTrue(self.window.controller.submit('snapshot'));self.wait_for(started.is_set);self.window.close();release.set();self.wait_idle()
        self.assertFalse(self.window._close_requested);self.assertTrue(self.window.isEnabled());self.assertTrue(self.window.bulk_timer.isActive())
        self.assertTrue(self.errors);self.errors.clear()

    def test_bulk_checkbox_keeps_emitting_item_alive(self):
        from PySide6.QtCore import Qt
        from shiboken6 import isValid
        self.open_test_project()
        self.action_result('create_record', {'entity':'contacts', 'fields':{
            'display_name':'Kontakt', 'email':'checkbox@example.test'}})
        self.window.workspace_mail_action('bulk', None);self.wait_idle()
        dialog=self.window._bulk_dialog;item=dialog.contacts.item(0)
        identifier=item.data(Qt.ItemDataRole.UserRole)
        for index in range(20):
            checked=index % 2 == 0
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.assertTrue(isValid(item))
            self.assertIs(dialog.contacts.item(0),item)
            self.assertEqual(identifier in dialog.selected,checked)
            self.assertIn(f'{int(checked)} ausgewählt',dialog.selection_status.text())
        dialog.reject()
