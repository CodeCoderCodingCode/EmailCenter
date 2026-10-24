"""Project administration with reviewed writes and conservative deletion."""

from .language import translate as _ui_tr, format_text as _ui_format
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from .database import utc_timestamp
from .project import ProjectError
from .database.repositories import _atomic, _write_activity
from .record_service import RECORDS, fingerprint

ENTITIES = {**{key: (value[0], value[1]) for key, value in RECORDS.items()},
            'documents': ('documents', 'original_filename'), 'templates': ('templates', 'name')}


class AdministrationService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def list(self, section='activity', entity='applications', state='active', search='', offset=0, limit=50):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 10 <= limit <= 200:
            raise ValueError(_ui_tr('Ungültige Seitengröße.'))
        if section == 'records':
            table, title = self._entity(entity)
            if state not in ('active', 'archived', 'trash'):
                raise ValueError(_ui_tr('Unbekannter Zustand.'))
            condition = "c.deleted_at IS NOT NULL" if state == 'trash' else "c.deleted_at IS NULL AND " + ('' if state == 'archived' else 'NOT ') + "EXISTS(SELECT 1 FROM record_archive r WHERE r.entity_type=? AND r.entity_id=c.id)"
            args = [] if state == 'trash' else [entity]
            query = f'SELECT c.* FROM {table} c WHERE {condition}'
            if search:
                query += f" AND instr(lower(c.{title}),lower(?))>0"
                args.append(search)
            query += f' ORDER BY c.{title} COLLATE NOCASE,c.id'
        elif section in ('statuses', 'signatures', 'activity', 'exports', 'document_sets', 'cleanup'):
            table = {'statuses': 'application_statuses', 'signatures': 'email_signatures', 'activity': 'activity_log', 'exports': 'export_history', 'document_sets': 'document_sets', 'cleanup':'file_cleanup'}[section]
            title = {'statuses':'label','signatures':'name','activity':'message','exports':'file_path','document_sets':'name','cleanup':'file_path'}[section]
            query, args = f'SELECT * FROM {table} WHERE 1=1', []
            if section == 'signatures':
                query += ' AND deleted_at IS NULL'
            if search:
                searches=[f'instr(lower({title}),lower(?))>0'];args.append(search)
                if section=='activity':
                    for linked,(linked_table,linked_title) in ENTITIES.items():
                        searches.append(f"EXISTS(SELECT 1 FROM {linked_table} link WHERE activity_log.entity_type='{linked_table}' AND activity_log.entity_id=link.id AND instr(lower(link.{linked_title}),lower(?))>0)")
                        args.append(search)
                query += ' AND ('+' OR '.join(searches)+')'
            query += ' ORDER BY ' + ('sort_order,label' if section == 'statuses' else 'created_at DESC,id')
        else:
            raise ValueError(_ui_tr('Unbekannter Verwaltungsbereich.'))
        total = self.db.execute('SELECT COUNT(*) FROM (' + query + ')', args).fetchone()[0]
        rows = []
        for record in self.db.execute(query + ' LIMIT ? OFFSET ?', (*args,limit,offset)):
            row = dict(record)
            row['version'] = fingerprint(dict(record))
            if section=='activity':
                lookup={table:(table,title) for table,title in ENTITIES.values()}
                lookup.update(email_signatures=('email_signatures','name'),application_statuses=('application_statuses','label'),email_jobs=('email_jobs','subject_snapshot'),email_draft_batches=('email_draft_batches','name'))
                pair=lookup.get(row['entity_type'])
                linked=self.db.execute(f'SELECT {pair[1]} FROM {pair[0]} WHERE id=?',(row['entity_id'],)).fetchone() if pair else None
                row['entity_name']=str(linked[0]) if linked else 'Nicht mehr vorhanden / Protokolleintrag'
                row['label']=row['entity_name']+' · '+row['message']
                if row['event_type']=='application.status_changed':
                    details=json.loads(row['details_json']);row['label']=row['entity_name']+' · Status: '+str(details.get('from',''))+' → '+str(details.get('to',''))
            if section == 'document_sets':
                row['variants'] = [dict(v) for v in self.db.execute('SELECT id,original_filename,format,file_path,file_hash,source_document_id,template_version_id,deleted_at FROM documents WHERE document_set_id=? ORDER BY created_at,id',(row['id'],))]
            rows.append(row)
        return {'section':section,'entity':entity,'state':state,'rows':rows,'total':total,'offset':offset,'limit':limit}

    def _entity(self, entity):
        if entity not in ENTITIES:
            raise ValueError(_ui_tr('Unbekannter Datensatztyp.'))
        return ENTITIES[entity]

    def _review(self, table, record_id, expected_version):
        record = self.db.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone()
        if record is None or fingerprint(dict(record)) != expected_version:
            raise ValueError(_ui_tr('Datensatz geändert oder nicht vorhanden. Verwaltung aktualisieren.'))
        return dict(record)

    def lifecycle(self, entity, record_id, action, expected_version, confirmed=False):
        table, _ = self._entity(entity)
        if action not in ('archive','trash','restore','purge'):
            raise ValueError(_ui_tr('Unbekannte Archivaktion.'))
        if action == 'purge' and confirmed is not True:
            raise ValueError(_ui_tr('Endgültiges Löschen ausdrücklich bestätigen.'))
        cleanup_ids, retained = [], []
        with _atomic(self.db):
            row = self._review(table,record_id,expected_version)
            now = utc_timestamp()
            if action == 'archive':
                if row['deleted_at']:
                    raise ValueError(_ui_tr('Zuerst aus Papierkorb wiederherstellen.'))
                self.db.execute('INSERT OR IGNORE INTO record_archive VALUES(?,?,?)',(entity,record_id,now))
                self.db.execute(f'UPDATE {table} SET updated_at=? WHERE id=?',(now,record_id))
            elif action == 'trash':
                if entity == 'applications' and self.db.execute("SELECT 1 FROM email_jobs WHERE application_id=? AND status IN ('Sending','Scheduled','Queued')",(record_id,)).fetchone():
                    raise ValueError(_ui_tr('Offene Versandaufträge zuerst pausieren/stornieren.'))
                self.db.execute(f'UPDATE {table} SET deleted_at=?,updated_at=? WHERE id=?',(now,now,record_id))
            elif action == 'restore':
                self.db.execute(f'UPDATE {table} SET deleted_at=NULL,updated_at=? WHERE id=?',(now,record_id))
                self.db.execute('DELETE FROM record_archive WHERE entity_type=? AND entity_id=?',(entity,record_id))
            else:
                if not row['deleted_at']:
                    raise ValueError(_ui_tr('Vor endgültigem Löschen in den Papierkorb verschieben.'))
                versions = [v[0] for v in self.db.execute('SELECT id FROM template_versions WHERE template_id=?',(record_id,))] if entity == 'templates' else []
                for version in versions:
                    self._require_unreferenced('template_versions',version)
                self._require_unreferenced(table,record_id,ignore=('template_versions',) if entity == 'templates' else ())
                candidates = [dict(v) for v in self.db.execute('SELECT file_path,content_hash AS file_hash FROM template_versions WHERE template_id=?',(record_id,))] if entity == 'templates' else [row] if entity == 'documents' else []
                self._require_json_unreferenced([record_id,*versions], [v.get('file_path') for v in candidates], table,record_id,versions)
                for candidate in candidates:
                    relative = candidate.get('file_path')
                    if not relative:
                        continue
                    try:
                        target = self.project.file_path(relative)
                    except (ValueError,ProjectError):
                        retained.append(relative)
                        continue
                    if target.relative_to(self.project.path.resolve()).parts[0] not in ('documents','templates','exports'):
                        retained.append(relative)
                        continue
                    if target.exists():
                        if not target.is_file() or not candidate.get('file_hash') or self._file_hash(target) != candidate['file_hash']:
                            raise ValueError(_ui_tr('Datei verändert oder Prüfsumme fehlt. Endgültiges Löschen wurde gesperrt.'))
                        identifier = str(uuid4())
                        self.db.execute('INSERT INTO file_cleanup VALUES(?,?,?,\'Pending\',NULL,?,?)',(identifier,relative,candidate['file_hash'],now,now))
                        cleanup_ids.append(identifier)
                if versions:
                    self.db.execute('DELETE FROM template_versions WHERE template_id=?',(record_id,))
                self.db.execute(f'DELETE FROM {table} WHERE id=?',(record_id,))
                self.db.execute('DELETE FROM record_archive WHERE entity_type=? AND entity_id=?',(entity,record_id))
            _write_activity(self.db,'record.'+action,table,record_id,'Archivaktion: '+action,{'retained_files':len(retained)},now)
        cleanup = [self.cleanup(identifier) for identifier in cleanup_ids]
        return {'entity':entity,'action':action,'record_id':record_id,'files_retained':bool(retained),'cleanup':cleanup,'retained_files':retained}

    @staticmethod
    def _file_hash(path):
        result = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                result.update(block)
        return result.hexdigest()

    def _require_json_unreferenced(self, identifiers, paths, own_table=None, own_id=None, versions=()):
        needles = {str(value).replace('\\','/').casefold() for value in identifiers if value}
        for value in paths:
            if value:
                needles.add(str(value).replace('\\','/').casefold())
                try:
                    needles.add(str(self.project.file_path(value)).replace('\\','/').casefold())
                except (ValueError,ProjectError):
                    pass
        def references(value):
            if isinstance(value,str):return value.replace('\\','/').casefold() in needles
            if isinstance(value,dict):return any(references(v) for v in value.values())
            if isinstance(value,list):return any(references(v) for v in value)
            return False
        for item in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            table = item[0]
            if not re.fullmatch(r'[a-z_]+',table) or table in ('activity_log','export_history','file_cleanup'):
                continue
            columns = [r['name'] for r in self.db.execute(f'PRAGMA table_info({table})') if r['name'].endswith('_json')]
            if not columns:
                continue
            for row in self.db.execute(f'SELECT * FROM {table}'):
                if 'id' in row.keys() and ((table==own_table and row['id']==own_id) or (table=='template_versions' and row['id'] in versions)):
                    continue
                for column in columns:
                    try:value=json.loads(row[column] or '{}')
                    except (ValueError,TypeError):
                        raise ValueError(_ui_format('Nicht lesbare Referenzen in {0}. Löschen gesperrt.', table))
                    if references(value):
                        raise ValueError(_ui_format('Datensatz/Datei wird noch verwendet ({0}). Zuordnung zuerst lösen.', table))

    def cleanup(self, record_id, expected_version=None):
        with _atomic(self.db):
            if expected_version:
                row = self._review('file_cleanup',record_id,expected_version)
            else:
                current=self.db.execute('SELECT * FROM file_cleanup WHERE id=?',(record_id,)).fetchone()
                if current is None:raise ValueError(_ui_tr('Dateibereinigung nicht gefunden.'))
                row=dict(current)
            if row['status']=='Deleted':return row
            try:
                path = self.project.file_path(row['file_path'])
                if path.relative_to(self.project.path.resolve()).parts[0] not in ('documents','templates','exports'):
                    raise ValueError(_ui_tr('Datei gehört nicht zu einem verwalteten Dokumentordner.'))
                for table,column in (('documents','file_path'),('template_versions','file_path'),('email_attachments','file_path_snapshot')):
                    if self.db.execute(f'SELECT 1 FROM {table} WHERE {column}=?',(row['file_path'],)).fetchone():
                        raise ValueError(_ui_tr('Datei wurde zwischenzeitlich erneut zugeordnet.'))
                self._require_json_unreferenced([], [row['file_path']])
                if path.exists():
                    if not path.is_file() or self._file_hash(path)!=row['file_hash']:
                        raise ValueError(_ui_tr('Datei wurde verändert; sie bleibt erhalten.'))
                    path.unlink()
                status,error='Deleted',None
            except (OSError,ValueError,ProjectError) as failure:
                status,error='Blocked',str(failure)
            self.db.execute('UPDATE file_cleanup SET status=?,last_error=?,updated_at=? WHERE id=?',(status,error,utc_timestamp(),record_id))
        return dict(self.db.execute('SELECT * FROM file_cleanup WHERE id=?',(record_id,)).fetchone())

    def _require_unreferenced(self, table, identifier, ignore=()):
        for item in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            child = item[0]
            if child in ignore or not re.fullmatch(r'[a-z_]+',child):
                continue
            for fk in self.db.execute(f'PRAGMA foreign_key_list({child})').fetchall():
                if fk['table'] == table and self.db.execute(f'SELECT 1 FROM {child} WHERE "{fk["from"]}"=? LIMIT 1',(identifier,)).fetchone():
                    raise ValueError(_ui_format('Datensatz wird noch verwendet ({0}). Zuordnungen zuerst lösen; Archivieren bleibt möglich.', child))

    def save_status(self, fields, record_id=None, expected_version=None):
        code, label = str(fields.get('code','')).strip(), str(fields.get('label','')).strip()
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',code) or not label or len(label)>100:
            raise ValueError(_ui_tr('Gültigen Statuscode und Bezeichnung eingeben.'))
        order = fields.get('sort_order',100)
        terminal = fields.get('is_terminal',False)
        if type(order) is not int or not -10000 <= order <= 10000 or type(terminal) is not bool:
            raise ValueError(_ui_tr('Ungültige Statusreihenfolge oder Abschlussregel.'))
        with _atomic(self.db):
            now = utc_timestamp()
            if record_id:
                row = self._review('application_statuses',record_id,expected_version)
                used = self.db.execute('SELECT 1 FROM applications WHERE status_id=?',(record_id,)).fetchone()
                if (row['is_system'] or used) and (code != row['code'] or terminal != bool(row['is_terminal'])):
                    raise ValueError(_ui_tr('System-/verwendete Statusregeln bleiben fest; Bezeichnung und Reihenfolge sind bearbeitbar.'))
                self.db.execute('UPDATE application_statuses SET code=?,label=?,sort_order=?,is_terminal=? WHERE id=?',(code,label,order,int(terminal),record_id))
            else:
                record_id = str(uuid4())
                self.db.execute('INSERT INTO application_statuses(id,code,label,sort_order,is_system,is_terminal,created_at) VALUES(?,?,?,?,0,?,?)',(record_id,code,label,order,int(terminal),now))
            _write_activity(self.db,'status.saved','application_statuses',record_id,'Statusverwaltung gespeichert.',{},now)
        return {'id':record_id}

    def delete_status(self, record_id, expected_version):
        with _atomic(self.db):
            row = self._review('application_statuses',record_id,expected_version)
            if row['is_system']:
                raise ValueError(_ui_tr('Systemstatus kann nicht gelöscht werden.'))
            self._require_unreferenced('application_statuses',record_id)
            self.db.execute('DELETE FROM application_statuses WHERE id=?',(record_id,))
            _write_activity(self.db,'status.deleted','application_statuses',record_id,'Eigener Status gelöscht.',{},utc_timestamp())
        return {'id':record_id}

    def export_path(self,record_id,expected_version):
        row=self._review('export_history',record_id,expected_version)
        path=Path(row['file_path'])
        if not path.is_absolute() or not path.is_file() or self._file_hash(path)!=row['file_hash']:
            raise ValueError(_ui_tr('Exportdatei fehlt oder wurde verändert.'))
        return {'path':str(path)}

    def log_export(self, kind, result, configuration=None):
        path = Path(result['path'])
        identifier = str(uuid4())
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                h.update(block)
        self.db.execute('INSERT INTO export_history VALUES(?,?,?,?,?,?,?,?)',(identifier,kind,str(path),h.hexdigest(),path.stat().st_size,result.get('count',0),json.dumps(configuration or {},ensure_ascii=False),utc_timestamp()))
        return identifier
