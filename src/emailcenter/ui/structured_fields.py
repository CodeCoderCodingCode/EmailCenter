"""Address inputs and typed, editable additional fields without raw JSON forms."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QComboBox
from .pages import button


class CustomFieldsEditor(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self)
        self.table=QTableWidget(0,3)
        _ui_locale.headers(self.table, [_ui_tr('Feldname'), _ui_tr('Typ'), _ui_tr('Wert')])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(160)
        layout.addWidget(self.table)
        actions=QHBoxLayout()
        actions.addWidget(button(_ui_tr('Feld hinzufügen'), self.add))
        actions.addWidget(button(_ui_tr('Feld entfernen'), self.remove))
        layout.addLayout(actions)
        self.original={}

    def add(self,key='',value=''):
        if not isinstance(key,str):
            key=''
        row=self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row,0,QTableWidgetItem(key))
        kind=QComboBox()
        for caption,code in [('Text','text'),('Zahl','number'),('Ja/Nein','bool'),('Leer','null'),('Struktur erhalten','keep')]:
            _ui_locale.add_item(kind, _ui_tr(caption), code)
        selected='bool' if type(value)is bool else 'number' if type(value)in(int,float) else 'null' if value is None else 'keep' if isinstance(value,(dict,list)) else 'text'
        kind.setCurrentIndex(kind.findData(selected))
        self.table.setCellWidget(row,1,kind)
        content=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        self.table.setItem(row,2,QTableWidgetItem(content))

    def remove(self):
        if self.table.currentRow()>=0:
            self.table.removeRow(self.table.currentRow())

    def populate(self, data):
        self.original=dict(data)
        self.table.setRowCount(0)
        for key,value in data.items():
            self.add(key,value)

    def values(self):
        result={}
        for row in range(self.table.rowCount()):
            key=self.table.item(row,0).text().strip()
            text=self.table.item(row,2).text()
            kind=self.table.cellWidget(row,1).currentData()
            if not key or key in result:
                raise ValueError(_ui_tr('Zusatzfeldnamen müssen ausgefüllt und eindeutig sein.'))
            if kind=='text': value=text
            elif kind=='number':
                try: value=json.loads(text)
                except ValueError: raise ValueError(_ui_format('Gültige Zahl für {0} eingeben.', key)) from None
                if type(value)not in(int,float): raise ValueError(_ui_format('Gültige Zahl für {0} eingeben.', key))
            elif kind=='bool':
                if text.strip().lower()not in('true','false','ja','nein'): raise ValueError(_ui_format('Ja/Nein für {0} eingeben.', key))
                value=text.strip().lower()in('true','ja')
            elif kind=='null': value=None
            else:
                if key not in self.original or text!=json.dumps(self.original[key],ensure_ascii=False):
                    raise ValueError(_ui_tr('Strukturierte Altwerte unverändert erhalten oder durch ein Textfeld ersetzen.'))
                value=self.original[key]
            result[key]=value
        return result
