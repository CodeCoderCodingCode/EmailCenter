"""Administration tables and worker-backed editors."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale
import json
from PySide6.QtCore import Signal,QDateTime,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QAbstractItemView,QMessageBox,QDialog,QDialogButtonBox,QTreeWidget,QTreeWidgetItem,QHeaderView
from .pages import button,label
from .dialogs import FormDialog
from .responsive import ActionFlowLayout


class AdministrationEditor(FormDialog):
    operation_requested=Signal(str,object)
    def __init__(self,section,row=None,parent=None):
        self.section,self.record,self._busy=section,row or {},False
        specs=[('code','Statuscode','required'),('label','Bezeichnung','required'),('sort_order','Reihenfolge',None),('is_terminal','Abschlussstatus',[(_ui_tr('Nein'),False),(_ui_tr('Ja'),True)])] if section=='statuses' else [('name','Name','required'),('content_text','Signaturtext','multiline'),('content_html','HTML (optional)','multiline'),('is_default','Standardsignatur',[(_ui_tr('Nein'),False),(_ui_tr('Ja'),True)])]
        super().__init__('Status bearbeiten' if section=='statuses' else 'Signatur bearbeiten',specs,parent=parent)
        values={**self.record}
        if section=='statuses':
            values['sort_order']=str(values.get('sort_order',100))
            values['is_terminal']=bool(values.get('is_terminal',False))
        if section=='signatures':values['is_default']=bool(values.get('is_default',False))
        self.populate(values)
    def validate(self):
        if self._busy:return
        fields=self.values()
        try:
            if self.section=='statuses':
                fields['sort_order']=int(fields['sort_order'] or '100')
            else:
                fields['content_text']=fields['content_text'] or ''
                fields['content_html']=fields['content_html'] or ''
        except ValueError:
            QMessageBox.warning(self, _ui_tr('Reihenfolge'), _ui_tr('Ganze Zahl eingeben.'));return
        payload={'fields':fields,'record_id':self.record.get('id'),'expected_version':self.record.get('version')}
        self.operation_requested.emit('administration_status_save' if self.section=='statuses' else 'administration_signature_save',payload)
    def set_busy(self,busy):
        self._busy=busy
        for widget in self.fields.values():widget.setEnabled(not busy)
        self.buttons.setEnabled(not busy)
    def reject(self):
        if not self._busy:super().reject()


class AdministrationPage(QWidget):
    operation_requested=Signal(str,object)
    editor_requested=Signal(str,object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows=[];self.offset=0;self.total=0
        layout=QVBoxLayout(self)
        layout.addWidget(label(_ui_tr('Verwaltung'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Status, Signaturen, Historien, Dokumentensätze und Archiv / Papierkorb.'), 'muted'))
        filters=QHBoxLayout()
        self.section=QComboBox()
        for caption,key in [('Aktivität / Statushistorie','activity'),('Eigene Statuswerte','statuses'),('Signaturen','signatures'),('Dokumentensätze','document_sets'),('Exporthistorie','exports'),('Archiv / Papierkorb','records'),('Dateibereinigung','cleanup')]:_ui_locale.add_item(self.section, _ui_tr(caption), key)
        self.entity=QComboBox()
        for caption,key in [('Bewerbungen','applications'),('Unternehmen','companies'),('Kontakte','contacts'),('Bewerberprofile','applicants'),('Stellen','jobs'),('Dokumente','documents'),('Vorlagen','templates')]:_ui_locale.add_item(self.entity, _ui_tr(caption), key)
        self.state=QComboBox()
        for caption,key in [('Aktiv','active'),('Archiv','archived'),('Papierkorb','trash')]:_ui_locale.add_item(self.state, _ui_tr(caption), key)
        self.search=QLineEdit();_ui_locale.set_placeholder(self.search, _ui_tr('Suche · Enter'))
        for widget in (self.section,self.entity,self.state,self.search):filters.addWidget(widget)
        layout.addLayout(filters)
        self.table=QTableWidget(0,3)
        _ui_locale.headers(self.table, [_ui_tr('Bezeichnung'), 'Status / Datum', _ui_tr('Details')])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in (1,2):self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table,1)
        actions=ActionFlowLayout()
        self.controls={}
        for key,caption in [('new','Neu'),('edit','Bearbeiten'),('archive','Archivieren'),('trash','Papierkorb'),('restore','Wiederherstellen'),('purge','Endgültig löschen'),('details','Details anzeigen'),('open','Exportdatei öffnen'),('cleanup','Dateibereinigung erneut versuchen'),('previous','Zurück'),('next','Weiter'),('refresh','Aktualisieren')]:
            widget=button(caption,lambda checked=False,key=key:self.act(key));self.controls[key]=widget;actions.addWidget(widget)
        layout.addLayout(actions)
        self.summary=label('','muted');layout.addWidget(self.summary)
        for widget in (self.section,self.entity,self.state):widget.currentIndexChanged.connect(self.reload)
        self.search.returnPressed.connect(self.reload)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.update_actions()
    def query(self):
        return {'section':self.section.currentData(),'entity':self.entity.currentData(),'state':self.state.currentData(),'search':self.search.text(),'offset':self.offset,'limit':50}
    def reload(self):
        self.offset=0;self.request_load()
    def request_load(self):self.operation_requested.emit('administration_list',self.query())
    def selected(self):
        index=self.table.currentRow();return self.rows[index] if 0<=index<len(self.rows) else None
    def display(self,value):
        if any(value[key]!=self.query()[key] for key in ('section','entity','state')):return
        self.rows=value['rows'];self.total=value['total'];self.offset=value['offset']
        self.table.setRowCount(len(self.rows))
        for index,row in enumerate(self.rows):
            name=next((row[k] for k in ('label','name','title','display_name','original_filename','message','file_path') if row.get(k)),row['id'])
            detail=row.get('code') or row.get('status') or row.get('event_type') or row.get('format') or row.get('kind') or ''
            if value['section']=='activity':
                detail={'record.created':'Angelegt','record.updated':'Bearbeitet','record.archive':'Archiviert','record.trash':'Papierkorb','record.restore':'Wiederhergestellt','record.purge':'Endgültig gelöscht','application.status_changed':'Statuswechsel','signature.saved':'Signatur gespeichert','status.saved':'Status gespeichert','status.deleted':'Status gelöscht','email_sent':'Versendet','builder.batch_created':'Builder-Gruppe angelegt'}.get(row.get('event_type'),'Protokoll')
            elif value['section']=='cleanup':detail={'Pending':'Offen','Deleted':'Bereinigt','Blocked':'Gesperrt'}.get(detail,detail)
            if 'variants'in row:detail=_ui_format('{0} Dokumentvarianten', len(row['variants']))
            if value['section'] in ('activity','cleanup'):detail=_ui_tr(detail)
            stamp=row.get('created_at') or row.get('updated_at') or ''
            date=QDateTime.fromString(stamp,Qt.DateFormat.ISODateWithMs)
            shown=date.toLocalTime().toString('dd.MM.yyyy HH:mm') if date.isValid() else stamp
            for col,text in enumerate((name,shown,detail)):
                item=QTableWidgetItem(str(text));item.setToolTip(stamp if col==1 else str(text));self.table.setItem(index,col,item)
        _ui_locale.set_text(self.summary, _ui_format('{0} Einträge · Seite {1}', f'{self.total}', f'{self.offset // 50 + 1}'))
        self.update_actions()
    def update_actions(self):
        section=self.section.currentData();row=self.selected();records=section=='records'
        self.entity.setVisible(records);self.state.setVisible(records)
        for key in ('new','edit'):self.controls[key].setVisible(section in ('statuses','signatures'))
        self.controls['edit'].setEnabled(bool(row))
        for key in ('archive','trash','restore'):self.controls[key].setVisible(records)
        self.controls['archive'].setEnabled(bool(row) and self.state.currentData()=='active')
        self.controls['trash'].setEnabled(bool(row) and self.state.currentData()!='trash')
        self.controls['restore'].setEnabled(bool(row) and self.state.currentData()!='active')
        self.controls['purge'].setVisible(records or section=='statuses')
        self.controls['purge'].setEnabled(bool(row) and (section=='statuses' or self.state.currentData()=='trash'))
        self.controls['details'].setEnabled(bool(row))
        self.controls['open'].setVisible(section=='exports');self.controls['open'].setEnabled(bool(row))
        self.controls['cleanup'].setVisible(section=='cleanup');self.controls['cleanup'].setEnabled(bool(row) and row.get('status')!='Deleted')
        self.controls['previous'].setEnabled(self.offset>0)
        self.controls['next'].setEnabled(self.offset+50<self.total)
    def act(self,action):
        row=self.selected();section=self.section.currentData()
        if action in ('new','edit'):
            if action=='new' or row:self.editor_requested.emit(section,row if action=='edit' else None)
        elif action in ('refresh','previous','next'):
            if action=='previous':self.offset=max(0,self.offset-50)
            elif action=='next':self.offset+=50
            self.request_load()
        elif action=='details' and row:
            self.details_dialog(row).exec()
        elif action=='open' and row and section=='exports':
            self.operation_requested.emit('administration_export_path',{'record_id':row['id'],'expected_version':row['version']})
        elif action=='cleanup' and row and section=='cleanup':
            self.operation_requested.emit('administration_cleanup',{'record_id':row['id'],'expected_version':row['version']})
        elif row and section=='records':
            if action in ('purge','trash') and QMessageBox.question(self, _ui_tr('Löschen'), _ui_tr('Datensatz und zugehörige unverwendete Projektdateien endgültig löschen? Referenzen oder geänderte Dateien sperren das Löschen. Externe Originale und Backups bleiben erhalten. Gesperrte Dateien erscheinen in der Dateibereinigung.') if action == 'purge' else _ui_tr('Datensatz in den Papierkorb verschieben?'))!=QMessageBox.StandardButton.Yes:return
            self.operation_requested.emit('administration_lifecycle',{'entity':self.entity.currentData(),'record_id':row['id'],'action':action,'expected_version':row['version'],'confirmed':action=='purge'})
        elif row and section=='statuses' and action=='purge':
            if QMessageBox.question(self, _ui_tr('Status löschen'), _ui_tr('Unverwendeten eigenen Status löschen?'))==QMessageBox.StandardButton.Yes:
                self.operation_requested.emit('administration_status_delete',{'record_id':row['id'],'expected_version':row['version']})

    def details_dialog(self,row):
        dialog=QDialog(self);_ui_locale.set_window_title(dialog, _ui_tr('Details / Herkunft'));dialog.resize(720,520)
        layout=QVBoxLayout(dialog);tree=QTreeWidget();_ui_locale.headers(tree, [_ui_tr('Angabe'), _ui_tr('Wert')]);layout.addWidget(tree,1)
        captions={'name':'Name','title':'Titel','display_name':'Name','label':'Bezeichnung','code':'Statuscode','status':'Zustand','message':'Ereignis','created_at':'Erstellt','updated_at':'Geändert','deleted_at':'Im Papierkorb seit','details_json':'Änderungen','address_json':'Adresse','custom_fields_json':'Zusatzfelder','configuration_json':'Exportangaben','file_path':'Datei','original_filename':'Dateiname','file_size_bytes':'Dateigröße (Bytes)','row_count':'Exportierte Datensätze','kind':'Exportart','format':'Format','is_terminal':'Abschlussstatus','sort_order':'Reihenfolge','content_text':'Signaturtext','content_html':'Signatur (HTML)','last_error':'Hinweis','variants':'Dokumentvarianten','source_document_id':'Originaldokument','template_version_id':'Vorlagenversion'}
        hidden={'id','version','file_hash','content_hash','event_type','entity_type','entity_id','is_system'}
        def add(parent,key,value):
            if key in hidden or value is None:return
            if key.endswith('_json') and isinstance(value,str):
                try:value=json.loads(value)
                except ValueError:pass
            item=_ui_locale.item(QTreeWidgetItem, [_ui_tr(captions[key]) if key in captions else key.replace('_', ' ').capitalize(), '' if isinstance(value,(dict,list)) else str(value)])
            parent.addTopLevelItem(item) if isinstance(parent,QTreeWidget) else parent.addChild(item)
            if isinstance(value,dict):
                for k,v in value.items():add(item,k,v)
            elif isinstance(value,list):
                for index,v in enumerate(value,1):add(item,'Eintrag '+str(index),v)
        for key,value in row.items():add(tree,key,value)
        tree.expandAll();tree.resizeColumnToContents(0)
        if row.get('variants'):
            layout.addWidget(label(_ui_tr('Dokument öffnen · Original und Varianten')))
            choices=QComboBox()
            for variant in row['variants']:
                if not variant['deleted_at']:choices.addItem(variant['original_filename']+' · '+variant['format'].upper(),variant['id'])
            controls=QHBoxLayout();controls.addWidget(choices,1)
            controls.addWidget(button(_ui_tr('Dokument öffnen'), lambda: self.operation_requested.emit('document_path', {'document_id': choices.currentData()}) if choices.currentData() else None));layout.addLayout(controls)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dialog.reject);layout.addWidget(close)
        return dialog
