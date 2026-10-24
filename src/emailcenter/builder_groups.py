"""Reusable graph selections; insertion remaps IDs and retains edge order."""

from .language import translate as _ui_tr, format_text as _ui_format
from copy import deepcopy
import json
from uuid import uuid4
from .database import utc_timestamp
from .database.repositories import _atomic
from .email_builder import validate_graph
from .record_service import fingerprint


def selection_graph(graph, selected_ids):
    validate_graph(graph,editable=True)
    if not isinstance(selected_ids,list) or not selected_ids or len(selected_ids)!=len(set(selected_ids)):
        raise ValueError(_ui_tr('Mindestens einen Baustein auswählen.'))
    result={'nodes':[deepcopy(n) for n in graph['nodes'] if n['id'] in selected_ids],
            'edges':[deepcopy(e) for e in graph['edges'] if e['from'] in selected_ids and e['to'] in selected_ids]}
    if len(result['nodes'])!=len(selected_ids):raise ValueError(_ui_tr('Auswahl enthält unbekannte Bausteine.'))
    x,y=min(n['x'] for n in result['nodes']),min(n['y'] for n in result['nodes'])
    for n in result['nodes']:
        n['x']-=x;n['y']-=y
        if n['kind']=='data':n['config']['sources']=[]
    validate_graph(result,editable=True)
    return result


def insert_group(graph, group):
    validate_graph(graph,editable=True);validate_graph(group,editable=True)
    result=deepcopy(graph);remap={n['id']:str(uuid4()) for n in group['nodes']}
    x=max(n['x']+300 for n in graph['nodes']);y=min(n['y'] for n in graph['nodes'])
    for source in group['nodes']:
        n=deepcopy(source);n['id']=remap[n['id']];n['x']+=x;n['y']+=y
        if n['kind']=='data':n['config']['sources']=[]
        result['nodes'].append(n)
    for source in group['edges']:
        e=deepcopy(source);e['from']=remap[e['from']];e['to']=remap[e['to']];result['edges'].append(e)
    validate_graph(result,editable=True)
    return result,list(remap.values())


class BuilderGroupsService:
    def __init__(self,project):self.db=project.connection
    def list(self):
        return [{**dict(row),'version':fingerprint(dict(row))} for row in self.db.execute('SELECT id,name,graph_json,created_at,updated_at FROM builder_groups ORDER BY name COLLATE NOCASE')]
    def save(self,name,graph,selected_ids,group_id=None,expected_version=None):
        if not isinstance(name,str) or not name.strip() or len(name)>200:raise ValueError(_ui_tr('Gültigen Gruppennamen eingeben.'))
        fragment=selection_graph(graph,selected_ids)
        with _atomic(self.db):
            now=utc_timestamp()
            if group_id:
                old=self.db.execute('SELECT * FROM builder_groups WHERE id=?',(group_id,)).fetchone()
                if old is None or fingerprint(dict(old))!=expected_version:raise ValueError(_ui_tr('Bausteingruppe geändert. Neu laden.'))
                self.db.execute('UPDATE builder_groups SET name=?,graph_json=?,updated_at=? WHERE id=?',(name.strip(),json.dumps(fragment,ensure_ascii=False),now,group_id))
            else:
                self.db.execute('INSERT INTO builder_groups VALUES(?,?,?,?,?)',(str(uuid4()),name.strip(),json.dumps(fragment,ensure_ascii=False),now,now))
        return self.list()
    def delete(self,group_id,expected_version):
        with _atomic(self.db):
            row=self.db.execute('SELECT * FROM builder_groups WHERE id=?',(group_id,)).fetchone()
            if row is None or fingerprint(dict(row))!=expected_version:raise ValueError(_ui_tr('Bausteingruppe geändert. Neu laden.'))
            self.db.execute('DELETE FROM builder_groups WHERE id=?',(group_id,))
        return self.list()
