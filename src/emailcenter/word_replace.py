"""Literal Word replacements across text runs; reviewed copies and shared row sources."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
from copy import deepcopy
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

from .bulk_sources import BulkSourceService, column_fields
from .data_source_library import DataSourceLibrary
from .database import DocumentRepository, utc_timestamp
from .database.repositories import _write_activity
from .document_service import convert_docx_to_pdf, find_libreoffice
from .documents import (DocumentError, SUPPORTED_PARTS, W_P, W_T, WORD_NAMESPACE, XML_SPACE,
                        _locate_character, _namespace_declarations, _parse_xml,
                        _restore_namespace_declarations, analyze_docx, extract_docx_text)
from .mail_bulk import digest
from .mail_models import MailError
from .mail_service import _transaction
from .filename_patterns import output_name


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate_source(path):
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".docx" or not source.is_file() or source.stat().st_size > 20 * 1024 * 1024 or not zipfile.is_zipfile(source):
        raise DocumentError(_ui_tr('Eine gültige DOCX-Datei bis 20 MiB auswählen.'))
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 80 * 1024 * 1024 or len({e.filename for e in entries}) != len(entries):
            raise DocumentError(_ui_tr('DOCX-Paket ist zu groß oder enthält doppelte Teile.'))
        if "word/document.xml" not in archive.namelist():
            raise DocumentError(_ui_tr('DOCX enthält keinen Dokumenttext.'))
        for entry in entries:
            if SUPPORTED_PARTS.fullmatch(entry.filename):
                value = archive.read(entry)
                if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", value, re.IGNORECASE):
                    raise DocumentError(_ui_tr('DOCX-XML mit DTD/Entitäten wird nicht verarbeitet.'))
    return source


class WordRuleError(MailError):
    """A rule error with editor row indices; never changes the user's rules."""

    def __init__(self, message, *rows):
        super().__init__(message)
        self.rule_rows = rows
        self.builder_node_id = None


def validate_rules(rules, case_sensitive):
    if not isinstance(rules, list) or not 1 <= len(rules) <= 100 or type(case_sensitive) is not bool:
        raise WordRuleError(_ui_tr('1 bis 100 Ersetzungsregeln anlegen.'))
    seen, result = {}, []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or set(rule) != {"find", "replacement", "field"} or any(not isinstance(v, str) for v in rule.values()):
            raise WordRuleError(_ui_format('Word Replace: Regel {0} ist ungültig. Suchen, Ersatz und Datenfeld müssen Text sein.', index + 1), index)
        key = rule["find"] if case_sensitive else rule["find"].casefold()
        if not key:
            raise WordRuleError(_ui_format('Word Replace: Regel {0} hat keinen Suchtext. Suchen ausfüllen oder die leere Regel entfernen.', index + 1), index)
        if any(c in key for c in "\r\n\t") or len(key) > 200:
            raise WordRuleError(_ui_format('Word Replace: Suchtext in Regel {0} darf höchstens 200 Zeichen und keine Zeilenumbrüche oder Tabulatoren enthalten.', index + 1), index)
        if len(rule['replacement']) > 32768 or len(rule['field']) > 200 or any('\x00' in v for v in rule.values()):
            raise WordRuleError(_ui_format('Word Replace: Regel {0} enthält ein ungültiges oder zu langes Ersatz-/Datenfeld (max. 32768/200 Zeichen, keine Nullzeichen).', index + 1), index)
        if key in seen:
            raise WordRuleError(_ui_format('Word Replace: Regel {0} und {1} haben denselben Suchtext „{2}“. Jede Suche nur einmal anlegen; eine Regel ersetzt alle Treffer.', seen[key] + 1, index + 1, rule['find']), seen[key], index)
        seen[key] = index
        result.append(dict(rule))
    return result


def _text_groups(paragraph):
    groups = [[]]
    def visit(element):
        for child in element:
            if child.tag == W_P:
                continue
            if child.tag == W_T:
                groups[-1].append(child)
            elif child.tag in (f"{{{WORD_NAMESPACE}}}br", f"{{{WORD_NAMESPACE}}}cr", f"{{{WORD_NAMESPACE}}}tab"):
                groups.append([])
            else:
                visit(child)
    visit(paragraph)
    return [group for group in groups if group]


def _line_breaks(root):
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in list(root.iter(W_T)):
        text = node.text or ""
        if "\n" not in text and "\r" not in text and "\t" not in text:
            continue
        parent = parents[node]
        position = list(parent).index(node)
        parent.remove(node)
        for offset, part in enumerate(re.split(r"([\n\t])", text.replace("\r\n", "\n").replace("\r", "\n"))):
            child = ET.Element(f"{{{WORD_NAMESPACE}}}br" if part == "\n" else f"{{{WORD_NAMESPACE}}}tab" if part == "\t" else W_T)
            if part not in ("\n", "\t"):
                child.attrib.update(node.attrib)
                child.set(XML_SPACE, "preserve")
                child.text = part
            parent.insert(position + offset, child)


def _styled_run(root, node, replacement, suffix, style):
    parents = {child: parent for parent in root.iter() for child in parent}
    run = parents[node]
    if run.tag != f"{{{WORD_NAMESPACE}}}r":
        raise DocumentError(_ui_tr('Formatierter Ersatz benötigt einen normalen Word-Text-Run.'))
    parent = parents[run]
    position = list(parent).index(run)
    properties = run.find(f"{{{WORD_NAMESPACE}}}rPr")
    inserted = ET.Element(run.tag, run.attrib)
    if style != "plain":
        props = deepcopy(properties) if properties is not None else ET.Element(f"{{{WORD_NAMESPACE}}}rPr")
        tag = f"{{{WORD_NAMESPACE}}}" + ("b" if style == "bold" else "i")
        prop = props.find(tag)
        if prop is None:
            prop = ET.SubElement(props, tag)
        prop.set(f"{{{WORD_NAMESPACE}}}val", "1")
        inserted.append(props)
    text = ET.SubElement(inserted, W_T, {XML_SPACE: "preserve"})
    text.text = replacement
    tail = ET.Element(run.tag, run.attrib)
    if properties is not None:
        tail.append(deepcopy(properties))
    if suffix:
        text = ET.SubElement(tail, W_T, {XML_SPACE: "preserve"})
        text.text = suffix
    after = list(run)[list(run).index(node) + 1:]
    for child in after:
        run.remove(child)
        tail.append(child)
    parent.insert(position + 1, inserted)
    if suffix or after:
        parent.insert(position + 2, tail)


def replace_docx(source, target, rules, *, fields=None, source_headers=(), case_sensitive=True, whole_words=False, missing_policy="error", replacement_style="first"):
    """All rules match original paragraph text once; replacements are never cascaded."""
    source = validate_source(source)
    rules = validate_rules(rules, case_sensitive)
    aliases = {header: alias for alias, header in column_fields(list(source_headers)).items()}
    bound_rules = []
    for rule in rules:
        field = rule['field'].strip()
        if field.startswith('{{') and field.endswith('}}'):
            field = field[2:-2].strip()
        field = aliases.get(field, field)
        bound_rules.append({**rule, 'field': field} if field and field in (fields or {}) else rule)
    rules = bound_rules
    if type(whole_words) is not bool or missing_policy not in ("error", "keep"):
        raise MailError(_ui_tr('Ungültige Word-Replace-Einstellungen.'))
    if replacement_style not in ("first", "plain", "bold", "italic"):
        raise MailError(_ui_tr('Ungültige Ersatzformatierung.'))
    if Path(target).resolve() == source:
        raise DocumentError(_ui_tr('Das Original darf nicht überschrieben werden.'))
    fields = fields or {}
    missing = sorted({rule["field"] for rule in rules if rule["field"] and not fields.get(rule["field"], "").strip()})
    if missing and missing_policy == "error":
        raise MailError(_ui_format('Fehlende Datenfelder: {0}', ', '.join(missing)))
    indexed = sorted(enumerate(rules), key=lambda item: (-len(item[1]["find"]), item[0]))
    pattern = "|".join(f"(?P<r{index}>{re.escape(rule['find'])})" for index, rule in indexed)
    if whole_words:
        pattern = r"(?<!\w)(?:" + pattern + r")(?!\w)"
    matcher = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    found, replaced, occurrences = {r["find"]: 0 for r in rules}, {r["find"]: 0 for r in rules}, []
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as output:
        for entry in original.infolist():
            content = original.read(entry)
            if SUPPORTED_PARTS.fullmatch(entry.filename):
                root = _parse_xml(content, entry.filename)
                changed = False
                for number, paragraph in enumerate(root.iter(W_P), 1):
                    for nodes in _text_groups(paragraph):
                        texts = [node.text or "" for node in nodes]
                        text = "".join(texts)
                        matches = list(matcher.finditer(text))
                        boundaries, offset = [], 0
                        for segment in texts:
                            boundaries.append((offset, offset + len(segment)))
                            offset += len(segment)
                        for match in reversed(matches):
                            rule = rules[int(match.lastgroup[1:])]
                            found[rule["find"]] += 1
                            replacement = fields.get(rule["field"]) if rule["field"] else rule["replacement"]
                            if rule["field"] in missing:
                                continue
                            first, start = _locate_character(boundaries, match.start())
                            last, end = _locate_character(boundaries, match.end() - 1)
                            if first == last:
                                if replacement_style == "first":
                                    texts[first] = texts[first][:start] + replacement + texts[last][end + 1:]
                                else:
                                    _styled_run(root, nodes[first], replacement, texts[last][end + 1:], replacement_style)
                                    texts[first] = texts[first][:start]
                            else:
                                if replacement_style != "first":
                                    _styled_run(root, nodes[first], replacement, "", replacement_style)
                                texts[first] = texts[first][:start] + (replacement if replacement_style == "first" else "")
                                for index in range(first + 1, last):
                                    texts[index] = ""
                                texts[last] = texts[last][end + 1:]
                            replaced[rule["find"]] += 1
                            changed = True
                            if len(occurrences) < 1000:
                                occurrences.append({"part": entry.filename, "paragraph": number, "find": rule["find"], "replacement": replacement,
                                                    "context": text[max(0, match.start() - 35):match.end() + 35]})
                        for node, value in zip(nodes, texts):
                            node.text = value
                            if value[:1].isspace() or value[-1:].isspace():
                                node.set(XML_SPACE, "preserve")
                if changed:
                    _line_breaks(root)
                    content = _restore_namespace_declarations(ET.tostring(root, encoding="utf-8", xml_declaration=True), _namespace_declarations(content))
            output.writestr(entry, content)
    return {"found": found, "replaced": replaced, "missing": missing, "occurrences": list(reversed(occurrences))}


class WordReplaceService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def details(self):
        library = DataSourceLibrary(self.db)
        from .word_replace_runs import WordReplaceRuns
        return {"lists": library.lists(), "profiles": library.profiles(), "runs": BulkSourceService(self.db).runs(), "replacement_runs": WordReplaceRuns(self.project).history()}

    def analyze(self, source_path):
        source = validate_source(source_path)
        return {"placeholders": list(analyze_docx(source).placeholders), "text": extract_docx_text(source)[:50000]}

    def preview(self, source_path, rules, *, sources=None, case_sensitive=True, whole_words=False, missing_policy="error", file_format="docx", libreoffice_path="", conversion_timeout=120, replacement_style="first", cancelled=lambda: False, progress=lambda value: None):
        source = validate_source(source_path)
        rules = validate_rules(rules, case_sensitive)
        if file_format not in ("docx", "pdf") or type(conversion_timeout) is not int or not 10 <= conversion_timeout <= 600:
            raise MailError(_ui_tr('Ungültiges Ausgabeformat oder Konvertierungszeitlimit.'))
        converter = libreoffice_path or find_libreoffice()
        if file_format == "pdf" and (not converter or not Path(converter).is_file()):
            raise MailError(_ui_tr('Für PDF LibreOffice installieren oder dessen Programmdatei in Einstellungen wählen.'))
        if sources is None:
            sources = [{"kind": "manual", "fields": {}}]
        if not isinstance(sources, list) or not 1 <= len(sources) <= 100:
            raise MailError(_ui_tr('1 bis 100 Datenzeilen verwenden.'))
        before, rows = extract_docx_text(source)[:50000], []
        with tempfile.TemporaryDirectory(prefix="word-replace-preview-", dir=self.project.path / "tmp") as folder:
            for index, reference in enumerate(sources, 1):
                progress({"current": index - 1, "total": len(sources), "message": _ui_tr("Word-Replace-Zeilen prüfen")})
                if cancelled():
                    raise MailError(_ui_tr('Word-Replace-Vorschau abgebrochen.'))
                row = {"number": index, "name": "", "error": "", "missing": [], "found": {}, "replaced": {}, "occurrences": [], "text": ""}
                try:
                    resolved = BulkSourceService(self.db).resolve(reference)
                    fields = resolved["fields"]
                    row.update(name=fields.get("contact.display_name", ""), source_snapshot=resolved["snapshot"], fields=fields)
                    output = Path(folder) / "preview.docx"
                    row.update(replace_docx(source, output, rules, fields=fields, source_headers=resolved['snapshot'].get('raw_values', {}), case_sensitive=case_sensitive, whole_words=whole_words, missing_policy=missing_policy, replacement_style=replacement_style))
                    row["text"] = extract_docx_text(output)[:50000]
                    row["unresolved"] = list(analyze_docx(output).placeholders)
                    row["output_hash"] = file_hash(output)
                except (MailError, DocumentError, OSError) as error:
                    row["error"] = str(error)
                rows.append(row)
        value = {"source_path": str(source), "source_hash": file_hash(source), "before": before, "rows": rows,
                 "ready": all(not row["error"] for row in rows), "rules": rules, "case_sensitive": case_sensitive,
                 "whole_words": whole_words, "missing_policy": missing_policy, "file_format": file_format,
                 "libreoffice_path": libreoffice_path, "conversion_timeout": conversion_timeout}
        value["replacement_style"] = replacement_style
        return {**value, "fingerprint": digest(value)}

    def create(self, *, expected_fingerprint, output_directory, prefix="Dokument", overwrite=False, filename_pattern="", cancelled=lambda: False, **options):
        preview = self.preview(cancelled=cancelled, **options)
        if preview["fingerprint"] != expected_fingerprint:
            raise MailError(_ui_tr('Original, Datenquelle oder Regeln wurden geändert. Vorschau erneut prüfen.'))
        if not preview["ready"]:
            raise MailError(_ui_tr('Alle Fehler vor der Ausgabe korrigieren.'))
        directory = Path(output_directory).expanduser()
        if not directory.is_absolute() or type(overwrite) is not bool or not isinstance(prefix, str) or not prefix.strip() or len(prefix) > 100 or any(c in prefix for c in '<>:"/\\|?*\r\n\x00'):
            raise MailError(_ui_tr('Absoluten Ausgabeordner und gültigen Dateinamen-Präfix wählen.'))
        directory = directory.resolve()
        if directory.is_relative_to(self.project.path.resolve()) and not directory.is_relative_to((self.project.path / "exports").resolve()):
            raise MailError(_ui_tr('Innerhalb des Projekts unter exports speichern.'))
        prefix = prefix.strip().rstrip(". ")
        if not prefix or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", prefix, re.IGNORECASE):
            raise MailError(_ui_tr('Einen gültigen Dateinamen-Präfix wählen.'))
        directory.mkdir(parents=True, exist_ok=True)
        targets, original_hashes = [], []
        for row in preview["rows"]:
            target = directory / output_name(prefix, row["number"], row["name"], row["fields"], preview["file_format"], filename_pattern, multiple=len(preview["rows"]) > 1)
            if target in targets:
                raise MailError(_ui_tr('Dateinamensmuster erzeugt doppelte Ziele. {number:03d} ergänzen.'))
            if target.resolve() == Path(preview["source_path"]):
                raise MailError(_ui_tr('Das Original darf nicht überschrieben werden.'))
            if target.exists() and (not overwrite or not target.is_file()):
                raise MailError(_ui_tr('Eine Ausgabedatei existiert bereits. Anderen Präfix wählen oder Überschreiben bestätigen.'))
            if target.is_relative_to(self.project.path.resolve()) and self.db.execute("SELECT 1 FROM documents WHERE file_path=?", (target.relative_to(self.project.path.resolve()).as_posix(),)).fetchone():
                raise MailError(_ui_tr('Eine bereits registrierte Dokumentausgabe erhalten. Anderen Präfix wählen.'))
            targets.append(target)
            original_hashes.append(file_hash(target) if target.exists() else None)
        published, backups, registered = [], {}, []
        with tempfile.TemporaryDirectory(prefix=".word-replace-", dir=directory) as folder:
            folder = Path(folder)
            staged = []
            for row in preview["rows"]:
                if cancelled():
                    raise MailError(_ui_tr('Word Replace abgebrochen. Keine Ausgabedatei wurde verändert.'))
                docx = folder / f"{row['number']}.docx"
                replace_docx(preview["source_path"], docx, preview["rules"], fields=row["fields"], source_headers=row['source_snapshot'].get('raw_values', {}), case_sensitive=preview["case_sensitive"], whole_words=preview["whole_words"], missing_policy=preview["missing_policy"], replacement_style=preview["replacement_style"])
                if file_hash(docx) != row["output_hash"]:
                    raise MailError(_ui_tr('Original wurde während der Ausgabe geändert. Vorschau erneut prüfen.'))
                if preview["file_format"] == "pdf":
                    pdf = folder / f"{row['number']}.pdf"
                    convert_docx_to_pdf(docx, pdf, executable=preview["libreoffice_path"] or None, timeout_seconds=preview["conversion_timeout"])
                    staged.append(pdf)
                else:
                    staged.append(docx)
            try:
                with _transaction(self.db):
                    if file_hash(preview["source_path"]) != preview["source_hash"]:
                        raise MailError(_ui_tr('Original wurde während der Ausgabe geändert. Vorschau erneut prüfen.'))
                    for row, reference in zip(preview["rows"], options.get("sources") or [{"kind": "manual", "fields": {}}]):
                        current = BulkSourceService(self.db).resolve(reference)
                        if current["snapshot"] != row["source_snapshot"] or current["fields"] != row["fields"]:
                            raise MailError(_ui_tr('Datenquelle wurde während der Ausgabe geändert. Vorschau erneut prüfen.'))
                    for index, (target, stage, expected) in enumerate(zip(targets, staged, original_hashes)):
                        if cancelled():
                            raise MailError(_ui_tr('Word Replace abgebrochen. Ausgabedateien wurden zurückgenommen.'))
                        actual = file_hash(target) if target.exists() else None
                        if actual != expected:
                            raise MailError(_ui_tr('Zieldatei wurde zwischenzeitlich geändert. Ausgabe erneut starten.'))
                        if expected is not None:
                            backup = folder / f"backup-{index}"
                            shutil.copyfile(target, backup)
                            backups[target] = backup
                        stage.replace(target)
                        published.append(target)
                        if target.is_relative_to(self.project.path.resolve()):
                            registered.append(DocumentRepository(self.db).create(file_path=target.relative_to(self.project.path.resolve()).as_posix(),
                                original_filename=target.name, file_size_bytes=target.stat().st_size, file_hash=file_hash(target), template_version_id=None,
                                file_format=preview["file_format"], document_type="word_replace"))
                    _write_activity(self.db, "word_replace.created", "documents", str(uuid4()), "Word-Replace-Ausgaben erstellt.", {"count": len(targets), "format": preview["file_format"]}, utc_timestamp())
            except BaseException as error:
                failures = []
                for target in reversed(published):
                    try:
                        if target in backups:
                            backups[target].replace(target)
                        else:
                            target.unlink(missing_ok=True)
                    except OSError as restore_error:
                        failures.append(f"{target}: {restore_error}")
                if failures:
                    recovery = directory / (".word-replace-recovery-" + str(uuid4()))
                    folder.rename(recovery)
                    instructions = "Rücknahme unvollständig. Originalkopien und erzeugte Dateien zur Wiederherstellung erhalten.\n\n" + "\n".join(failures)
                    instructions += "\n\nOriginalkopien:\n" + "\n".join(f"{backup.name} -> {target}" for target, backup in backups.items() if (recovery / backup.name).exists())
                    (recovery / "WIEDERHERSTELLUNG.txt").write_text(instructions, encoding="utf-8")
                    raise DocumentError(_ui_format('Ausgabe fehlgeschlagen; Rücknahme durch Dateisperren unvollständig. Wiederherstellungsdateien: {0}', f'{recovery}')) from error
                raise
        return {"paths": [str(path) for path in targets], "count": len(targets), "documents": registered, "format": preview["file_format"]}
