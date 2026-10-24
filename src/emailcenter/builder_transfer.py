"""Portable graph templates; imported graphs never carry active data or file sources."""

from .language import translate as _ui_tr, format_text as _ui_format

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from .document_bundle import file_hash
from .email_builder import FILE_KINDS, NODE_TYPES, validate_graph
from .mail_models import MailError, header


def portable_graph(graph):
    validate_graph(graph, editable=True)
    value = deepcopy(graph)
    sources = []
    for item in value["nodes"]:
        if item["kind"] == "data":
            item["config"]["sources"] = []
            sources.append({"node_id": item["id"], "title": NODE_TYPES[item["kind"]]["title"], "type": "rows"})
        elif item["kind"] in FILE_KINDS:
            item["config"]["path"] = ""
            sources.append({"node_id": item["id"], "title": NODE_TYPES[item["kind"]]["title"], "type": "file"})
    return value, sources


class BuilderTransferService:
    def __init__(self, project):
        self.project = project

    def export(self, *, name, graph, target_path, overwrite=False, cancelled=lambda: False):
        name = header(name, _ui_tr('Buildername'))
        if len(name) > 200 or type(overwrite) is not bool:
            raise MailError(_ui_tr('Buildername zu lang oder ungültige Überschreiboption.'))
        graph, sources = portable_graph(graph)
        content = (json.dumps({"format": "emailcenter.builder", "version": 1, "name": name, "graph": graph}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(content) > 3_000_000:
            raise MailError(_ui_tr('Graphvorlage ist größer als 3 MB.'))
        target = Path(target_path).expanduser()
        if not target.is_absolute() or target.suffix.lower() != ".json":
            raise MailError(_ui_tr('Einen absoluten Zielpfad mit .json auswählen.'))
        target = target.resolve()
        if target.is_relative_to(self.project.path.resolve()) and not target.is_relative_to((self.project.path / "exports").resolve()):
            raise MailError(_ui_tr('Innerhalb des Projekts Graphvorlagen nur unter exports speichern.'))
        existed = target.exists()
        if existed and (not overwrite or not target.is_file()):
            raise MailError(_ui_tr('Vorhandene Graphdatei ausdrücklich zum Ersetzen bestätigen.'))
        original = file_hash(target) if existed else None
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".emailcenter-graph-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if cancelled():
                raise MailError(_ui_tr('Graphexport abgebrochen.'))
            if target.exists() != existed or (existed and file_hash(target) != original):
                raise MailError(_ui_tr('Zieldatei zwischenzeitlich geändert; Export neu starten.'))
            os.replace(temporary, target)
            return {"path": str(target), "name": name, "nodes": len(graph["nodes"]), "sources": sources}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def import_file(self, path):
        source = Path(path)
        if not source.is_absolute() or not source.is_file() or source.suffix.lower() != ".json" or source.stat().st_size > 3_000_000:
            raise MailError(_ui_tr('Eine vorhandene Graph-JSON bis 3 MB mit absolutem Pfad auswählen.'))
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(_ui_tr('Doppeltes JSON-Feld'))
                result[key] = value
            return result
        try:
            with source.open("rb") as stream:
                content = stream.read(3_000_001)
            if len(content) > 3_000_000:
                raise ValueError()
            value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique_object,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Ungültige Zahl")))
            if not isinstance(value, dict) or set(value) != {"format", "version", "name", "graph"} or value["format"] != "emailcenter.builder" or type(value["version"]) is not int or value["version"] != 1:
                raise ValueError()
            name = header(value["name"], _ui_tr('Buildername'))
            if len(name) > 200:
                raise ValueError()
            graph, sources = portable_graph(value["graph"])
        except (ValueError, TypeError, UnicodeError, RecursionError, KeyError) as error:
            raise MailError(_ui_tr('Ungültige oder nicht unterstützte EmailCenter-Graphvorlage. Aktueller Graph bleibt erhalten.')) from error
        return {"name": name, "graph": graph, "sources": sources, "filename": source.name}
