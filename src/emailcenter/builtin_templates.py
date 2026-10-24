"""Editable starter templates without recipients, accounts or approval."""
from .resources import resource_path
from .email_builder import node, starter_graph
from .document_service import DocumentService
from .mail_templates import MailTemplateService

DOCUMENTS = {'cover': ('Anschreiben · Ausbildung', 'Anschreiben_Ausbildung.docx'), 'cover-job': ('Anschreiben · Beruf', 'Anschreiben_Beruf.docx'), 'cv': ('Lebenslauf · Klar', 'Lebenslauf.docx')}
MAILS = {
    'application': ('Bewerbung · Unterlagen', 'Bewerbung bei {{company.name}} als {{job.title}}', '{{contact.salutation}} {{contact.display_name}},\n\nanbei übersende ich Ihnen meine Bewerbungsunterlagen für {{job.title}}.\n\n{{application.cover_letter}}\n\nIch freue mich über Ihre Rückmeldung.\n\nFreundliche Grüße\n{{applicant.display_name}}'),
    'followup': ('Bewerbung · Nachfragen', 'Rückfrage zu meiner Bewerbung bei {{company.name}}', '{{contact.salutation}} {{contact.display_name}},\n\nich möchte freundlich nach dem Stand meiner Bewerbung fragen. Für Rückfragen stehe ich gerne zur Verfügung.\n\nFreundliche Grüße\n{{applicant.display_name}}'),
    'message': ('E-Mail · Allgemein', '{{company.name}} · Nachricht', '{{contact.salutation}} {{contact.display_name}},\n\n[Hier deinen Nachrichtentext eintragen.]\n\nFreundliche Grüße\n{{applicant.display_name}}'),
}
GRAPHS = {'basic': 'Bewerbung · E-Mail', 'pdf': 'Bewerbung · Persönliches Anschreiben als PDF', 'dated': 'Bewerbung · Datum und Festwert', 'html': 'E-Mail · HTML mit Bausteinen'}


def install_document(project, key):
    from .documents import analyze_docx
    title, filename = DOCUMENTS[key]
    path = resource_path('assets', 'templates', filename)
    names = list(analyze_docx(path).placeholders)
    return DocumentService(project).import_template(path, name=title, mapping={name: name for name in names}, required_placeholders=names)


def install_mail(project, key):
    name, subject, body = MAILS[key]
    return MailTemplateService(project.connection).save(name=name, subject=subject, body=body)


def builder_graph(key):
    if key not in GRAPHS:
        raise ValueError('Unknown built-in builder template.')
    graph = starter_graph()
    data, subject, body, mail = graph['nodes']
    data['config']['sources'] = []
    subject['config']['text'], body['config']['text'] = MAILS['application'][1:]
    def connect(a, output, b, input):
        graph['edges'].append({'from': a['id'], 'output': output, 'to': b['id'], 'input': input})
    if key == 'pdf':
        doc, replace, pdf = node('docx', 0, 350), node('replace', 300, 350), node('convert', 600, 350)
        doc['config']['path'] = str(resource_path('assets', 'templates', DOCUMENTS['cover'][1]))
        from .documents import analyze_docx
        replace['config']['rules'] = [{'find': '{{'+name+'}}', 'replacement': '', 'field': name} for name in analyze_docx(doc['config']['path']).placeholders]
        pdf['config']['filename'] = 'Anschreiben{{company.name}}.pdf'
        graph['nodes'].extend([doc, replace, pdf])
        connect(doc, 'file', replace, 'docx'); connect(data, 'values', replace, 'values')
        connect(replace, 'file', pdf, 'docx'); connect(pdf, 'file', mail, 'attachments')
    elif key == 'dated':
        date, variable = node('date', 270, 350), node('variable', 570, 350)
        variable['config'].update(field='ausbildungsbeginn', value='01.02.2027')
        graph['nodes'].extend([date, variable])
        graph['edges'] = [e for e in graph['edges'] if not (e['to'] == body['id'] and e['input'] == 'values')]
        connect(data, 'values', date, 'values'); connect(date, 'values', variable, 'values'); connect(variable, 'values', body, 'values')
        body['config']['text'] += '\n\nBewerbung vom {{datum}} · Ausbildungsbeginn {{ausbildungsbeginn}}'
    elif key == 'html':
        body['kind'] = 'paragraph'
        mail['config']['body_format'] = 'html'
        heading = node('heading', 300, 350); heading['config']['text'] = 'Bewerbung bei {{company.name}}'
        graph['nodes'].append(heading)
        connect(data, 'values', heading, 'values')
        graph['edges'].insert(0, {'from': heading['id'], 'output': 'text', 'to': mail['id'], 'input': 'body'})
    return graph
