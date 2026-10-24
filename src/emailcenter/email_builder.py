"""Typed email graphs, immutable versions and reviewed local draft groups."""

from .language import translate as _ui_tr, format_text as _ui_format

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import html
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from .bulk_sources import BulkSourceService, text_values
from .bulk_delivery import BulkDeliveryService
from .database import utc_timestamp, DocumentRepository
from .database.repositories import _write_activity
from .document_service import convert_docx_to_pdf, find_libreoffice, DocumentServiceError
from .documents import analyze_docx, extract_docx_text, DocumentError
from .mail_bulk import BulkMailService, digest
from .mail_models import MailError, address, header
from .mail_service import MailService, _json, _transaction
from .mail_templates import _hash as template_hash
from .builder_values import TOKEN, placeholders, FieldValues, VALUE_CONFIGS, validate_value_config, frozen_clock, value_output, clean_text
from .word_replace import WordRuleError, file_hash, replace_docx, validate_source, validate_rules
from .builder_pdf_names import filename_fields, pdf_filename


# Inputs: (accepted types, required, multiple). Edge order defines body/attachment order.
NODE_TYPES = {
    "data": {"title": "Excel / Datenliste", "inputs": {}, "outputs": {"values": "fields", "email": "recipient"}},
    "text": {"title": "Text (universell)", "inputs": {"values": (("fields",), False, False)}, "outputs": {"text": "text"}},
    **{kind: {"title": title, "inputs": {"values": (("fields",), False, False)}, "outputs": {"text": output}}
       for kind, title, output in (("subject", "Betreff", "subject"), ("description", "Beschreibung / Anschreiben", "text"),
          ("paragraph", "Absatz", "text"), ("heading", "Überschrift", "text"), ("html", "HTML-Inhalt", "html"),
          ("greeting", "Anrede", "text"), ("closing", "Gruß / Signaturtext", "text"), ("separator", "Trennlinie", "text"))},
    **{kind: {"title": title, "inputs": {"values": (("fields",), False, False)}, "outputs": {"text": "text"}}
       for kind, title in (("link", "Link"), ("button", "Button / Handlungslink"), ("list", "Liste / Aufzählung"))},
    "recipient": {"title": "Empfänger", "inputs": {"values": (("fields",), False, False)}, "outputs": {"email": "recipient"}},
    "condition": {"title": "Bedingung / Textwahl", "inputs": {"values": (("fields",), True, False), "yes": (("text", "subject", "html"), False, False), "no": (("text", "subject", "html"), False, False)}, "outputs": {"text": "text"}},
    "merge": {"title": "Texte zusammenführen", "inputs": {"parts": (("text", "subject", "html"), True, True)}, "outputs": {"text": "text"}},
    "docx": {"title": "DOCX", "inputs": {}, "outputs": {"file": "docx"}},
    "pdf": {"title": "PDF-Datei", "inputs": {}, "outputs": {"file": "pdf"}},
    "image": {"title": "Bild-Anhang", "inputs": {}, "outputs": {"file": "image"}},
    "video": {"title": "Video-Anhang", "inputs": {}, "outputs": {"file": "video"}},
    "file": {"title": "Datei-Anhang", "inputs": {}, "outputs": {"file": "file"}},
    "replace": {"title": "Word Replace", "inputs": {"docx": (("docx",), True, False), "values": (("fields",), False, False)}, "outputs": {"file": "docx"}},
    "convert": {"title": "DOCX → PDF", "inputs": {"docx": (("docx",), True, False)}, "outputs": {"file": "pdf"}},
    "email": {"title": "E-Mail / Bulk-Ausgabe", "inputs": {"recipient": (("recipient",), True, False), "subject": (("text", "subject"), True, False),
        "body": (("text", "html"), True, True), "attachments": (("file", "docx", "pdf", "image", "video"), False, True)}, "outputs": {}},
}
TEXT_KINDS = ("text", "subject", "description", "paragraph", "heading", "html", "greeting", "closing", "separator", "link", "button", "list")
NODE_TYPES['inline_image'] = {'title':'Inline-Bild','inputs':{'values':(('fields',),False,False)},'outputs':{'file':'image','text':'html'}}
NODE_TYPES['attachment'] = {'title':'Anhang benennen','inputs':{'file':(('file','docx','pdf','image','video'),True,False),'values':(('fields',),False,False)},'outputs':{'file':'file'}}
for _kind, _title in (('date', 'Datum'), ('time', 'Uhrzeit'), ('variable', 'Variable / Festwert')):
    NODE_TYPES[_kind] = {'title': _title, 'inputs': {'values': (('fields',), False, False)}, 'outputs': {'values': 'fields', 'text': 'text'}}
NODE_TYPES['clean'] = {'title': 'Text bereinigen', 'inputs': {'text': (('text', 'subject'), True, False)}, 'outputs': {'text': 'text'}}
FILE_KINDS = ("docx", "pdf", "image", "video", "file", "inline_image")
CONDITION_OPERATORS = {"equals": "Ist gleich", "not_equals": "Ist ungleich", "contains": "Enthält", "empty": "Ist leer", "not_empty": "Ist ausgefüllt"}
for _kind in FILE_KINDS:
    NODE_TYPES[_kind]["inputs"] = {"values": (("fields",), False, False)}
EXTENSIONS = {"docx": (".docx",), "pdf": (".pdf",), "image": (".png", ".jpg", ".jpeg", ".gif", ".webp"),
              "video": (".mp4", ".webm", ".mov", ".avi")}
EXTENSIONS['inline_image'] = EXTENSIONS['image']


def node(kind, x=0, y=0):
    configs = {"data": {"sources": [], "allow_duplicate_recipients": False}, "text": {"text": ""}, "recipient": {"text": ""},
        **{kind: {"text": "---" if kind == "separator" else ""} for kind in TEXT_KINDS},
        "link": {"text": "Mehr erfahren", "url": "https://"}, "button": {"text": "Dokument ansehen", "url": "https://"}, "list": {"text": "", "ordered": False},
        **{kind: {"path": ""} for kind in FILE_KINDS},
        'inline_image': {'path':'','alt':'Bild','width':600}, 'attachment': {'filename':'{{company.name}}.pdf'},
        "replace": {"rules": [], "case_sensitive": True, "whole_words": False}, "convert": {'filename': ''}, "email": {"body_format": "plain"},
        "condition": {"field": "contact.display_name", "operator": "not_empty", "compare": "", "case_sensitive": False, "yes": "", "no": ""}, "merge": {"separator": "\n\n"}}
    configs.update(VALUE_CONFIGS)
    return {"id": str(uuid4()), "kind": kind, "x": x, "y": y, "config": deepcopy(configs[kind])}


def starter_graph(blocks=None):
    if blocks is not None and blocks != ["text"]:
        graph = starter_graph()
        source, subject, original, sink = graph["nodes"]
        bodies = [node(kind, 320, 220 + index * 190) for index, kind in enumerate(blocks)]
        for body in bodies:
            if body["kind"] in ("text", "description", "paragraph", "html", "list"):
                body["config"]["text"] = "{{application.cover_letter}}"
            elif body["kind"] == "greeting":
                body["config"]["text"] = "Guten Tag {{contact.display_name}},"
            elif body["kind"] == "closing":
                body["config"]["text"] = "Mit freundlichen Grüßen"
            elif body["kind"] == "heading":
                body["config"]["text"] = "Bewerbung bei {{company.name}}"
        graph["nodes"] = [source, subject, *bodies, sink]
        graph["edges"] = [edge for edge in graph["edges"] if original["id"] not in (edge["from"], edge["to"])]
        for body in bodies:
            graph["edges"].extend([{"from": source["id"], "output": "values", "to": body["id"], "input": "values"}, {"from": body["id"], "output": "text", "to": sink["id"], "input": "body"}])
        return graph
    nodes = [node("data", 0, 40), node("subject", 320, 0), node("text", 320, 230), node("email", 670, 80)]
    nodes[1]["config"]["text"] = "Bewerbung bei {{company.name}}"
    nodes[2]["config"]["text"] = "Guten Tag {{contact.display_name}},\n\n{{application.cover_letter}}"
    def edge(a, port, b, target):
        return {"from": nodes[a]["id"], "output": port, "to": nodes[b]["id"], "input": target}
    return {"nodes": nodes, "edges": [edge(0, "values", 1, "values"), edge(0, "values", 2, "values"),
        edge(0, "email", 3, "recipient"), edge(1, "text", 3, "subject"), edge(2, "text", 3, "body")]}


def validate_graph(graph, *, complete=False, editable=False):
    """Incomplete drafts are saveable; malformed/ambiguous/cyclic graphs never are."""
    if not isinstance(graph, dict) or set(graph) != {"nodes", "edges"} or not isinstance(graph["nodes"], list) or not isinstance(graph["edges"], list):
        raise MailError(_ui_tr('Ungültiger Builder-Graph.'))
    if not 1 <= len(graph["nodes"]) <= 100 or len(graph["edges"]) > 400:
        raise MailError(_ui_tr('1 bis 100 Bausteine und höchstens 400 Verbindungen verwenden.'))
    if len(_json(graph)) > 2_000_000:
        raise MailError(_ui_tr('Builder-Graph ist zu groß (maximal 2 MB Text).'))
    nodes, incoming, outgoing = {}, {}, {}
    for node_number, item in enumerate(graph["nodes"], 1):
        if not isinstance(item, dict) or set(item) != {"id", "kind", "x", "y", "config"}:
            raise MailError(_ui_tr('Ungültiger Baustein.'))
        identifier, kind, config = item["id"], item["kind"], item["config"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier) or identifier in nodes or not isinstance(kind, str) or kind not in NODE_TYPES or not isinstance(config, dict):
            raise MailError(_ui_tr('Baustein-ID oder Typ ist ungültig bzw. doppelt.'))
        if any(type(item[axis]) not in (int, float) or not math.isfinite(item[axis]) or abs(item[axis]) > 100000 for axis in ("x", "y")):
            raise MailError(_ui_tr('Ungültige Bausteinposition.'))
        keys = set(node(kind)["config"])
        if kind == 'data' and 'allow_duplicate_recipients' not in config:
            keys.remove('allow_duplicate_recipients')  # Existing saved graphs remain valid.
        if kind == 'convert' and 'filename' not in config:
            keys.remove('filename')  # Old graph versions keep the original document name.
        if set(config) != keys:
            raise MailError(_ui_format('Ungültige Bausteineigenschaften: {0}', _ui_tr(NODE_TYPES[kind]['title'])))
        if kind in VALUE_CONFIGS:
            validate_value_config(kind, config, editable=editable)
        elif kind == "data":
            if type(config.get('allow_duplicate_recipients', False)) is not bool:
                raise MailError('Repeated-recipient choice must be a boolean.')
            if not isinstance(config["sources"], list) or len(config["sources"]) > 100 or any(not isinstance(s, dict) for s in config["sources"]):
                raise MailError(_ui_tr('Höchstens 100 Datenzeilen auswählen.'))
        elif kind in (*TEXT_KINDS, "recipient"):
            if not isinstance(config["text"], str) or len(config["text"]) > 100000 or "\x00" in config["text"]:
                raise MailError(_ui_tr('Bausteintext ist ungültig oder zu lang.'))
            if not editable:
                placeholders("", config["text"])
            if kind in ("link", "button"):
                if not isinstance(config["url"], str) or len(config["url"]) > 2048 or any(c in config["url"] for c in "\x00\r\n"):
                    raise MailError(_ui_tr('Ungültiges Linkziel.'))
                if not editable:
                    placeholders("", config["url"])
            if kind == "list" and type(config["ordered"]) is not bool:
                raise MailError(_ui_tr('Ungültige Listenart.'))
        elif kind == "condition":
            if any(not isinstance(config[key], str) or len(config[key]) > 100000 or "\x00" in config[key] for key in ("field", "operator", "compare", "yes", "no")) or type(config["case_sensitive"]) is not bool or config["operator"] not in CONDITION_OPERATORS:
                raise MailError(_ui_tr('Ungültige Textbedingung.'))
            if not editable:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,199}", config["field"]):
                    raise MailError(_ui_tr('Gültigen Datenfeldnamen für die Bedingung wählen.'))
                placeholders("", config["yes"])
                placeholders("", config["no"])
        elif kind == "merge":
            if not isinstance(config["separator"], str) or len(config["separator"]) > 1000 or "\x00" in config["separator"]:
                raise MailError(_ui_tr('Trenntext ist ungültig oder zu lang.'))
        elif kind in FILE_KINDS:
            if not isinstance(config["path"], str) or len(config["path"]) > 2048 or any(c in config["path"] for c in "\x00\n\r"):
                raise MailError(_ui_tr('Ungültiger Dateipfad.'))
            if kind == 'inline_image' and (not isinstance(config['alt'],str) or len(config['alt'])>1000 or '\x00' in config['alt'] or type(config['width'])is not int or not 1<=config['width']<=1200):
                raise MailError(_ui_tr('Ungültige Bildbeschreibung oder Breite (1–1200).'))
        elif kind == 'attachment':
            if not isinstance(config['filename'],str) or len(config['filename'])>250 or any(c in config['filename'] for c in '\x00\r\n'):
                raise MailError(_ui_tr('Gültigen persönlichen Anhangnamen eingeben.'))
            if not editable:placeholders('',config['filename'])
        elif kind == "replace":
            if type(config["whole_words"]) is not bool or type(config["case_sensitive"]) is not bool or not isinstance(config["rules"], list):
                raise MailError(_ui_tr('Ungültige Ersetzungseinstellungen.'))
            if not editable and (config["rules"] or complete):
                try:
                    validate_rules(config["rules"], config["case_sensitive"])
                except WordRuleError as error:
                    error.builder_node_id = identifier
                    error.args = (_ui_format('Baustein {0}: {1}', node_number, error.args[0]),)
                    raise
        elif kind == 'convert':
            pattern = config.get('filename', '')
            if not isinstance(pattern, str) or len(pattern) > 250 or any(c in pattern for c in '\x00\r\n'):
                raise MailError(_ui_tr('PDF-Dateinamensmuster ist ungültig (maximal 250 Zeichen, keine Zeilenumbrüche).'))
            if not editable:
                filename_fields(pattern)
        elif kind == "email" and config["body_format"] not in ("plain", "html"):
            raise MailError(_ui_tr('Nachrichtenformat plain/html wählen.'))
        nodes[identifier], incoming[identifier], outgoing[identifier] = item, [], []
    seen, inputs = set(), {}
    for edge in graph["edges"]:
        if not isinstance(edge, dict) or set(edge) != {"from", "output", "to", "input"} or any(not isinstance(v, str) for v in edge.values()):
            raise MailError(_ui_tr('Ungültige Verbindung.'))
        if edge["from"] not in nodes or edge["to"] not in nodes:
            raise MailError(_ui_tr('Verbindung zeigt auf fehlenden Baustein.'))
        origin, target = NODE_TYPES[nodes[edge["from"]]["kind"]], NODE_TYPES[nodes[edge["to"]]["kind"]]
        spec = target["inputs"].get(edge["input"])
        if edge["output"] not in origin["outputs"] or not spec or origin["outputs"][edge["output"]] not in spec[0]:
            raise MailError(_ui_tr('Unpassende Stecker: Ausgang und Eingang besitzen unterschiedliche Typen.'))
        key, endpoint = tuple(edge[k] for k in ("from", "output", "to", "input")), (edge["to"], edge["input"])
        if key in seen or (endpoint in inputs and not spec[2]):
            raise MailError(_ui_tr('Verbindung doppelt oder Eingang bereits belegt.'))
        seen.add(key)
        inputs[endpoint] = True
        incoming[edge["to"]].append(edge)
        outgoing[edge["from"]].append(edge)
    degree = {key: len(value) for key, value in incoming.items()}
    queue, order = [key for key in nodes if not degree[key]], []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for edge in outgoing[current]:
            degree[edge["to"]] -= 1
            if not degree[edge["to"]]:
                queue.append(edge["to"])
    if len(order) != len(nodes):
        raise MailError(_ui_tr('Zyklische Verbindungen sind nicht erlaubt.'))
    if sum(n["kind"] == "data" for n in nodes.values()) > 1 or sum(n["kind"] == "email" for n in nodes.values()) > 1:
        raise MailError(_ui_tr('Je Graph höchstens einen Daten- und einen E-Mail-Baustein verwenden.'))
    if complete:
        emails = [n for n in nodes.values() if n["kind"] == "email"]
        if not emails:
            raise MailError(_ui_tr('Einen E-Mail-Ausgang hinzufügen.'))
        active, queue = set(), [emails[0]["id"]]
        while queue:
            current = queue.pop()
            if current not in active:
                active.add(current)
                queue.extend(e["from"] for e in incoming[current])
        if active != set(nodes):
            raise MailError(_ui_tr('Unverbundene Bausteine verbinden oder entfernen; die Vorschau wertet den gesamten Graphen aus.'))
        for identifier, item in nodes.items():
            for port, (_, required, _) in NODE_TYPES[item["kind"]]["inputs"].items():
                if required and (identifier, port) not in inputs:
                    raise MailError(_ui_format('{0}: Eingang „{1}“ fehlt.', _ui_tr(NODE_TYPES[item['kind']]['title']), port))
    return nodes, incoming, order


def render_text(text, fields, *, escape=False):
    missing = [name for name in placeholders("", text) if not fields.get(name, "").strip()]
    if missing:
        raise MailError(_ui_format('Fehlende Datenfelder: {0}', ', '.join(missing)))
    return TOKEN.sub(lambda match: html.escape(fields[match.group(1)], quote=True) if escape else fields[match.group(1)], text)


def source_file(path, kind):
    source = Path(path).expanduser()
    if not source.is_absolute() or not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
        raise MailError(_ui_tr('Eine vorhandene Datei mit absolutem Pfad bis 20 MiB wählen.'))
    source = source.resolve()
    if kind in EXTENSIONS and source.suffix.lower() not in EXTENSIONS[kind]:
        raise MailError(_ui_format('Dateityp passt nicht zum Baustein „{0}“.', _ui_tr(NODE_TYPES[kind]['title'])))
    if kind == "docx":
        validate_source(source)
    with source.open("rb") as stream:
        prefix = stream.read(16)
    if kind == "pdf" and not prefix[:5] == b"%PDF-":
        raise MailError(_ui_tr('Datei enthält keinen PDF-Kopf.'))
    if kind in ("image","inline_image") and not (prefix.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")) or prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP"):
        raise MailError(_ui_tr('Bilddatei besitzt keinen unterstützten Bildkopf.'))
    if kind == "video" and not (prefix[:4] == b"\x1aE\xdf\xa3" or prefix[:4] == b"RIFF" and prefix[8:12] == b"AVI " or prefix[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free")):
        raise MailError(_ui_tr('Videodatei besitzt keinen unterstützten Videokopf.'))
    return {"path": str(source), "filename": source.name, "size": source.stat().st_size, "hash": file_hash(source), "format": "image" if kind == "inline_image" else kind, "generated": False}


def body_part(text, fields, kind, body_format, options=None):
    if kind == 'literal':
        return html.escape(text, quote=True).replace('\n', '<br>') if body_format == 'html' else text
    if kind == 'inline_image':
        if body_format != 'html':
            raise MailError(_ui_tr('Inline-Bilder benötigen HTML im E-Mail-Baustein.'))
        alt=html.escape(render_text(options['alt'],fields),quote=True)
        return f'<img src="cid:{options["cid"]}" alt="{alt}" width="{options["width"]}" style="max-width:100%;height:auto">'
    options = options or {}
    if kind == "merge":
        separator = options["separator"]
        if body_format == "html":
            separator = html.escape(separator).replace("\n", "<br>")
        return separator.join(body_part(t, f, k, body_format, o) for t, f, k, o in options["parts"])
    if kind in ("link", "button"):
        url = render_text(options["url"], fields)
        parsed = urlsplit(url)
        try:
            parsed.port
        except ValueError:
            raise MailError(_ui_tr('Linkziel enthält einen ungültigen Port.')) from None
        if any(c.isspace() or ord(c) < 32 for c in url) or not ((parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password) or (parsed.scheme == "mailto" and not parsed.query and address(parsed.path))):
            raise MailError(_ui_tr('Linkziel benötigt eine vollständige HTTP(S)-Adresse oder mailto:E-Mail, ohne Zugangsdaten/Leerzeichen.'))
        label_text = render_text(text, fields)
        if not label_text.strip():
            raise MailError(_ui_tr('Linkbeschriftung fehlt.'))
        if body_format == "plain":
            return label_text + " (" + url + ")"
        style = ' style="display:inline-block;background:#2862c4;color:#ffffff;padding:10px 16px;border-radius:6px;text-decoration:none"' if kind == "button" else ""
        return '<a href="' + html.escape(url, quote=True) + '"' + style + '>' + html.escape(label_text) + "</a>"
    if kind == "list":
        items = [line.strip() for line in render_text(text, fields).splitlines() if line.strip()]
        if not items:
            raise MailError(_ui_tr('Liste benötigt mindestens einen Eintrag pro Zeile.'))
        if body_format == "plain":
            return "\n".join((str(index) + ". " if options["ordered"] else "• ") + item for index, item in enumerate(items, 1))
        tag = "ol" if options["ordered"] else "ul"
        return "<" + tag + ">" + "".join("<li>" + html.escape(item) + "</li>" for item in items) + "</" + tag + ">"
    if kind == "html" and body_format != "html":
        raise MailError(_ui_tr('HTML-Inhalt benötigt HTML als Format im E-Mail-Baustein.'))
    if body_format == "plain":
        return render_text(text, fields)
    rendered = render_text(text, fields, escape=True)
    # Existing universal text retains its HTML semantics for saved graphs.
    if kind in ("html", "text"):
        return rendered
    if kind == "separator":
        return "<hr>"
    rendered = html.escape(render_text(text, fields)).replace("\n", "<br>")
    return "<h2>" + rendered + "</h2>" if kind == "heading" else rendered


def condition_matches(configuration, fields):
    field, operator = configuration["field"], configuration["operator"]
    actual = fields.get(field, "")
    if operator == "empty":
        return not actual.strip()
    if operator == "not_empty":
        return bool(actual.strip())
    if field not in fields:
        raise MailError(_ui_format('Datenfeld der Bedingung fehlt: {0}', field))
    compare = configuration["compare"]
    if not configuration["case_sensitive"]:
        actual, compare = actual.casefold(), compare.casefold()
    return actual == compare if operator == "equals" else actual != compare if operator == "not_equals" else compare in actual


class EmailBuilderService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def choices(self):
        return [dict(r) for r in self.db.execute("SELECT b.id,b.name,v.id AS version_id,v.version_number FROM email_builders b JOIN email_builder_versions v ON v.builder_id=b.id AND v.version_number=(SELECT MAX(version_number) FROM email_builder_versions WHERE builder_id=b.id) ORDER BY b.name COLLATE NOCASE,b.id")]

    def version(self, version_id):
        row = self.db.execute("SELECT v.*,b.name FROM email_builder_versions v JOIN email_builders b ON b.id=v.builder_id WHERE v.id=?", (version_id,)).fetchone()
        if row is None:
            raise MailError(_ui_tr('Builder-Version nicht gefunden.'))
        value = dict(row)
        graph = json.loads(value.pop("graph_json"))
        validate_graph(graph)
        if digest(graph) != value["content_hash"]:
            raise MailError(_ui_tr('Gespeicherte Builder-Version wurde verändert.'))
        return {**value, "graph": graph, "versions": [dict(r) for r in self.db.execute("SELECT id,version_number FROM email_builder_versions WHERE builder_id=? ORDER BY version_number DESC", (value["builder_id"],))]}

    def save(self, name, graph, *, builder_id=None, base_version_id=None):
        name = header(name, _ui_tr('Builder-Name'))
        if len(name) > 200:
            raise MailError(_ui_tr('Builder-Name ist zu lang.'))
        validate_graph(graph)
        identifier, version_id, now = builder_id or str(uuid4()), str(uuid4()), utc_timestamp()
        with _transaction(self.db):
            number = 1
            if builder_id:
                latest = self.db.execute("SELECT id,version_number FROM email_builder_versions WHERE builder_id=? ORDER BY version_number DESC LIMIT 1", (builder_id,)).fetchone()
                if latest is None or latest["id"] != base_version_id:
                    raise MailError(_ui_tr('Builder wurde geändert. Neu laden und Änderungen prüfen.'))
                number = latest["version_number"] + 1
                self.db.execute("UPDATE email_builders SET name=?,updated_at=? WHERE id=?", (name, now, identifier))
            else:
                self.db.execute("INSERT INTO email_builders(id,name,created_at,updated_at) VALUES(?,?,?,?)", (identifier, name, now, now))
            self.db.execute("INSERT INTO email_builder_versions(id,builder_id,version_number,graph_json,content_hash,created_at) VALUES(?,?,?,?,?,?)", (version_id, identifier, number, _json(graph), digest(graph), now))
            _write_activity(self.db, "builder.saved", "email_builders", identifier, "Builder-Version gespeichert.", {"version_id": version_id, "version_number": number}, now)
        return {"version": self.version(version_id), "builders": self.choices()}

    def details(self):
        data = BulkMailService(self.project).details()
        return {"builders": self.choices(), "runs": data["source_runs"], "profiles": data["source_profiles"], "lists": data["source_lists"], "accounts": data["accounts"], "signatures": data["signatures"], "project_settings": data["project_settings"]}

    @contextmanager
    def evaluate(self, graph, *, provider_account_id=None, signature_id=None, libreoffice_path="", conversion_timeout=120, materialize=False, selected_row=None, evaluation_time=None, cancelled=lambda: False):
        nodes, incoming, order = validate_graph(graph, complete=True)
        clock = frozen_clock(evaluation_time)
        temporal = any(n['kind'] in ('date', 'time') for n in nodes.values())
        if type(conversion_timeout) is not int or not 10 <= conversion_timeout <= 600 or not isinstance(libreoffice_path, str):
            raise MailError(_ui_tr('Ungültige PDF-Einstellungen.'))
        mail = MailService(self.project)
        account = mail._account(provider_account_id) if provider_account_id else None
        mail._reference("email_signatures", signature_id)
        signature = dict(self.db.execute("SELECT * FROM email_signatures WHERE id=?", (signature_id,)).fetchone()) if signature_id else None
        data = next((n for n in nodes.values() if n["kind"] == "data"), None)
        sources = data["config"]["sources"] if data else [None]
        if not sources:
            raise MailError(_ui_tr('Im Datenbaustein 1 bis 100 Excel-/Listenzeilen auswählen.'))
        converter = libreoffice_path or find_libreoffice()
        if any(n["kind"] == "convert" for n in nodes.values()) and (not converter or not Path(converter).is_file()):
            raise MailError(_ui_tr('DOCX → PDF benötigt eine vorhandene LibreOffice-Programmdatei (Einstellungen → Word Replace).'))
        rows, seen = [], set()
        with tempfile.TemporaryDirectory(prefix="builder-", dir=self.project.path / "tmp") as directory:
            temp = Path(directory)
            for row_number, source in enumerate(sources, 1):
                if selected_row is not None and row_number != selected_row:
                    continue
                if cancelled():
                    raise MailError(_ui_tr('Builder-Vorgang abgebrochen.'))
                resolved = BulkSourceService(self.db).resolve(source) if source else {"fields": {}, "contact_id": None, "snapshot": {"kind": "builder_manual"}}
                fields, outputs, files, texts = FieldValues(resolved['fields'], headers=resolved['snapshot'].get('raw_values', {})), {}, [], []
                row = {"number": row_number, "name": fields.get("contact.display_name", ""), "email": "", "error": "", "attachments": [], "documents": [], "node_previews": {}, "linked_contact_id": resolved["contact_id"], "source_snapshot": resolved["snapshot"]}
                try:
                    for identifier in order:
                        if cancelled():
                            raise MailError(_ui_tr('Builder-Vorgang abgebrochen.'))
                        item, inputs = nodes[identifier], {}
                        kind, config = item["kind"], item["config"]
                        for edge in incoming[identifier]:
                            inputs.setdefault(edge["input"], []).append(outputs[(edge["from"], edge["output"])])
                        values = inputs.get("values", [{}])[0]
                        if kind in ('date', 'time', 'variable'):
                            enriched, text = value_output(kind, config, values, clock)
                            outputs[(identifier, 'values')] = enriched
                            outputs[(identifier, 'text')] = (text, {}, 'literal', {})
                            row['node_previews'][identifier] = {'format': 'text', 'text': text, 'field': config['field']}
                            row['source_snapshot'].setdefault('builder_variables', {})[config['field']] = text
                        elif kind == 'clean':
                            source_text, source_values, source_kind, source_options = inputs['text'][0]
                            text = clean_text(body_part(source_text, source_values, source_kind, 'plain', source_options), config)
                            outputs[(identifier, 'text')] = (text, {}, 'literal', {})
                            row['node_previews'][identifier] = {'format': 'text', 'text': text}
                        elif kind == "data":
                            outputs[(identifier, "values")], outputs[(identifier, "email")] = fields, fields.get("contact.email", "")
                        elif kind in (*TEXT_KINDS, "recipient"):
                            # Text carries raw template and values; HTML escaping happens at the email sink.
                            outputs[(identifier, "text" if kind in TEXT_KINDS else "email")] = (config["text"], values, kind, config) if kind in TEXT_KINDS else address(render_text(config["text"], values))
                            try:
                                if kind in ("link", "button", "list"):
                                    row["node_previews"][identifier] = {"format": "html", "text": body_part(config["text"], values, kind, "html", config)}
                                else:
                                    row["node_previews"][identifier] = {"format": "html" if kind == "html" else "text", "text": render_text(config["text"], values, escape=kind == "html")}
                            except MailError as error:
                                if kind == "recipient":
                                    raise
                                # Only the selected condition branch is required by the final mail.
                                row["node_previews"][identifier] = {"format": "text", "text": _ui_format('Noch nicht verwendbar: {0}', str(error)), "error": str(error)}
                        elif kind in ("condition", "merge"):
                            if kind == "condition":
                                branch = "yes" if condition_matches(config, values) else "no"
                                descriptor = inputs.get(branch, [(config[branch], values, "paragraph", {})])[0]
                            else:
                                descriptor = ("", {}, "merge", {"parts": inputs["parts"], "separator": config["separator"]})
                            outputs[(identifier, "text")] = descriptor
                            try:
                                preview_format = "html" if kind == "merge" or descriptor[2] == "html" else "plain"
                                t, f, k, o = descriptor
                                row["node_previews"][identifier] = {"format": "html" if preview_format == "html" else "text", "text": body_part(t, f, k, preview_format, o), **({"branch": branch} if kind == "condition" else {})}
                            except MailError as error:
                                row["node_previews"][identifier] = {"format": "text", "text": _ui_format('Noch nicht verwendbar: {0}', str(error)), "error": str(error)}
                        elif kind in FILE_KINDS:
                            outputs[(identifier, "file")] = source_file(render_text(config["path"], values), kind)
                            if kind == 'docx':
                                outputs[(identifier, 'file')]['_values'] = FieldValues(values)
                            if kind == 'inline_image':
                                image=outputs[(identifier,'file')]
                                image['cid']='ec-'+identifier+'-'+str(row_number)+'@emailcenter.local'
                                outputs[(identifier,'text')]=('',values,'inline_image',{**config,'cid':image['cid']})
                        elif kind == 'attachment':
                            image=deepcopy(inputs['file'][0])
                            filename=render_text(config['filename'],values)
                            if not filename or len(filename)>250 or re.search(r'[\\/:*?"<>|\x00\r\n]',filename) or filename.rstrip(' .')!=filename or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',filename.split('.')[0]):
                                raise MailError(_ui_tr('Anhangname ist ungültig; nur Dateinamen verwenden.'))
                            if Path(filename).suffix.lower()!=Path(image['filename']).suffix.lower():
                                raise MailError(_ui_tr('Die Dateiendung des Anhangs darf nicht geändert werden.'))
                            image['filename']=filename
                            outputs[(identifier,'file')]=image

                        elif kind == "replace":
                            original = inputs["docx"][0]
                            if 'values' not in inputs:
                                values = original.get('_values', values)
                            target = temp / f"{row_number}-{identifier}.docx"
                            replace_docx(original["path"], target, config["rules"], fields=values, source_headers=resolved['snapshot'].get('raw_values', {}), case_sensitive=config["case_sensitive"], whole_words=config["whole_words"])
                            text = extract_docx_text(target)
                            # Literal Word searches may leave braces around multiword/Unicode values.
                            remaining = sorted({match.group(1).strip() or match.group(0)
                                                for match in re.finditer(r'\{\{([^{}\r\n]*)\}\}', text)})
                            if remaining:
                                raise MailError(_ui_format('Offene Dokumentplatzhalter: {0}', ', '.join(remaining)))
                            texts.append({"node_id": identifier, "text": text[:50000]})
                            outputs[(identifier, "file")] = {"path": str(target), "filename": original['filename'], "size": target.stat().st_size, "hash": file_hash(target), "format": "docx", "generated": True, '_values': FieldValues(values)}
                        elif kind == "convert":
                            original = inputs["docx"][0]
                            if analyze_docx(original["path"]).placeholders:
                                raise MailError(_ui_tr('Vor PDF-Ausgabe offene DOCX-Platzhalter ersetzen.'))
                            filename = pdf_filename(config.get('filename', ''), original.get('_values') or fields, original['filename'], source_headers=resolved['snapshot'].get('raw_values', {}))
                            target = Path(convert_docx_to_pdf(original["path"], temp / f"pdf-{row_number}-{identifier}.pdf", executable=converter, timeout_seconds=conversion_timeout, cancelled=cancelled)) if materialize else None
                            outputs[(identifier, "file")] = {"path": str(target) if target else "", "filename": filename, "size": target.stat().st_size if target else None, "hash": file_hash(target) if target else None,
                                "input_hash": original["hash"], "format": "pdf", "generated": True, "conversion": True}
                        elif kind == "email":
                            row["email"] = address(inputs["recipient"][0])
                            subject, subject_fields, subject_kind, subject_options = inputs["subject"][0]
                            row["subject"] = header(body_part(subject, subject_fields, subject_kind, "plain", subject_options), _ui_tr('Betreff'))
                            row["body_format"] = config["body_format"]
                            separator = "<br><br>" if config["body_format"] == "html" else "\n\n"
                            row["body"] = separator.join(body_part(text, values, part_kind, config["body_format"], part_options) for text, values, part_kind, part_options in inputs["body"])
                            if not row["body"].strip() or len(row["body"]) > 1000000:
                                raise MailError(_ui_tr('Nachrichtentext fehlt oder ist zu lang.'))
                            files = list(inputs.get("attachments", []))
                            for descriptor in inputs['body']:
                                # Inline images may appear through merge/condition descriptors.
                                def inline_parts(part):
                                    if part[2]=='inline_image':return [part[3]['cid']]
                                    if part[2]=='merge':return [cid for child in part[3]['parts'] for cid in inline_parts(child)]
                                    return []
                                for cid in inline_parts(descriptor):
                                    inline=next(value for (key,port),value in outputs.items() if port=='file' and value.get('cid')==cid)
                                    if not any(f.get('cid')==cid for f in files):files.append(inline)

                            for file in files:
                                if file["format"] == "docx" and analyze_docx(file["path"]).placeholders:
                                    raise MailError(_ui_tr('DOCX-Anhang enthält offene Platzhalter; Word Replace verbinden.'))
                            if len(files) > 20 or sum(f["size"] or 0 for f in files) > 20 * 1024 * 1024:
                                raise MailError(_ui_tr('Höchstens 20 Anhänge mit zusammen maximal 20 MiB je Nachricht.'))
                            if len({f["filename"].casefold() for f in files}) != len(files):
                                raise MailError(_ui_tr('Anhang-Dateinamen müssen je Nachricht eindeutig sein; doppelte Verbindungen entfernen.'))
                            row["preview_body"] = row["body"]
                            if signature:
                                row["preview_body"] += separator + ((signature["content_html"] or html.escape(signature["content_text"]).replace("\n", "<br>")) if row["body_format"] == "html" else signature["content_text"])
                        if (identifier, "file") in outputs:
                            file = outputs[(identifier, "file")]
                            row["node_previews"][identifier] = deepcopy(file)
                            if file["format"] == "docx":
                                row["node_previews"][identifier]["text"] = extract_docx_text(file["path"])[:50000]
                    if row["email"].casefold() in seen and not (data and data['config'].get('allow_duplicate_recipients', False)):
                        raise MailError(_ui_tr('Doppelte Empfängeradresse. Datenquelle korrigieren.'))
                    seen.add(row["email"].casefold())
                except (ValueError, OSError, DocumentError, DocumentServiceError) as error:
                    row["error"] = str(error)
                row["name"] = row["name"] or row["email"] or f"Zeile {row_number}"
                personal_docx = {}
                for (node_id, port), descriptor in outputs.items():
                    if port == 'file' and descriptor.get('generated') and descriptor.get('format') == 'docx':
                        personal_docx.setdefault(descriptor['path'], {**descriptor, 'node_id': node_id})
                row['personal_docx'] = list(personal_docx.values())
                row["documents"], row["attachments"] = texts, files
                rows.append(row)
            if cancelled():
                raise MailError(_ui_tr('Builder-Vorgang abgebrochen.'))
            yield {"rows": rows, "ready": all(not r["error"] for r in rows), "account": account, "signature": signature, "graph": graph,
                "provider_account_id": provider_account_id, "signature_id": signature_id, "converter": str(converter or ""), "conversion_timeout": conversion_timeout,
                **({'evaluation_time': clock.isoformat()} if temporal else {})}

    @staticmethod
    def public(value):
        result = deepcopy(value)
        for row in result["rows"]:
            for document in row['personal_docx']:
                document.pop('path', None)
                document.pop('_values', None)
            for preview in row["node_previews"].values():
                preview.pop("path", None)
                preview.pop('_values', None)
                if preview.get("conversion"):
                    preview["hash"], preview["size"] = None, None
            for file in row["attachments"]:
                file.pop("path", None)
                file.pop('_values', None)
                if file.get("conversion"):
                    # PDF metadata can vary: approve exact DOCX input and configuration; final bytes are captured at creation.
                    file["hash"], file["size"] = None, None
        result["fingerprint"] = digest(result)
        return result

    def preview(self, graph, **options):
        with self.evaluate(graph, **options) as value:
            result = self.public(value)
            if 'evaluation_time' in result:
                cache = getattr(self, '_preview_clocks', {})
                cache[result['fingerprint']] = result['evaluation_time']
                self._preview_clocks = dict(list(cache.items())[-20:])
            return result

    def asset_preview(self, graph, node_id, *, row_number=1, expected_hash=None, layout=False, **options):
        """Read local media while generated DOCX paths still exist; never send."""
        nodes, _, _ = validate_graph(graph, editable=True)
        item = nodes.get(node_id)
        if item is None or type(row_number) is not int or row_number < 1:
            raise MailError(_ui_tr('Baustein oder Vorschauzeile fehlt.'))
        def read(file):
            if expected_hash is not None and file["hash"] != expected_hash:
                raise MailError(_ui_tr('Vorschaudatei wurde geändert. Alle Zeilen erneut vorschauen.'))
            kind = file["format"]
            if kind == 'docx' and layout:
                with tempfile.TemporaryDirectory(prefix='builder-layout-',dir=self.project.file_path('tmp')) as directory:
                    original_hash=file_hash(file['path'])
                    pdf=convert_docx_to_pdf(file['path'],Path(directory)/'layout.pdf',executable=options.get('libreoffice_path') or find_libreoffice(),timeout_seconds=options.get('conversion_timeout',120),cancelled=options.get('cancelled'))
                    if file_hash(file['path'])!=original_hash:
                        raise MailError(_ui_tr('Dokument während der Layoutvorschau geändert.'))
                    content=pdf.read_bytes()
                    if len(content)>20*1024*1024:raise MailError(_ui_tr('PDF-Vorschau ist zu groß.'))
                    return {'format':'pdf','content':content,'filename':Path(file['filename']).stem+'.pdf'}
            if kind == "docx":
                return {"format": "text", "text": extract_docx_text(file["path"])[:50000], "filename": file["filename"]}
            if kind in ("image", "pdf"):
                with Path(file["path"]).open("rb") as stream:
                    content = stream.read(20 * 1024 * 1024 + 1)
                if len(content) > 20 * 1024 * 1024:
                    raise MailError(_ui_tr('Vorschaudatei ist größer als 20 MiB.'))
                if expected_hash is not None and sha256(content).hexdigest() != expected_hash:
                    raise MailError(_ui_tr('Vorschaudatei während des Ladens geändert. Alle Zeilen erneut vorschauen.'))
                return {"format": kind, "content": content, "filename": file["filename"]}
            if kind == "video":
                return {"format": kind, "path": file["path"], "filename": file["filename"]}
            return {"format": "text", "text": file["filename"] + "\n" + str(file["size"]) + " Bytes"}
        if item["kind"] in FILE_KINDS and "{{" not in item["config"]["path"]:
            return read(source_file(item["config"]["path"], item["kind"]))
        with self.evaluate(graph, selected_row=row_number, materialize=layout, **options) as value:
            preview = value["rows"][0]["node_previews"].get(node_id) if value["rows"] else None
            if not preview:
                if value['rows'] and value['rows'][0]['error']:
                    raise MailError(_ui_format('Bausteinvorschau für Zeile {0} fehlgeschlagen: {1}', value['rows'][0]['number'], value['rows'][0]['error']))
                raise MailError(_ui_tr('Keine Bausteinvorschau verfügbar. Alle Zeilen vorschauen und Daten sowie Verbindungen prüfen.'))
            if preview.get("conversion") and not layout:
                return {"format": "text", "text": "PDF entsteht beim Erstellen. DOCX-Text im Word-Replace-Baustein prüfen; PDF-Layout in der gespeicherten Gruppe ansehen."}
            return preview if "text" in preview and "path" not in preview else read(preview)

    def create(self, name, graph, expected_fingerprint, *, delivery_plan=None, cancelled=lambda: False, **options):
        validate_graph(graph)
        if any(n['kind'] in ('date', 'time') for n in graph['nodes']) and 'evaluation_time' not in options:
            options['evaluation_time'] = getattr(self, '_preview_clocks', {}).get(expected_fingerprint)
            if not options['evaluation_time']:
                raise MailError(_ui_tr('Builder-Vorschau erneut laden und prüfen.'))
        name = header(name, _ui_tr('Gruppenname'))
        if delivery_plan is not None and (not isinstance(delivery_plan, dict) or not {"interval_seconds", "scheduled_local", "timezone_id"} <= set(delivery_plan) <= {"interval_seconds", "scheduled_local", "timezone_id", "daily_budget", "window_start", "window_end"}):
            raise MailError(_ui_tr('Ungültige Builder-Versandplanung.'))
        identifier, now, copied = str(uuid4()), utc_timestamp(), []
        mail = MailService(self.project)
        try:
            with _transaction(self.db), self.evaluate(graph, materialize=True, cancelled=cancelled, **options) as value:
                if self.public(value)["fingerprint"] != expected_fingerprint or not value["ready"]:
                    raise MailError(_ui_tr('Daten, Dateien oder Einstellungen geändert bzw. fehlerhaft. Vorschau erneut prüfen.'))
                template_id, version_id = str(uuid4()), str(uuid4())
                payload = {"subject": "Builder-Ausgabe", "body": "Feste persönliche Builder-Ergebnisse.", "body_format": "plain"}
                # Internal batch metadata is not offered as an editable user mail template.
                self.db.execute("INSERT INTO templates(id,name,template_type,created_at,updated_at,deleted_at) VALUES(?,?,'email',?,?,?)", (template_id, "Builder: " + name[:185], now, now, now))
                self.db.execute("INSERT INTO template_versions(id,template_id,version_number,content_text,placeholders_json,configuration_json,content_hash,created_at) VALUES(?,?,1,?,'[]',?,?,?)", (version_id, template_id, payload["body"], _json({"subject": payload["subject"], "body_format": "plain"}), template_hash(payload), now))
                self.db.execute("INSERT INTO email_draft_batches(id,name,template_version_id,created_at) VALUES(?,?,?,?)", (identifier, name, version_id, now))
                for row in value["rows"]:
                    if cancelled():
                        raise MailError(_ui_tr('Builder-Vorgang abgebrochen.'))
                    draft_id = str(uuid4())
                    entries = mail._copy_attachments([{"path": f["path"], "filename": f["filename"], **({"cid":f["cid"]} if f.get("cid") else {})} for f in row["attachments"]], Path("exports/mail/drafts") / draft_id / str(uuid4()))
                    copied.extend(entries)
                    if [f["hash"] for f in entries] != [f["hash"] for f in row["attachments"]]:
                        raise MailError(_ui_tr('Anhang während der Erstellung geändert. Vorschau erneut prüfen.'))
                    for entry, file in zip(entries, row["attachments"]):
                        if file["generated"]:
                            document = DocumentRepository(self.db).create(file_path=entry["path"], original_filename=entry["filename"], file_size_bytes=entry["size"], file_hash=entry["hash"], template_version_id=None, document_type="builder_document", file_format=file["format"])
                            entry["document_id"] = document["id"]
                    for generated in row['personal_docx']:
                        if any(f['path'] == generated['path'] for f in row['attachments']):
                            continue  # Already persisted as an explicitly chosen attachment.
                        filename = f"{Path(generated['filename']).stem}-{generated['node_id']}.docx"
                        retained = mail._copy_attachments([{'path': generated['path'], 'filename': filename}], Path('documents/builder') / identifier / draft_id)
                        copied.extend(retained)
                        entry = retained[0]
                        if entry['hash'] != generated['hash']:
                            raise MailError(_ui_tr('Anhang während der Erstellung geändert. Vorschau erneut prüfen.'))
                        DocumentRepository(self.db).create(file_path=entry['path'], original_filename=entry['filename'], file_size_bytes=entry['size'], file_hash=entry['hash'], template_version_id=None, document_type='builder_document', file_format='docx')
                    self.db.execute("INSERT INTO email_drafts(id,provider_account_id,signature_id,subject,body,body_format,recipients_json,configuration_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (draft_id, options.get("provider_account_id"), options.get("signature_id"), row["subject"], row["body"], row["body_format"], _json({"to": [row["email"]], "cc": [], "bcc": []}), _json({"attachments": entries}), now, now))
                    reuse = next((n['config'].get('allow_duplicate_recipients', False) for n in graph['nodes'] if n['kind'] == 'data'), False)
                    self.db.execute("INSERT INTO email_draft_batch_items(batch_id,item_key,contact_id,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json,recipient_reuse_allowed) VALUES(?,?,?,?,?,?,?,?)", (identifier, str(row["number"]), row["linked_contact_id"], draft_id, row["email"], row["name"], _json({**row["source_snapshot"], "builder_graph": graph}), int(reuse)))
                # Re-read live inputs after potentially long conversions/copies, still under the write lock.
                if self.preview(graph, cancelled=cancelled, **options)["fingerprint"] != expected_fingerprint:
                    raise MailError(_ui_tr('Quelldaten während der Erstellung geändert. Vorschau erneut prüfen.'))
                _write_activity(self.db, "builder.batch_created", "email_draft_batches", identifier, "Lokale Builder-Entwurfsgruppe erstellt.", {"count": len(value["rows"])}, now)
                dispatch = BulkDeliveryService(self.project)._begin(identifier, options.get("provider_account_id"), **delivery_plan) if delivery_plan is not None else None
        except BaseException:
            mail._cleanup_files(copied)
            raise
        return {"batch": BulkMailService(self.project).batch(identifier), "dispatch": dispatch}
