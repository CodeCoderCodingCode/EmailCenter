from datetime import datetime, timezone
from copy import deepcopy
import unittest
from unittest.mock import patch

from emailcenter.builder_values import FieldValues, VALUE_CONFIGS, clean_text, render_text, value_output, frozen_clock
from emailcenter.email_builder import node, validate_graph
from emailcenter.mail_models import MailError
from test_email_builder import BuilderTests, edge


class ValueTests(unittest.TestCase):
    def test_raw_columns_and_literal_values(self):
        fields = FieldValues({'Ansprechpartner_Name': 'Ada', 'Unternehmen': '<Firma>'}, headers=['Ansprechpartner Name', 'Unternehmen'])
        self.assertEqual(render_text('{{ Ansprechpartner Name }} bei {{Unternehmen}}', fields), 'Ada bei <Firma>')
        self.assertEqual(render_text('{{Unternehmen}}', fields, escape=True), '&lt;Firma&gt;')
        with self.assertRaises(MailError):
            render_text('{{}}', fields)

    def test_date_timezone_offsets_formats_and_source(self):
        config = deepcopy(VALUE_CONFIGS['date'])
        clock = frozen_clock('2027-01-31T23:30:00+00:00')
        values, text = value_output('date', config, {}, clock)
        self.assertEqual(text, '01.02.2027')
        self.assertEqual(values['datum'], text)
        config.update(mode='source', source_field='Startdatum', offset_days=-1, format='yyyy-MM-dd')
        self.assertEqual(value_output('date', config, {'Startdatum': '01.02.2027'}, clock)[1], '2027-01-31')
        config.update(mode='fixed', value='2027-02-01', format='dd. Monat yyyy', offset_days=0)
        self.assertEqual(value_output('date', config, {}, clock)[1], '01. Februar 2027')

    def test_time_and_variable_overwrite(self):
        config = deepcopy(VALUE_CONFIGS['time'])
        clock = frozen_clock('2027-01-31T23:30:15+00:00')
        self.assertEqual(value_output('time', config, {}, clock)[1], '00:30')
        config.update(mode='fixed', value='17:42:10', format='HH:mm:ss')
        self.assertEqual(value_output('time', config, {}, clock)[1], '17:42:10')
        variable = {**VALUE_CONFIGS['variable'], 'field': 'datum', 'value': '{{firma}}'}
        with self.assertRaises(MailError):
            value_output('variable', variable, {'datum': 'old', 'firma': 'new'}, clock)
        variable['overwrite'] = True
        self.assertEqual(value_output('variable', variable, {'datum': 'old', 'firma': 'new'}, clock)[0]['datum'], 'new')

    def test_clean_preserves_paragraphs(self):
        self.assertEqual(clean_text('  Hallo   Welt \r\n\r\n Gruß  ', VALUE_CONFIGS['clean']), 'Hallo Welt\n\nGruß')
        config = {**VALUE_CONFIGS['clean'], 'remove_empty_lines': True, 'case': 'upper'}
        self.assertEqual(clean_text(' A\n\n b ', config), 'A\nB')
        with self.assertRaises(MailError):
            frozen_clock(datetime(2027, 1, 1))


class ValueGraphTests(BuilderTests):
    def test_values_flow_clock_stable_and_create(self):
        data, subject, body, mail = self.graph['nodes']
        date, time, variable, clean = [node(k) for k in ('date', 'time', 'variable', 'clean')]
        variable['config'].update(field='beginn', value='{{datum}} um {{uhrzeit}}')
        body['config']['text'] = '  Hallo {{contact.display_name}}  \n\n {{beginn}} '
        self.graph['nodes'].extend([date, time, variable, clean])
        self.graph['edges'] = [e for e in self.graph['edges'] if not (e['to'] == body['id'] or (e['from'] == body['id'] and e['to'] == mail['id']))]
        self.graph['edges'].extend([edge(data, 'values', date, 'values'), edge(date, 'values', time, 'values'), edge(time, 'values', variable, 'values'), edge(variable, 'values', body, 'values'), edge(body, 'text', clean, 'text'), edge(clean, 'text', mail, 'body')])
        preview = self.service.preview(self.graph, evaluation_time='2027-01-31T23:30:00+00:00')
        self.assertTrue(preview['ready'], preview['rows'])
        self.assertIn('01.02.2027 um 00:30', preview['rows'][0]['body'])
        batch = self.service.create('Frozen', self.graph, preview['fingerprint'])['batch']
        self.assertEqual(len(batch['items']), 2)
        self.assertNotIn('_values', str(preview))

    def test_new_kinds_validate_editable(self):
        for kind in ('date', 'time', 'variable', 'clean'):
            value = node(kind)
            self.assertEqual(value['kind'], kind)
