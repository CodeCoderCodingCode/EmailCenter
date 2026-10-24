"""Personal PDF names survive preview, conversion, capture, and reopening."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_email_builder as service_harness
import test_builder_ui as ui_harness
import test_ui as harness
from emailcenter.builder_pdf_names import filename_fields, pdf_filename
from emailcenter.email_builder import node, validate_graph
from emailcenter.mail_service import MailService


class PdfNameTests(unittest.TestCase):
    def test_empty_pattern_preserves_original_document_stem(self):
        self.assertEqual(pdf_filename('', {}, 'Anschreiben.docx'), 'Anschreiben.pdf')
        self.assertEqual(pdf_filename(' ', {}, 'Anschreiben Bewerbung.DOCX'), 'Anschreiben Bewerbung.pdf')

    def test_original_headers_aliases_and_unicode_are_bound_without_collisions(self):
        fields = {'Unternehmen': 'Müller & Söhne', 'Bewerber_Name_2': 'Ada Lovelace', 'Bewerber_Name': 'Other'}
        headers = ['Unternehmen', 'Bewerber Name', 'Bewerber_Name']
        self.assertEqual(pdf_filename('Anschreiben{{Unternehmen}}.pdf', fields, 'input.docx', source_headers=headers),
                         'AnschreibenMüller & Söhne.pdf')
        self.assertEqual(pdf_filename('{{ Bewerber Name }}_{{Bewerber_Name}}.pdf', fields, 'input.docx', source_headers=headers),
                         'Ada Lovelace_Other.pdf')

    def test_values_are_literal_and_cannot_inject_paths(self):
        self.assertEqual(pdf_filename('Anschreiben_{{company.name}}.pdf', {'company.name': 'A/B:C?D\\E*F"G<H>I|J'}, 'input.docx'),
                         'Anschreiben_A_B_C_D_E_F_G_H_I_J.pdf')
        self.assertEqual(pdf_filename('{{company.name}}.pdf', {'company.name': '{{NAME}}'}, 'input.docx'), '{{NAME}}.pdf')

    def test_invalid_or_missing_fields_and_filenames_are_rejected(self):
        for pattern in ('../Anschreiben.pdf', 'A\\B.pdf', 'A.docx', 'A', 'NUL.pdf', 'CON.pdf', '.pdf', '..pdf', 'x' * 251,
                        '{{}}.pdf', '{{company.name}.pdf', '{{company.name\n}}.pdf', 'bad\x00.pdf'):
            with self.subTest(pattern=pattern):
                with self.assertRaises(ValueError):
                    pdf_filename(pattern, {'company.name': 'Example'}, 'input.docx')
        with self.assertRaisesRegex(ValueError, 'Datenfeld.*Unternehmen'):
            pdf_filename('{{Unternehmen}}.pdf', {}, 'input.docx')
        with self.assertRaises(ValueError):
            pdf_filename('{{Unternehmen}}.pdf', {'Unternehmen': 'x' * 250}, 'input.docx')
        self.assertEqual(filename_fields('A{{Unternehmen}}_{{company.name}}.pdf'), ['Unternehmen', 'company.name'])


class BuilderPdfNamesTests(unittest.TestCase):
    setUp = service_harness.BuilderTests.setUp
    tearDown = service_harness.BuilderTests.tearDown
    document_chain = service_harness.BuilderTests.document_chain

    def adapter(self, source, target, **options):
        Path(target).write_bytes(b'%PDF-1.4\nsynthetic adapter output')
        return Path(target)

    def prepare(self):
        source = self.document_chain(pdf=True)
        named = source.with_name('Anschreiben.docx')
        source.rename(named)
        next(n for n in self.graph['nodes'] if n['kind'] == 'docx')['config']['path'] = str(named)
        converter = self.root / 'soffice.exe'
        converter.write_bytes(b'test adapter')
        return next(n for n in self.graph['nodes'] if n['kind'] == 'convert'), converter

    def test_personal_names_match_preview_disk_document_metadata_and_reopened_draft(self):
        convert, executable = self.prepare()
        convert['config']['filename'] = 'Anschreiben{{company.name}}.pdf'
        with patch('emailcenter.email_builder.convert_docx_to_pdf', side_effect=self.adapter):
            preview = self.service.preview(self.graph, libreoffice_path=str(executable))
            self.assertTrue(preview['ready'], preview['rows'])
            self.assertEqual([r['attachments'][0]['filename'] for r in preview['rows']],
                             ['AnschreibenAda GmbH.pdf', 'AnschreibenGrace GmbH.pdf'])
            batch = self.service.create('Personal names', self.graph, preview['fingerprint'], libreoffice_path=str(executable))['batch']
        for item in batch['items']:
            attachment = MailService(self.project).draft(item['draft_id'])['configuration']['attachments'][0]
            expected = 'Anschreiben' + item['name_snapshot'] + ' GmbH.pdf'
            self.assertEqual(attachment['filename'], expected)
            self.assertEqual(self.project.file_path(attachment['path']).name, expected)
            self.assertTrue(self.project.file_path(attachment['path']).is_file())
            self.assertEqual(self.db.execute('SELECT original_filename FROM documents WHERE id=?', (attachment['document_id'],)).fetchone()[0], expected)
        self.workspace.close()
        self.workspace.open(str(self.root / 'project'))
        self.assertEqual(MailService(self.workspace.project).draft(batch['items'][0]['draft_id'])['configuration']['attachments'][0]['filename'], 'AnschreibenAda GmbH.pdf')

    def test_old_convert_config_and_original_word_name_remain_usable(self):
        convert, executable = self.prepare()
        convert['config'] = {}
        validate_graph(self.graph, complete=True)
        original = deepcopy(self.graph)
        value = self.service.preview(self.graph, libreoffice_path=str(executable))
        self.assertTrue(value['ready'], value['rows'])
        self.assertEqual(value['rows'][0]['attachments'][0]['filename'], 'Anschreiben.pdf')
        self.assertEqual(value['rows'][0]['personal_docx'][0]['filename'], 'Anschreiben.docx')
        self.assertEqual(self.graph, original)

    def test_invalid_name_stops_before_conversion_and_name_changes_require_new_preview(self):
        convert, executable = self.prepare()
        before = self.service.preview(self.graph, libreoffice_path=str(executable))
        convert['config']['filename'] = 'Anschreiben{{company.name}}.pdf'
        with patch('emailcenter.email_builder.convert_docx_to_pdf', side_effect=self.adapter), self.assertRaisesRegex(ValueError, 'Vorschau'):
            self.service.create('Changed name', self.graph, before['fingerprint'], libreoffice_path=str(executable))
        convert['config']['filename'] = '../bad.pdf'
        with patch('emailcenter.email_builder.convert_docx_to_pdf') as adapter:
            value = self.service.preview(self.graph, libreoffice_path=str(executable))
            self.assertFalse(value['ready'])
            with self.service.evaluate(self.graph, materialize=True, libreoffice_path=str(executable)) as value:
                self.assertFalse(value['ready'])
            adapter.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0], 0)


@unittest.skipUnless(harness.QT_AVAILABLE, 'PySide6 not installed')
class BuilderPdfNamesDesktopTests(unittest.TestCase):
    setUpClass = classmethod(harness.DesktopTests.setUpClass.__func__)
    setUp = harness.DesktopTests.setUp
    tearDown = harness.DesktopTests.tearDown
    wait_for = harness.DesktopTests.wait_for
    wait_idle = harness.DesktopTests.wait_idle
    submit = harness.DesktopTests.submit
    open_test_project = harness.DesktopTests.open_test_project
    builder = ui_harness.BuilderDesktopTests.builder

    def test_pdf_filename_editor_stores_pattern_and_round_trips_old_graph(self):
        page = self.builder()
        graph = deepcopy(page.graph)
        convert = node('convert')
        convert['config'] = {}
        graph['nodes'].append(convert)
        page.commit(graph, convert['id'])
        from PySide6.QtWidgets import QLineEdit
        editor = page.properties.findChild(QLineEdit, 'pdf_filename_pattern')
        self.assertEqual(editor.text(), '')
        self.assertIn('ursprünglicher', editor.placeholderText())
        editor.setText('Anschreiben{{Unternehmen}}.pdf')
        self.assertEqual(page.graph['nodes'][-1]['config']['filename'], 'Anschreiben{{Unternehmen}}.pdf')
        self.assertFalse(page.confirm.isChecked())
        page.save_button.click()
        self.wait_idle()
        self.assertTrue(page.version_id)
        self.assertEqual(page.graph['nodes'][-1]['config']['filename'], 'Anschreiben{{Unternehmen}}.pdf')
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
