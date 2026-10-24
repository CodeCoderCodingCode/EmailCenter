from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from emailcenter.builtin_templates import DOCUMENTS, MAILS, GRAPHS, builder_graph, install_document, install_mail
from emailcenter.email_builder import validate_graph
from emailcenter.project import create_project
from emailcenter.resources import resource_path, shared_oauth_client
from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.appearance import THEMES


class ReleaseFeatureTests(unittest.TestCase):
    def test_templates_are_editable_and_graphs_have_no_targets(self):
        with tempfile.TemporaryDirectory(dir=resource_path()) as folder:
            project=create_project(Path(folder)/'project')
            try:
                for key in DOCUMENTS:
                    value=install_document(project,key)
                    self.assertTrue(value)
                for key in MAILS:
                    value=install_mail(project,key)
                    self.assertTrue(value)
                self.assertEqual(project.connection.execute('SELECT COUNT(*) FROM templates').fetchone()[0],6)
                self.assertEqual(project.connection.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0],0)
            finally:
                project.close()
        for key in GRAPHS:
            graph=builder_graph(key)
            validate_graph(graph,editable=True)
            self.assertEqual(graph['nodes'][0]['config']['sources'],[])

    def test_theme_and_feedback_preferences_persist(self):
        with tempfile.TemporaryDirectory(dir=resource_path()) as folder:
            store=PreferencesStore(Path(folder)/'settings.json')
            store.load()
            prefs=Preferences.validate({**Preferences().values(),'theme':'aurora','transition_style':'slide','animation_ms':300,'hover_feedback':False,'builder_preview_delay_ms':350})
            store.save(prefs)
            value,warning=store.load()
            self.assertIsNone(warning)
            self.assertEqual(value,prefs)
        self.assertEqual(len(THEMES),14)

    def test_guide_covers_every_page_block_and_settings_anchor(self):
        from emailcenter.email_builder import NODE_TYPES
        text=resource_path('guide','EmailCenter_Guide.html').read_text(encoding='utf-8')
        for kind in NODE_TYPES:
            self.assertIn('id="node-'+kind+'"',text)
        for i in range(9): self.assertIn('id="settings-'+str(i)+'"',text)
        for page in ('overview','workspace','applications','companies','contacts','applicants','jobs','templates','documents','followups','import','mail','word_replace','builder','administration','settings'):
            self.assertIn('id="'+page+'"',text)
        self.assertGreater(text.count('data:image/png;base64,'),40)
        self.assertIn('sieben Tagen',text)

    def test_shared_client_does_not_discover_authorized_users(self):
        import emailcenter.resources as resources
        with tempfile.TemporaryDirectory(dir=resource_path()) as folder:
            root=Path(folder); (root/'json').mkdir()
            (root/'json/token.json').write_text('{"refresh_token":"synthetic-only"}')
            with patch.object(resources,'resource_path',side_effect=lambda *parts:root.joinpath(*parts)):
                self.assertIsNone(shared_oauth_client())

    def test_long_capture_path_retains_public_name(self):
        from emailcenter.mail_service import MailService
        with tempfile.TemporaryDirectory(dir=resource_path()) as folder:
            root=Path(folder)
            project=create_project(root/'project')
            try:
                source=root/'input.txt';source.write_text('synthetic-only')
                filename='Ein_sehr_langer_Dateiname_'+('x'*50)+'.txt'
                directory=Path('documents/builder')/('g'*36)/('d'*36)
                entry=MailService(project)._copy_attachments([{'path':str(source),'filename':filename}],directory)[0]
                self.assertEqual(entry['filename'],filename)
                self.assertEqual(project.file_path(entry['path']).name,filename)
                self.assertEqual(project.file_path(entry['path']).read_text(),'synthetic-only')
                self.assertLessEqual(len(str(project.file_path(entry['path']))),258)
            finally:project.close()

    def test_unrepresentable_name_is_rejected_instead_of_silently_renamed(self):
        from emailcenter.mail_service import MailService
        from emailcenter.mail_models import MailError
        with tempfile.TemporaryDirectory(dir=resource_path()) as folder:
            root=Path(folder);project=create_project(root/'project')
            try:
                source=root/'input.txt';source.write_text('synthetic-only')
                with self.assertRaisesRegex(MailError, 'Windows'):
                    MailService(project)._copy_attachments([{'path':str(source),'filename':('x'*245)+'.txt'}],Path('exports/mail')/('a'*36))
                self.assertEqual(project.connection.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0)
            finally:project.close()


class ReleaseUiTests(unittest.TestCase):
    def test_context_help_and_theme_transitions(self):
        from PySide6.QtWidgets import QApplication, QWidget
        from PySide6.QtCore import QEvent
        from emailcenter.ui.help_viewer import HelpDialog,context_anchor
        from emailcenter.ui.transitions import PageTransition
        app=QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        dialog=HelpDialog('node-date')
        self.assertEqual(dialog.browser.source().fragment(),'node-date')
        self.assertIn('Kompletter Bewerbungsablauf',dialog.browser.toPlainText())
        dialog.navigate('settings-0')
        self.assertEqual(dialog.browser.source().fragment(),'settings-0')
        dialog.close(); dialog.deleteLater()
        widget=QWidget();widget.resize(300,200);widget.show();app.processEvents()
        transition=PageTransition(widget)
        for style in ('fade','slide','zoom','none'):
            transition.configure(Preferences(transition_style=style))
            transition.play()
            if style=='none':self.assertIsNone(transition.animation)
            else:self.assertIsNotNone(transition.animation)
            transition.stop()
        transition.play(True);self.assertIsNone(transition.animation)
        widget.close();widget.deleteLater()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
