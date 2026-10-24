"""Inventory owned captions/messages and generate the reviewed DE/EN catalog."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

GERMAN = re.compile(r'\b(Projekt|Projekte|Entwurf|Entwürfe|Auftrag|Aufträge|Versand|Vorlage|Vorlagen|Dokument|Dokumente|Baustein|Bausteine|Bitte|Keine|Kein|Nicht|Datei|Dateien|Ordner|Werte|Wert|Fehler|Abbrechen|Anhang|Anhänge|Senden|Speichern|Auswahl|Liste|Zeile|Zeilen|Eintrag|Einträge|Ausgabe|Vorschau|Quelle|Quellen|Verbindung|Konto|Konten|Signatur|Bewerbung|Bewerbungen|Feld|Felder|Fenster|Daten|Ersetzen|Neu|Zurück|Weiter|Aktualisieren|nicht|kein|keine|fehlt|fehlen|wählen|prüfen|laden|erzeugen|erstellen|ändern|löschen|erhalten|ungültig|gespeichert|verändert|benötigt|bereits|muss|darf|werden|wurde|für|mit|und|oder|nach|bei|aus|sind|ist)\b', re.I)


def owned_text(value):
    if not value or len(value) > 3000:
        return False
    if value.lstrip().upper().startswith(('SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'ALTER ', 'PRAGMA ', 'WITH ')):
        return False
    if GERMAN.search(value) or re.search('[äöüÄÖÜß]', value):
        return True
    return bool(re.fullmatch(r'[A-ZÄÖÜ][a-zäöüß]+(?: [A-Za-zÄÖÜäöüß]+)*', value))


def message_pattern(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, (), False
    if isinstance(node, ast.JoinedStr):
        parts, arguments = [], []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(part.value)
            else:
                parts.append('{' + str(len(arguments)) + '}')
                arguments.append(ast.JoinedStr(values=[part]))
        return ''.join(parts), tuple(arguments), True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts, arguments = [], []
        def visit(value):
            if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
                visit(value.left); visit(value.right)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append('{' + str(len(arguments)) + '}')
                arguments.append(value)
        visit(node)
        return ''.join(parts), tuple(arguments), True
    return None


def collect():
    items = {}
    for path in sorted((ROOT / 'src/emailcenter').rglob('*.py')):
        if path.name in {'language.py', 'language_catalog.py', 'localization.py'}:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(parents.get(node), (ast.Expr, ast.JoinedStr)):
                continue
            if isinstance(node, ast.BinOp) and isinstance(parents.get(node), ast.BinOp):
                continue
            pattern = message_pattern(node)
            if not pattern or not owned_text(pattern[0]):
                continue
            source, arguments, template = pattern
            entry = items.setdefault((source, template), {'source': source, 'template': template, 'locations': []})
            entry['locations'].append(path.relative_to(ROOT).as_posix() + ':' + str(node.lineno))
    return sorted(items.values(), key=lambda value: (not any('/ui/' in path for path in value['locations']), value['locations'][0], value['source']))


def generate():
    from emailcenter.language import TEXTS
    audit = json.loads((ROOT / 'docs/localization/Catalog_Audit.json').read_text(encoding='utf-8'))
    reviewed = json.loads((ROOT / 'docs/localization/Catalog_Review.json').read_text(encoding='utf-8'))
    texts, templates, missing = {}, {}, []
    for index, entry in enumerate(audit):
        target = reviewed.get(str(index), TEXTS.get(entry['source']))
        if target is None:
            missing.append(index); continue
        if entry['template']:
            assert sorted(re.findall(r'\{\d+\}', entry['source'])) == sorted(re.findall(r'\{\d+\}', target)), (index, entry['source'], target)
        (templates if entry['template'] else texts)[entry['source']] = target
    destination = ROOT / 'src/emailcenter/language_catalog.py'
    content = '"""Reviewed owned captions/messages; imported and editable data is unchanged."""\n'
    for name, values in (('TEXTS', texts), ('TEMPLATES', templates)):
        content += name + ' = {\n' + ''.join('    ' + repr(key) + ': ' + repr(value) + ',\n' for key, value in sorted(values.items())) + '}\n\n'
    destination.write_text(content, encoding='utf-8')
    print(f'Reviewed: {len(texts)} literals / {len(templates)} templates; outstanding: {len(missing)}.')
    return missing


if __name__ == '__main__':
    if '--generate' in sys.argv:
        generate()
    else:
        values = collect()
        # Candidate collection must not renumber the reviewed catalog.
        destination = ROOT / 'docs/localization/Catalog_Candidates.json'
        destination.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Caption/message candidates: {len(values)}; saved separately from the reviewed ledger.')
