"""Explicit UI localization preserves identifiers, editable values and mail content."""
from copy import deepcopy
import json
import ast
from pathlib import Path
import re
import unittest

from emailcenter.language import (Message, format_text, get_language, render,
                                  set_language, translate, translate_tree)
from emailcenter.language_catalog import TEXTS, TEMPLATES
from emailcenter.email_builder import validate_graph, starter_graph
from emailcenter.oauth_callback import completion_page
import test_ui as harness
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFormLayout, QLabel,
                              QLineEdit, QListWidget, QListWidgetItem, QTableWidget,
                              QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
from emailcenter.ui import localization as captions
from emailcenter.ui.pages import label
from emailcenter.ui.dialogs import FormDialog
from emailcenter.ui.mail_workflow import PrepareMailDialog
from emailcenter.ui.bulk_source_dialogs import ManualRowsDialog
from emailcenter.preferences import PreferencesStore


class MessageTests(unittest.TestCase):
    def setUp(self):
        set_language('de')

    def tearDown(self):
        set_language('de')

    def test_numeric_slots_preserve_user_words_braces_and_unicode(self):
        source = 'Vorlagen {{company.name}} {0} 😀'
        set_language('en')
        message = format_text('{0} · Zeile {1}', source, 12)
        self.assertEqual(message, source + ' · Row 12')
        self.assertEqual(render(message.message, 'de'), source + ' · Zeile 12')
        self.assertEqual(format_text('Eintrag {0}', 'Speichern'), 'Record Speichern')

    def test_nested_owned_caption_rerenders_without_translating_other_arguments(self):
        message = format_text('{0} bearbeiten', translate('Unternehmen'))
        set_language('en')
        self.assertEqual(translate(message), 'Edit Companies')
        self.assertEqual(translate(format_text('{0} bearbeiten', 'Unternehmen')), 'Edit Unternehmen')
        set_language('de')
        self.assertEqual(translate(message), 'Unternehmen bearbeiten')

    def test_unknown_owned_text_has_readable_fallback(self):
        set_language('en')
        self.assertEqual(translate('Future caption'), 'Future caption')
        self.assertEqual(format_text('Future {0}', 'Vorlagen'), 'Future Vorlagen')

    def test_join_keeps_owned_fragments_and_raw_imported_values_distinct(self):
        from emailcenter.language import join_text
        message = join_text(' · ', (translate('Betreff'), 'Vorlagen {{NAME}}', translate('Bereit')))
        set_language('en')
        self.assertEqual(translate(message), 'Subject · Vorlagen {{NAME}} · Ready')
        set_language('de')
        self.assertEqual(translate(message), 'Betreff · Vorlagen {{NAME}} · Bereit')
        self.assertEqual(join_text('\n', []), '')

    def test_localized_text_copy_and_pickle_keep_snapshot_and_owned_metadata(self):
        from copy import copy
        import pickle
        from emailcenter.language import LocalizedText
        message=format_text('{0} · {1}',translate('Betreff'),'Vorlagen {0} 😀')
        set_language('en')
        for duplicate in (copy(message),deepcopy(message),pickle.loads(pickle.dumps(message))):
            self.assertIsInstance(duplicate,LocalizedText)
            self.assertEqual(duplicate,'Betreff · Vorlagen {0} 😀')
            self.assertEqual(duplicate.message,message.message)
            self.assertEqual(translate(duplicate),'Subject · Vorlagen {0} 😀')

    def test_language_validation_and_explicit_render_do_not_change_active_language(self):
        with self.assertRaises(ValueError):set_language('fr')
        self.assertEqual(render(Message('Empfänger'), 'en'), 'Recipient')
        self.assertEqual(get_language(), 'de')

    def test_catalog_numeric_slots_match_and_no_encoding_damage(self):
        for source, target in TEMPLATES.items():
            self.assertEqual(sorted(re.findall(r'\{\d+\}',source)), sorted(re.findall(r'\{\d+\}',target)),source)
        for value in [*TEXTS.values(), *TEMPLATES.values()]:
            self.assertNotIn('â€¦',value)
            self.assertFalse(any(0xd800 <= ord(char) <= 0xdfff for char in value))
        self.assertGreater(len(TEXTS),1800)

    def test_every_reviewed_source_is_in_the_generated_catalog(self):
        from emailcenter.language import TEXTS as base
        audit=json.loads((harness.ROOT/'docs/localization/Catalog_Audit.json').read_text(encoding='utf-8'))
        for entry in audit:
            self.assertTrue(entry['source'] in (TEMPLATES if entry['template'] else {**base,**TEXTS}), entry['source'])

    def test_static_translation_boundaries_have_catalog_entries(self):
        from emailcenter.language import TEXTS as base
        for path in (harness.ROOT/'src/emailcenter').rglob('*.py'):
            if path.name in ('language.py','language_catalog.py'):continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('_ui_tr','_ui_format','caption') and node.args:
                    values=[node.args[0]]
                    if isinstance(node.args[0],ast.IfExp):values=[node.args[0].body,node.args[0].orelse]
                    for value in values:
                        if isinstance(value,ast.Constant) and isinstance(value.value,str):
                            self.assertTrue(value.value in (TEMPLATES if node.func.id=='_ui_format' else {**base,**TEXTS}), f'{path}: {value.value}')

    def test_owned_german_raised_messages_have_explicit_translation_boundaries(self):
        from tools.localization_audit import GERMAN,message_pattern
        for path in (harness.ROOT/'src/emailcenter').rglob('*.py'):
            if path.name in ('language.py','language_catalog.py'):continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node,ast.Raise) or not isinstance(node.exc,ast.Call) or not node.exc.args:continue
                message=message_pattern(node.exc.args[0])
                if message:self.assertFalse(GERMAN.search(message[0]) or any(c in message[0] for c in 'äöüÄÖÜß'),f'{path}:{node.lineno}: {message[0]}')

    def test_context_distinguishes_company_field_from_companies_navigation(self):
        field=translate('Unternehmen',context='field');navigation=translate('Unternehmen')
        set_language('en')
        self.assertEqual(translate(field),'Company');self.assertEqual(translate(navigation),'Companies')
        set_language('de');self.assertEqual(translate(field),'Unternehmen')

    def test_backend_validation_message_obeys_language_and_graph_stays_unchanged(self):
        graph = {'nodes': [], 'edges': []}; original = deepcopy(graph)
        set_language('en')
        with self.assertRaisesRegex(ValueError,'1 to 100 blocks'):validate_graph(graph)
        self.assertEqual(graph,original)
        set_language('de')
        with self.assertRaisesRegex(ValueError,'1 bis 100 Bausteine'):validate_graph(graph)

    def test_address_errors_and_subject_caption_are_english_but_custom_names_stay_raw(self):
        from emailcenter.mail_models import address, header, MailError
        set_language('en')
        with self.assertRaisesRegex(MailError,'without display names'):address('Display name <name@example.test>')
        with self.assertRaisesRegex(MailError,'Subject missing'):header('',translate('Betreff'))
        with self.assertRaisesRegex(MailError,'Vorlagen missing'):header('','Vorlagen')
        with self.assertRaisesRegex(ValueError,'Unknown language'):set_language('fr')

    def test_builder_error_translates_owned_block_type_without_changing_graph_data(self):
        from emailcenter.email_builder import node
        graph={'nodes':[node('description')],'edges':[]}
        graph['nodes'][0]['config']['foreign_key']='Vorlagen'
        original=deepcopy(graph);set_language('en')
        with self.assertRaisesRegex(ValueError,'Invalid block properties: Description / Cover letter'):validate_graph(graph)
        self.assertEqual(graph,original)

    def test_context_warnings_translate_and_proposed_mail_content_stays_unchanged(self):
        from test_mail_context import MailContextTests
        fixture=MailContextTests('runTest');fixture.setUp()
        try:
            first=fixture.record('contacts',display_name='Vorlagen',email='first@example.test')
            second=fixture.record('contacts',display_name='Speichern',email='second@example.test')
            for contact in (first,second):fixture.link('applications',fixture.application,contact)
            german=fixture.context();set_language('en');english=fixture.context()
            self.assertEqual(english['subject'],german['subject'])
            self.assertEqual(english['body'],german['body'])
            self.assertEqual(english['recipients'],german['recipients'])
            self.assertEqual([c['id'] for c in english['candidates']],[c['id'] for c in german['candidates']])
            self.assertEqual([c['display_name'] for c in english['candidates']],['Speichern','Vorlagen'])
            self.assertNotIn('Mehrere Ansprechpartner',str(english['warnings']))
            self.assertTrue(english['warnings'])
            self.assertEqual(fixture.db.execute('SELECT COUNT(*) FROM email_attempts').fetchone()[0],0)
        finally:fixture.tearDown()

    def test_oauth_page_is_bilingual_and_keeps_browser_feedback_honest(self):
        english = completion_page(language='en')
        self.assertIn('lang="en"', english)
        self.assertIn('Google response received',english)
        self.assertIn('Close tab',english)
        self.assertIn('does not confirm a saved account connection',english)
        self.assertIn('window.close()',english)
        self.assertNotIn('Tab schließen',english)
        self.assertIn('Sign-in cancelled',completion_page(True,language='en'))
        german = completion_page(language='de')
        self.assertIn('Tab schließen',german)
        self.assertEqual(get_language(),'de')


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class CaptionTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)

    def setUp(self):
        set_language('de');self.root=QWidget();self.layout=QVBoxLayout(self.root)

    def tearDown(self):
        from PySide6.QtCore import QEvent
        self.root.close();self.root.deleteLater()
        self.application.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.application.processEvents();set_language('de')

    def switch(self, language):
        set_language(language);translate_tree(self.root)

    def test_plain_labels_user_inputs_and_dynamic_captions_do_not_collide(self):
        raw=label('Vorlagen');owned=label(translate('Vorlagen'));editor=QLineEdit('Speichern')
        for w in (raw,owned,editor):self.layout.addWidget(w)
        self.switch('en')
        self.assertEqual(raw.text(),'Vorlagen');self.assertEqual(editor.text(),'Speichern')
        self.assertEqual(owned.text(),'Templates')
        captions.set_text(owned,'Name')
        self.switch('de');self.switch('en')
        self.assertEqual(owned.text(),'Name')

    def test_combo_keeps_internal_values_selection_and_no_business_signals(self):
        combo=QComboBox();self.layout.addWidget(combo)
        captions.add_item(combo,translate('Vorlagen'),'template-key')
        combo.addItem('Vorlagen','user-key')
        combo.setCurrentIndex(0);signals=[]
        combo.currentTextChanged.connect(signals.append)
        combo.currentIndexChanged.connect(signals.append)
        self.switch('en')
        self.assertEqual(combo.itemText(0),'Templates');self.assertEqual(combo.itemText(1),'Vorlagen')
        self.assertEqual(combo.currentData(),'template-key');self.assertEqual(signals,[])
        combo.setCurrentIndex(1);signals.clear();self.switch('de')
        self.assertEqual(combo.currentData(),'user-key');self.assertEqual(signals,[])

    def test_editable_combo_preserves_text_cursor_selection_and_modified_flag(self):
        combo=QComboBox();self.layout.addWidget(combo);combo.setEditable(True)
        captions.add_item(combo,translate('Vorlagen'),'template-key')
        editor=combo.lineEdit();editor.setText('Vorlagen {{NAME}}');editor.setSelection(2,5);editor.setModified(True)
        before=(editor.text(),editor.cursorPosition(),editor.selectionStart(),editor.selectedText())
        signals=[];editor.textChanged.connect(signals.append)
        self.switch('en')
        self.assertEqual((editor.text(),editor.cursorPosition(),editor.selectionStart(),editor.selectedText()),before)
        self.assertTrue(editor.isModified());self.assertEqual(signals,[])

    def test_editable_combo_preserves_full_emoji_selection(self):
        combo=QComboBox();self.layout.addWidget(combo);combo.setEditable(True)
        captions.add_item(combo,translate('Vorlagen'),'template-key')
        editor=combo.lineEdit();editor.setText('Vorlagen 😀 test');editor.setSelection(9,2);editor.setModified(True)
        before=(editor.text(),editor.cursorPosition(),editor.selectionStart(),editor.selectedText())
        self.assertEqual(before[-1],'😀')
        self.switch('en');self.assertEqual((editor.text(),editor.cursorPosition(),editor.selectionStart(),editor.selectedText()),before)
        self.switch('de');self.assertEqual(editor.selectedText(),'😀')

    def test_table_headers_and_owned_cells_translate_without_row_changes(self):
        table=QTableWidget(1,2);self.layout.addWidget(table)
        captions.headers(table,[translate('Betreff'),translate('Zustand')])
        table.setItem(0,0,captions.cell('Vorlagen'));table.setItem(0,1,captions.cell(translate('Gespeichert')))
        signals=[];table.itemChanged.connect(signals.append)
        self.switch('en')
        self.assertEqual(table.horizontalHeaderItem(0).text(),'Subject')
        self.assertEqual(table.item(0,0).text(),'Vorlagen');self.assertEqual(table.item(0,1).text(),'Saved')
        self.assertEqual(signals,[])

    def test_list_and_tree_captions_preserve_private_and_user_roles(self):
        values=QListWidget();tree=QTreeWidget();self.layout.addWidget(values);self.layout.addWidget(tree)
        item=captions.item(QListWidgetItem,translate('Anhang'));item.setData(Qt.ItemDataRole.UserRole,'attachment-key');values.addItem(item)
        tree.setColumnCount(2);captions.headers(tree,[translate('Angabe'),translate('Wert')])
        branch=captions.item(QTreeWidgetItem,[translate('Dateiname'),'Vorlagen']);tree.addTopLevelItem(branch)
        self.switch('en')
        self.assertEqual(item.text(),'Attachment');self.assertEqual(item.data(Qt.ItemDataRole.UserRole),'attachment-key')
        self.assertEqual(branch.text(0),'Filename');self.assertEqual(branch.text(1),'Vorlagen')

    def test_form_captions_translate_but_raw_choices_and_input_values_do_not(self):
        dialog=FormDialog(translate('Neue Bewerbung'),[('name','Firmenname','required'),('company','Unternehmen',[('Vorlagen','user-key')])])
        self.addCleanup(dialog.deleteLater)
        dialog.fields['name'].setText('Speichern')
        set_language('en');translate_tree(dialog)
        self.assertEqual(dialog.fields['name'].text(),'Speichern')
        self.assertEqual(dialog.fields['company'].currentText(),'Vorlagen')
        self.assertEqual(dialog.fields['company'].currentData(),'user-key')
        self.assertIn('Company name *',[w.text() for w in dialog.findChildren(QLabel)])
        raw=FormDialog('Raw',[('x','Vorlagen',None)],owned_captions=False);self.addCleanup(raw.deleteLater)
        translate_tree(raw);self.assertIn('Vorlagen',[w.text() for w in raw.findChildren(QLabel)])

    def test_mail_renderer_keeps_mail_contents_and_clear_does_not_restore_old_headers(self):
        from emailcenter.ui.builder_preview import MailRenderer
        view=MailRenderer();self.layout.addWidget(view)
        row={'sender':'sender@example.test','email':'target@example.test','subject':'Vorlagen','body':'Speichern {{NAME}}','body_format':'plain','attachments':[]}
        original=deepcopy(row);view.display(row)
        self.switch('en')
        self.assertIn('From: sender@example.test',view.headers.text())
        self.assertIn('Subject: Vorlagen',view.headers.text())
        self.assertEqual(view.attachments.text(),'Attachments: None')
        self.assertEqual(view.text.toPlainText(),'Speichern {{NAME}}');self.assertEqual(row,original)
        view.clear();self.switch('de');self.switch('en')
        self.assertEqual(view.headers.text(),'');self.assertEqual(view.attachments.text(),'')
        self.assertNotIn('target@example.test',view.text.toPlainText())
        view.display({**row,'body_format':'html','body':'<p>Unternehmen Vorlagen</p>'})
        self.switch('de');self.switch('en')
        self.assertEqual(view.text.toPlainText(),'Unternehmen Vorlagen')

    def test_calendar_locale_and_accessible_captions_change_without_changing_date(self):
        from PySide6.QtWidgets import QDateTimeEdit
        from PySide6.QtCore import QDateTime,QLocale
        date=QDateTimeEdit();self.layout.addWidget(date);date.setCalendarPopup(True)
        date.setDateTime(QDateTime.fromString('2026-10-20T09:30:00',Qt.DateFormat.ISODate))
        original=date.dateTime();signals=[];date.dateTimeChanged.connect(signals.append)
        captions.set_accessible_name(date,translate('Termin'))
        self.switch('en')
        self.assertEqual(date.dateTime(),original);self.assertEqual(signals,[])
        self.assertEqual(date.locale().language(),QLocale.Language.English)
        self.assertEqual(date.accessibleName(),'Date')
        self.switch('de');self.assertEqual(date.accessibleName(),'Termin')

    def test_immediate_send_and_scheduled_caption_change_in_english(self):
        set_language('en')
        dialog=PrepareMailDialog({'subject':'Vorlagen','provider_account_id':None},'Europe/Berlin');self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.windowTitle(),'Send')
        save=dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.assertEqual(save.text(),'Send')
        dialog.scheduled.setChecked(True)
        self.assertEqual(save.text(),'Schedule delivery')
        set_language('de');translate_tree(dialog)
        self.assertEqual(save.text(),'Versand planen')

    def test_progress_format_rerenders_counts_without_changing_progress(self):
        from PySide6.QtWidgets import QProgressBar
        progress=QProgressBar();self.layout.addWidget(progress);progress.setValue(42)
        captions.set_format(progress,format_text('{0}/{1} vorbereitet · {2} gesendet · {3} storniert · {4} zu prüfen',2,3,1,0,0))
        self.switch('en')
        self.assertEqual(progress.format(),'2/3 prepared · 1 sent · 0 cancelled · 0 to review')
        self.assertEqual(progress.value(),42)
        self.switch('de');self.assertIn('vorbereitet',progress.format())

    def test_replaced_combo_caption_keeps_id_and_clears_previous_metadata(self):
        combo=QComboBox();self.layout.addWidget(combo);combo.addItem('raw','contact-id')
        captions.set_item_text(combo,0,format_text('{0} · {1} · {2}',translate('Bereit'),'Vorlagen','name@example.test'))
        self.switch('en');self.assertEqual(combo.itemText(0),'Ready · Vorlagen · name@example.test')
        self.assertEqual(combo.currentData(),'contact-id')
        captions.set_item_text(combo,0,'Unternehmen');self.switch('de');self.switch('en')
        self.assertEqual(combo.itemText(0),'Unternehmen')

    def test_bulk_dispatch_captions_switch_without_actions_or_payload_changes(self):
        from emailcenter.ui.bulk_delivery_dialog import BulkDeliveryDialog
        dialog=BulkDeliveryDialog({'batch':{'name':'Vorlagen','id':'batch'},'accounts':[],'drafts':[], 'dispatch':None},self.root)
        value={'id':'dispatch','status':'Preparing','items':[{'name_snapshot':'Unternehmen','job':None,'job_id':None}],
               'counts':{'total':1,'prepared':0,'sent':0,'cancelled':0,'blocked':0,'pending':1},
               'timezone_id':'Europe/Berlin','last_error':'','wait_reason':'','background':False,'scheduled_local':None}
        original=deepcopy(value);actions=[];dialog.operation_requested.connect(lambda *args:actions.append(args))
        dialog.display(value)
        self.switch('en')
        self.assertEqual(dialog.windowTitle(),'Bulk delivery · Vorlagen')
        self.assertEqual(dialog.jobs.item(0).text(),'Unternehmen · not prepared yet')
        self.assertIn('Budget 100/day',dialog.status.text())
        self.assertEqual(value,original);self.assertEqual(actions,[])
        self.switch('de');self.assertEqual(dialog.windowTitle(),'Gruppenversand · Vorlagen')

    def test_project_wizard_summary_buttons_and_subtitles_keep_user_values(self):
        from emailcenter.ui.project_wizard import ProjectWizard
        from PySide6.QtWidgets import QWizard
        wizard=ProjectWizard(self.root)
        wizard.fields['name'].setText('Vorlagen')
        wizard.fields['goal'].setPlainText('Speichern {{NAME}}')
        wizard.refresh_summary(2)
        self.switch('en')
        self.assertEqual(wizard.button(QWizard.WizardButton.FinishButton).text(),'Create project')
        self.assertIn('Project goal: Speichern {{NAME}}',wizard.summary.toPlainText())
        self.assertIn('Gmail: Connect in the workspace',wizard.summary.toPlainText())
        self.assertTrue(wizard.summary.toPlainText().startswith('Vorlagen\nFolder:'))
        self.assertNotIn('Arbeitsmodus:',wizard.summary.toPlainText())
        self.switch('de');self.assertIn('Projektziel: Speichern {{NAME}}',wizard.summary.toPlainText())

    def test_project_wizard_runtime_caption_sources_are_in_catalog(self):
        from emailcenter.ui.project_wizard import ProjectWizard
        from emailcenter.language import TEXTS as base
        wizard=ProjectWizard(self.root);wizard.refresh_summary(2)
        def check(source):
            if not isinstance(source,Message):return
            self.assertTrue(source.source in (TEMPLATES if source.template else {**base,**TEXTS}) or not any(c.isalpha() for c in source.source),source.source)
            for value in source.arguments:check(value)
        for widget in [wizard,*wizard.findChildren(QWidget)]:
            for prop in widget.dynamicPropertyNames():
                key=bytes(prop).decode()
                if key.startswith('language'):check(widget.property(key))

    def test_toast_owned_captions_switch_and_raw_message_stays_plain_text(self):
        from emailcenter.ui.toast import Toast
        from emailcenter.preferences import Preferences
        toast=Toast(self.root);toast.configure(Preferences(reduced_motion=True))
        raw='Vorlagen {{NAME}} <b>Speichern</b>'
        toast.notify('Vorlagen',raw)
        self.switch('en')
        self.assertEqual(toast.title.text(),'Success · Vorlagen')
        self.assertEqual(toast.message.text(),raw)
        self.assertEqual(toast.message.textFormat(),Qt.TextFormat.PlainText)
        toast.notify(translate('Vorlagen'),format_text('{0} · Zeile {1}','Vorlagen',3))
        self.assertEqual(toast.title.text(),'Success · Templates')
        self.switch('de')
        self.assertEqual(toast.title.text(),'Erfolg · Vorlagen')
        self.assertEqual(toast.message.text(),'Vorlagen · Zeile 3')
        self.switch('en');self.assertEqual(toast.message.text(),'Vorlagen · Row 3')

    def test_english_reminder_distinguishes_both_dst_occurrences_by_error_type(self):
        from emailcenter.ui.reminder_page import ReminderDialog
        from emailcenter.mail_models import AmbiguousTimeError
        from emailcenter.reminder_service import local_reminder_time
        from PySide6.QtCore import QDate,QTime
        set_language('en')
        with self.assertRaisesRegex(AmbiguousTimeError,'ambiguous'):
            local_reminder_time('2026-10-25T02:30:00','Europe/Berlin')
        dialog=ReminderDialog({'source':'reminder','record':None,'applications':[]},self.root)
        dialog.title.setText('Vorlagen');dialog.zone.setCurrentText('Europe/Berlin')
        dialog.date.setDate(QDate(2026,10,25));dialog.time.setTime(QTime(2,30))
        self.assertFalse(dialog.occurrence.isHidden())
        events=[];dialog.operation_requested.connect(lambda action,payload:events.append((action,payload)))
        for occurrence in (0,1):
            dialog.occurrence.setCurrentIndex(dialog.occurrence.findData(occurrence));dialog.save()
        self.assertEqual([p['due_at_utc'] for _,p in events],['2026-10-25T00:30:00Z','2026-10-25T01:30:00Z'])
        self.assertTrue(all(action=='reminder_save' and p['title']=='Vorlagen' for action,p in events))
        dialog.date.setDate(QDate(2026,10,26));self.assertTrue(dialog.occurrence.isHidden())


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class LanguageDesktopTests(unittest.TestCase):
    setUpClass=classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp=harness.DesktopTests.setUp
    wait_for=harness.DesktopTests.wait_for
    wait_idle=harness.DesktopTests.wait_idle
    submit=harness.DesktopTests.submit
    open_test_project=harness.DesktopTests.open_test_project

    def tearDown(self):
        try:harness.DesktopTests.tearDown(self)
        finally:set_language('de')

    def english(self):
        self.window.save_preferences({**self.window.preferences.values(),'language':'en'})
        self.assertEqual(self.errors,[])

    def test_main_pages_settings_tabs_and_column_headers_switch_both_ways(self):
        self.english();settings=self.window.pages['settings']
        self.assertEqual(self.window.pages['companies'].table.horizontalHeaderItem(0).text(),'Company')
        self.assertEqual(self.window.pages['jobs'].table.horizontalHeaderItem(0).text(),'Job')
        self.assertEqual(settings.tabs.tabText(1),'Workspace / lists')
        self.assertEqual(settings.controls['workspace_mode'].itemText(1),'Email orders')
        self.assertEqual(settings.controls['workspace_mode'].itemData(1),'mail')
        settings.controls['mail_signature_name'].setText('Vorlagen')
        self.window.save_preferences({**self.window.preferences.values(),'language':'de'},preserve_edits=True)
        self.assertEqual(settings.controls['mail_signature_name'].text(),'Vorlagen')
        self.assertEqual(settings.tabs.tabText(1),'Arbeitsbereich / Listen')

    def test_language_persists_in_restart_and_project_user_names_stay_unchanged(self):
        self.open_test_project()
        self.submit('create_record',{'entity':'companies','fields':{'name':'Vorlagen','notes':'Speichern {{NAME}}'}})
        self.english()
        self.window.navigate('companies');self.wait_idle()
        page=self.window.pages['companies']
        self.assertEqual(page.table.item(0,0).text(),'Vorlagen')
        self.window.create_record('companies');self.wait_idle()
        dialog=self.window._record_dialog
        self.assertEqual(dialog.windowTitle(),'Create company')
        dialog.fields['name'].setText('Speichern')
        self.assertEqual(dialog.fields['name'].text(),'Speichern');dialog.reject()
        loaded,warning=PreferencesStore(self.directory/'preferences.json').load()
        self.assertIsNone(warning);self.assertEqual(loaded.language,'en')
        # New MainWindow reads stored language before constructing captions.
        from emailcenter.ui.main_window import MainWindow
        another=MainWindow(settings_store=PreferencesStore(self.directory/'preferences.json'))
        try:
            self.assertEqual(another.pages['settings'].tabs.tabText(1),'Workspace / lists')
            self.assertEqual(another.pages['companies'].table.horizontalHeaderItem(1).text(),'Industry')
            another.apply_preferences(loaded.__class__(language='de'))
            self.assertEqual(another.pages['settings'].theme.itemText(0),'Klar · Hell')
            self.assertEqual(another.pages['settings'].controls['workspace_mode'].itemText(1),'E-Mail-Aufträge')
        finally:
            another.close();self.wait_for(lambda:not another.controller.thread.isRunning());another.deleteLater()

    def test_manual_custom_field_caption_and_cells_remain_raw(self):
        self.english()
        dialog=ManualRowsDialog(['Vorlagen'],self.window)
        index=dialog.fields.index('Vorlagen')
        self.assertEqual(dialog.rows.horizontalHeaderItem(index).text(),'Vorlagen')
        self.assertEqual(dialog.rows.horizontalHeaderItem(dialog.fields.index('contact.display_name')).text(),'Contact person')
        dialog.rows.setItem(0,index,captions.cell('Speichern {{NAME}}'))
        set_language('de');translate_tree(dialog);set_language('en');translate_tree(dialog)
        self.assertEqual(dialog.rows.item(0,index).text(),'Speichern {{NAME}}')

    def test_saved_settings_toast_uses_english_owned_text(self):
        self.english()
        self.assertEqual(self.window.toast.title.text(),'Success · Settings')
        self.assertEqual(self.window.toast.message.text(),'Changes saved and applied.')

