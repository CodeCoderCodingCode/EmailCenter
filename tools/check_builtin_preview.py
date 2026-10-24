import tempfile
from pathlib import Path
from emailcenter.project import create_project
from emailcenter.builtin_templates import builder_graph
from emailcenter.email_builder import EmailBuilderService
from emailcenter.documents import analyze_docx

def diff(a,b,path=''):
    if type(a)!=type(b):print(path,type(a),type(b))
    elif isinstance(a,dict):
        for k in set(a)|set(b):diff(a.get(k),b.get(k),path+'/'+str(k))
    elif isinstance(a,list):
        for i,(x,y) in enumerate(zip(a,b)):diff(x,y,path+'/'+str(i))
    elif a!=b:print(path,repr(a),repr(b))

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
    project=create_project(Path(folder)/'project')
    try:
        graph=builder_graph('pdf')
        fields={name:'Example' for name in analyze_docx(graph['nodes'][4]['config']['path']).placeholders}
        fields['contact.email']='max@example.test'
        graph['nodes'][0]['config']['sources']=[{'kind':'manual','fields':fields}]
        service=EmailBuilderService(project)
        a=service.preview(graph)
        with service.evaluate(graph,materialize=True) as value:
            b=service.public(value)
        diff(a,b)
    finally:
        project.close()
