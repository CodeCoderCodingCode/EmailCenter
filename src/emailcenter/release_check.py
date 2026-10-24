"""Offline packaged application check; never connects or sends to a provider."""
from pathlib import Path
import json
import tempfile
from .resources import resource_path, shared_oauth_client
from .project import create_project
from .builtin_templates import builder_graph, install_document, install_mail
from .email_builder import EmailBuilderService
from .document_service import find_libreoffice
from .gmail import load_desktop_client


def check(output):
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    report = {'success': False, 'network_calls': 0}
    try:
        with tempfile.TemporaryDirectory(prefix='release-check-', dir=target.parent) as folder:
            project = create_project(Path(folder)/'project', name='Offline Release Check')
            try:
                for key in ('cover', 'cover-job', 'cv'):
                    install_document(project, key)
                for key in ('application', 'followup', 'message'):
                    install_mail(project, key)
                graph = builder_graph('pdf')
                fields = {'contact.display_name':'Max Mustermann','contact.salutation':'Sehr geehrter Herr','contact.email':'max@example.test',
                          'company.name':'Musterfirma','company.address':'Musterstraße 1\n12345 Musterstadt','job.title':'Fachinformatiker',
                          'applicant.display_name':'Erika Beispiel','applicant.address':'Beispielweg 2','applicant.email':'erika@example.test','applicant.phone':'01234 000000',
                          'application.cover_letter':'Dies ist ein vollständig lokaler Test mit erfundenen Daten.','application.date':'01.02.2027'}
                graph['nodes'][0]['config']['sources'] = [{'kind':'manual','fields':fields}]
                service = EmailBuilderService(project)
                preview = service.preview(graph)
                if not preview['ready']:
                    raise RuntimeError(str(preview['rows']))
                batch = service.create('Lokaler Test', graph, preview['fingerprint'])['batch']
                import pdfplumber
                documents = project.connection.execute("SELECT file_path FROM documents WHERE format='pdf'").fetchall()
                if not documents:
                    raise RuntimeError('Generated PDF missing.')
                with pdfplumber.open(project.file_path(documents[0]['file_path'])) as pdf:
                    text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
                    if '{{' in text or 'Musterfirma' not in text:
                        raise RuntimeError('PDF personalization failed.')
                    report['pdf_pages'] = len(pdf.pages)
                report['local_drafts'] = len(batch['items'])
                report['database_integrity'] = project.connection.execute('PRAGMA integrity_check').fetchone()[0]
                report['schema'] = project.connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
                client = shared_oauth_client()
                report['shared_client'] = bool(client)
                if client:
                    load_desktop_client(client)
                report['converter'] = bool(find_libreoffice())
                report['guide'] = resource_path('guide','EmailCenter_Guide.html').is_file()
                report['logo'] = resource_path('assets','Logo256.png').is_file()
                if not all(report[k] for k in ('converter','guide','logo','shared_client')):
                    raise RuntimeError('Missing release resource.')
                report['success'] = True
            finally:
                project.close()
    except Exception as error:
        report['error'] = str(error)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['success'] else 1
