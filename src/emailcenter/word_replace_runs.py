"""Resumable reviewed Word Replace runs with a publication receipt per row."""

from .language import translate as _ui_tr, format_text as _ui_format

import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from .database import DocumentRepository, utc_timestamp
from .filename_patterns import output_name
from .mail_models import MailError
from .mail_service import _json, _transaction
from .word_replace import WordReplaceService, file_hash, replace_docx
from .document_service import convert_docx_to_pdf
from .documents import DocumentError
from .document_service import DocumentServiceError
from .process_identity import owner_is_alive, current_owner


class WordReplaceRuns:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def history(self):
        return [dict(row) for row in self.db.execute("SELECT r.*,COUNT(i.position) AS total,SUM(i.status='Completed') AS completed FROM word_replace_runs r JOIN word_replace_run_items i ON i.run_id=r.id GROUP BY r.id ORDER BY r.created_at DESC")]

    def snapshot(self, run_id):
        row = self.db.execute("SELECT * FROM word_replace_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise MailError(_ui_tr('Word-Replace-Lauf nicht gefunden.'))
        value = dict(row)
        value["configuration"] = json.loads(value.pop("configuration_json"))
        value["items"] = [{**dict(r), "fields": json.loads(r["fields_json"])} for r in self.db.execute("SELECT * FROM word_replace_run_items WHERE run_id=? ORDER BY position", (run_id,))]
        value["completed"] = sum(item["status"] == "Completed" for item in value["items"])
        value["total"] = len(value["items"])
        return value

    def begin(self, *, expected_fingerprint, output_directory, prefix="Dokument", overwrite=False, filename_pattern="", cancelled=lambda: False, **options):
        preview = WordReplaceService(self.project).preview(cancelled=cancelled, **options)
        if preview["fingerprint"] != expected_fingerprint or not preview["ready"]:
            raise MailError(_ui_tr('Vorschau erneut laden und alle Fehler korrigieren.'))
        directory = Path(output_directory).expanduser()
        if not directory.is_absolute() or type(overwrite) is not bool or not isinstance(prefix, str) or not prefix.strip() or len(prefix) > 100:
            raise MailError(_ui_tr('Absoluten Ausgabeordner und gültigen Präfix wählen.'))
        directory = directory.resolve()
        if directory.is_relative_to(self.project.path) and not directory.is_relative_to(self.project.path / "exports"):
            raise MailError(_ui_tr('Innerhalb des Projekts unter exports speichern.'))
        targets, old_hashes = [], []
        for row in preview["rows"]:
            name = output_name(prefix, row["number"], row["name"], row["fields"], preview["file_format"], filename_pattern, multiple=len(preview["rows"]) > 1)
            target = (directory / name).resolve()
            if target == Path(preview["source_path"]) or target in targets:
                raise MailError(_ui_tr('Original oder doppelte Ziele im Dateinamensmuster. {number:03d} ergänzen.'))
            if target.exists() and (not overwrite or not target.is_file()):
                raise MailError(_ui_tr('Ausgabe existiert bereits; Überschreiben bestätigen oder Muster ändern.'))
            if target.is_relative_to(self.project.path) and self.db.execute("SELECT 1 FROM documents WHERE file_path=?", (target.relative_to(self.project.path).as_posix(),)).fetchone():
                raise MailError(_ui_tr('Registrierte Ausgaben erhalten; ein neues Dateinamensmuster wählen.'))
            targets.append(target)
            old_hashes.append(file_hash(target) if target.exists() else None)
        identifier, now = str(uuid4()), utc_timestamp()
        folder = self.project.file_path(f"exports/word_replace_runs/{identifier}/input.docx", create_parent=True).parent
        captured = folder / "input.docx"
        committed = False
        try:
            shutil.copyfile(preview["source_path"], captured)
            if file_hash(captured) != preview["source_hash"] or cancelled():
                raise MailError(_ui_tr('Original geändert oder Lauf abgebrochen. Vorschau erneut laden.'))
            configuration = {key: preview[key] for key in ("rules", "case_sensitive", "whole_words", "missing_policy", "file_format", "libreoffice_path", "conversion_timeout", "replacement_style")}
            configuration.update(prefix=prefix, filename_pattern=filename_pattern, original_hashes=old_hashes, original_path=preview["source_path"],
                                 source_snapshots=[r["source_snapshot"] for r in preview["rows"]], docx_hashes=[r["output_hash"] for r in preview["rows"]])
            with _transaction(self.db):
                self.db.execute("INSERT INTO word_replace_runs(id,name,source_path,source_hash,configuration_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'Paused',?,?)", (identifier, prefix, captured.relative_to(self.project.path).as_posix(), preview["source_hash"], _json(configuration), now, now))
                for position, (row, target) in enumerate(zip(preview["rows"], targets)):
                    self.db.execute("INSERT INTO word_replace_run_items(run_id,position,fields_json,output_path,status) VALUES(?,?,?,?,'Pending')", (identifier, position, _json(row["fields"]), str(target)))
            committed = True
        finally:
            if not committed:
                captured.unlink(missing_ok=True)
                folder.rmdir()
        return self.snapshot(identifier)

    def pause(self, run_id):
        with _transaction(self.db):
            value = self.snapshot(run_id)
            if value["status"] == "Running" and value.get("owner_token") and owner_is_alive(value):
                raise MailError(_ui_tr('Dieser Lauf wird bereits in einem anderen Fenster verarbeitet. Dort pausieren.'))
            self.db.execute("UPDATE word_replace_runs SET status='Paused',owner_token=NULL,updated_at=? WHERE id=? AND status<>'Completed'", (utc_timestamp(), run_id))
        return self.snapshot(run_id)

    def _claim(self, run_id):
        with _transaction(self.db):
            value = self.snapshot(run_id)
            if value["configuration"].get("restored_requires_review"):
                raise MailError(_ui_tr('Lauf aus einer Sicherung: Original und neues Ausgabeziel prüfen und einen neuen Lauf anlegen. Alte absolute Ausgabeziele werden nicht weiter beschrieben.'))
            if value["status"] == "Completed":
                return value
            if value["status"] == "Running" and value.get("owner_token") and owner_is_alive(value):
                raise MailError(_ui_tr('Dieser Lauf wird bereits in einem anderen Fenster verarbeitet.'))
            pid, started, host = current_owner()
            self.db.execute("UPDATE word_replace_runs SET status='Running',owner_token=?,owner_pid=?,owner_started=?,owner_host=?,updated_at=? WHERE id=?", (str(uuid4()), pid, started, host, utc_timestamp(), run_id))
        return self.snapshot(run_id)

    def _release(self, run_id, token):
        self.db.execute("UPDATE word_replace_runs SET status='Paused',owner_token=NULL,updated_at=? WHERE id=? AND owner_token=? AND status<>'Completed'", (utc_timestamp(), run_id, token))
        return self.snapshot(run_id)

    def _complete(self, run, item):
        target = Path(item["output_path"])
        if not target.is_file() or file_hash(target) != item["output_hash"]:
            raise MailError(_ui_tr('Ausgabedatei fehlt oder wurde geändert. Lauf bleibt pausiert.'))
        with _transaction(self.db):
            if self.db.execute("SELECT owner_token FROM word_replace_runs WHERE id=?", (run["id"],)).fetchone()[0] != run["owner_token"]:
                raise MailError(_ui_tr('Laufbesitz wurde geändert; Ausgabe bleibt zur Wiederherstellung erhalten.'))
            document_id = None
            if target.is_relative_to(self.project.path):
                document = DocumentRepository(self.db).create(file_path=target.relative_to(self.project.path).as_posix(), original_filename=target.name,
                    file_size_bytes=target.stat().st_size, file_hash=item["output_hash"], template_version_id=None,
                    file_format=run["configuration"]["file_format"], document_type="word_replace")
                document_id = document["id"]
            self.db.execute("UPDATE word_replace_run_items SET status='Completed',document_id=?,last_error=NULL WHERE run_id=? AND position=?", (document_id, run["id"], item["position"]))

    def next(self, run_id, cancelled=lambda: False):
        run = self._claim(run_id)
        if run["status"] == "Completed":
            return run
        token = run["owner_token"]
        source = self.project.file_path(run["source_path"])
        try:
            if not source.is_file() or file_hash(source) != run["source_hash"]:
                raise MailError(_ui_tr('Gespeichertes Original fehlt oder wurde geändert. Neuen Lauf erstellen.'))
            for entry in run["items"]:
                if entry["status"] == "Completed" and (not Path(entry["output_path"]).is_file() or file_hash(entry["output_path"]) != entry["output_hash"]):
                    raise MailError(_ui_tr('Eine fertige Ausgabe fehlt oder wurde geändert. Bestehende Ergebnisse bleiben erhalten.'))
        except BaseException:
            self._release(run_id, token)
            raise
        configuration = run["configuration"]
        item = next((entry for entry in run["items"] if entry["status"] != "Completed"), None)
        if not item:
            self.db.execute("UPDATE word_replace_runs SET status='Completed',owner_token=NULL,updated_at=? WHERE id=? AND owner_token=?", (utc_timestamp(), run_id, token))
            return self.snapshot(run_id)
        target = Path(item["output_path"])
        stage = source.parent / f"output-{item['position']}.{configuration['file_format']}"
        try:
            if cancelled():
                return self._release(run_id, token)
            if item["output_hash"] and target.is_file() and file_hash(target) == item["output_hash"]:
                # Recovery after publication but before the completion transaction.
                self._complete(run, item)
            else:
                actual = file_hash(target) if target.is_file() else None
                if actual != configuration["original_hashes"][item["position"]] or (target.exists() and not target.is_file()):
                    raise MailError(_ui_tr('Zieldatei wurde seit der Laufanlage verändert. Sie wird nicht überschrieben.'))
                if item["output_hash"] and (not stage.is_file() or file_hash(stage) != item["output_hash"]):
                    raise MailError(_ui_tr('Vorbereitete Ausgabekopie beschädigt; Lauf bleibt pausiert.'))
                if not item["output_hash"]:
                    docx = source.parent / f"prepared-{item['position']}.docx"
                    replace_docx(source, docx, configuration["rules"], fields=item["fields"], source_headers=configuration['source_snapshots'][item['position']].get('raw_values', {}),
                        **{key: configuration[key] for key in ("case_sensitive", "whole_words", "missing_policy", "replacement_style")})
                    if file_hash(docx) != configuration["docx_hashes"][item["position"]]:
                        raise MailError(_ui_tr('Ausgabe stimmt nicht mit der bestätigten Vorschau überein.'))
                    if configuration["file_format"] == "pdf":
                        convert_docx_to_pdf(docx, stage, executable=configuration["libreoffice_path"] or None, timeout_seconds=configuration["conversion_timeout"], cancelled=cancelled)
                    else:
                        os.replace(docx, stage)
                    if cancelled():
                        return self._release(run_id, token)
                    item["output_hash"] = file_hash(stage)
                    self.db.execute("UPDATE word_replace_run_items SET status='Publishing',output_hash=?,last_error=NULL WHERE run_id=? AND position=?", (item["output_hash"], run_id, item["position"]))
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    backup = source.parent / f"original-{item['position']}.{configuration['file_format']}"
                    if not backup.exists():
                        shutil.copyfile(target, backup)
                        if file_hash(backup) != configuration["original_hashes"][item["position"]]:
                            raise MailError(_ui_tr('Zieldatei wurde während der Sicherung verändert.'))
                # Recheck immediately before publication; the receipt was persisted first.
                if (file_hash(target) if target.exists() else None) != configuration["original_hashes"][item["position"]]:
                    raise MailError(_ui_tr('Zieldatei wurde während der Erzeugung verändert.'))
                if cancelled():
                    return self._release(run_id, token)
                # A sibling temporary file makes replacement atomic even across drives.
                temporary = target.with_name("." + target.name + "." + run_id + ".tmp")
                try:
                    shutil.copyfile(stage, temporary)
                    with temporary.open("r+b") as stream:
                        os.fsync(stream.fileno())
                    if file_hash(temporary) != item["output_hash"]:
                        raise MailError(_ui_tr('Ausgabekopie wurde während der Veröffentlichung geändert.'))
                    if target.resolve() != target or (file_hash(target) if target.exists() else None) != configuration["original_hashes"][item["position"]]:
                        raise MailError(_ui_tr('Ziel wurde vor der Veröffentlichung verändert.'))
                    if cancelled():
                        return self._release(run_id, token)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                self._complete(run, item)
        except (MailError, OSError, ValueError, DocumentError, DocumentServiceError) as error:
            self.db.execute("UPDATE word_replace_run_items SET status='Failed',last_error=? WHERE run_id=? AND position=?", (str(error), run_id, item["position"]))
        finally:
            self._release(run_id, token)
        result = self.snapshot(run_id)
        if result["completed"] == result["total"]:
            self.db.execute("UPDATE word_replace_runs SET status='Completed',updated_at=? WHERE id=?", (utc_timestamp(), run_id))
        return self.snapshot(run_id)
