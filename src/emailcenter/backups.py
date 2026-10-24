"""Verified archives, conservative retention and atomic restore into a new folder."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from .project import (DATABASE_FILENAME, MANIFEST_FILENAME, PROJECT_DIRECTORIES,
                      ProjectError, open_project, _sha256)
from .database import utc_timestamp

INDEX = "backup_index.json"
MAX_TOTAL = 4 * 1024**3
MAX_FILE = 2 * 1024**3


def _filesystem_path(path):
    """Use Windows extended paths for already validated staging filesystem work.

    Staging adds characters even when the final project paths fit MAX_PATH.
    Logical paths stay unchanged for archive names, project metadata and UI values.
    """
    path = Path(path)
    if os.name != 'nt':
        return path
    value = str(path.absolute())
    if value.startswith('\\\\?\\'):
        return path
    if value.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + value[2:])
    return Path('\\\\?\\' + value)


def write_index(path, project_id):
    entries = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            digest = hashlib.sha256()
            with archive.open(info) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            entries[info.filename] = {"size": info.file_size, "sha256": digest.hexdigest()}
    with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(INDEX, json.dumps({"version": 1, "project_id": project_id, "files": entries}, ensure_ascii=False))


def safe_members(archive):
    members, seen, total = [], set(), 0
    for info in archive.infolist():
        name, path = info.filename, PurePosixPath(info.filename)
        if (not name or "\\" in name or ":" in name or "\x00" in name or path.is_absolute()
                or any(part in (".", "..", "") or part.endswith((".", " "))
                       or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
                       for part in name.rstrip("/").split("/"))
                or stat.S_ISLNK(info.external_attr >> 16)):
            raise ProjectError(_ui_format('Unsicherer Dateipfad im Backup: {0}', name))
        if (path.parts[0] not in ("imports", "templates", "documents", "exports")
                and name not in (MANIFEST_FILENAME, DATABASE_FILENAME, INDEX)):
            raise ProjectError(_ui_format('Unbekannter Backup-Inhalt: {0}', name))
        normalized = name.rstrip("/").casefold()
        if normalized in seen:
            raise ProjectError(_ui_format('Doppelte Backup-Datei: {0}', name))
        seen.add(normalized)
        total += info.file_size
        if len(seen) > 20000 or info.file_size > MAX_FILE or total > MAX_TOTAL:
            raise ProjectError(_ui_tr('Backup überschreitet die Sicherheitsgrößen (20.000 Dateien / 4 GiB).'))
        if info.flag_bits & 1:
            raise ProjectError(_ui_tr('Verschlüsselte ZIP-Dateien werden nicht unterstützt.'))
        members.append(info)
    if not {MANIFEST_FILENAME, DATABASE_FILENAME} <= {item.filename for item in members}:
        raise ProjectError(_ui_tr('Backup enthält keine vollständige Projektbasis.'))
    return members


def inspect_backup(path):
    try:
        path = Path(path).resolve()
        with zipfile.ZipFile(path) as archive:
            members = safe_members(archive)
            if archive.getinfo(MANIFEST_FILENAME).file_size > 65536:
                raise ProjectError(_ui_tr('Projektmanifest ist zu groß.'))
            manifest = json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("project_format_version") != 1 or manifest.get("database") != DATABASE_FILENAME or any(not isinstance(manifest.get(key), str) or not manifest[key].strip() for key in ("name", "project_id", "created_at")):
                raise ProjectError(_ui_tr('Backup hat kein gültiges Projektmanifest.'))
            index = None
            if INDEX in archive.namelist():
                if archive.getinfo(INDEX).file_size > 4_000_000:
                    raise ProjectError(_ui_tr('Backup-Dateiverzeichnis ist zu groß.'))
                index = json.loads(archive.read(INDEX).decode("utf-8"))
                names = {info.filename for info in members if info.filename != INDEX and not info.is_dir()}
                if not isinstance(index, dict) or index.get("version") != 1 or index.get("project_id") != manifest["project_id"] or not isinstance(index.get("files"), dict) or set(index["files"]) != names:
                    raise ProjectError(_ui_tr('Backup-Dateiverzeichnis passt nicht zum Archiv.'))
                for info in members:
                    if info.filename == INDEX or info.is_dir():
                        continue
                    item = index["files"][info.filename]
                    if not isinstance(item, dict) or item.get("size") != info.file_size or not isinstance(item.get("sha256"), str) or re.fullmatch("[a-f0-9]{64}", item["sha256"]) is None:
                        raise ProjectError(_ui_tr('Ungültiger Backup-Dateihash.'))
        return {"path": str(path), "hash": _sha256(path), "name": manifest["name"], "project_id": manifest["project_id"],
                "created_at": manifest["created_at"], "files": len(members), "bytes": sum(info.file_size for info in members),
                "verified_index": index is not None}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        raise ProjectError(_ui_format('Backup kann nicht geprüft werden: {0}', str(error))) from error


def restore_backup(path, destination, expected_hash, *, cancelled=lambda: False):
    review = inspect_backup(path)
    if review["hash"] != expected_hash:
        raise ProjectError(_ui_tr('Backup wurde seit der Vorschau verändert. Erneut prüfen.'))
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ProjectError(_ui_tr('Wiederherstellung benötigt einen neuen, noch nicht vorhandenen Ordner.'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".emailcenter-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(review["path"]) as archive:
            members = safe_members(archive)
            index = json.loads(archive.read(INDEX).decode("utf-8")) if review["verified_index"] else None
            for info in members:
                if cancelled():
                    raise ProjectError(_ui_tr('Wiederherstellung abgebrochen.'))
                if info.filename == INDEX:
                    continue
                target = staging.joinpath(*PurePosixPath(info.filename).parts)
                filesystem_target = _filesystem_path(target)
                if info.is_dir():
                    filesystem_target.mkdir(parents=True, exist_ok=True)
                    continue
                filesystem_target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(info) as source, filesystem_target.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        if cancelled():
                            raise ProjectError(_ui_tr('Wiederherstellung abgebrochen.'))
                        digest.update(chunk)
                        output.write(chunk)
                if index and digest.hexdigest() != index["files"][info.filename]["sha256"]:
                    raise ProjectError(_ui_format('Backup-Datei stimmt nicht mit ihrem Hash überein: {0}', info.filename))
        if _sha256(Path(review["path"])) != expected_hash:
            raise ProjectError(_ui_tr('Backup wurde während der Wiederherstellung verändert.'))
        for directory in PROJECT_DIRECTORIES:
            (staging / directory).mkdir(exist_ok=True)
        with open_project(staging) as project:
            # Restored copies must never resume delivery using an old approval.
            db, now = project.connection, utc_timestamp()
            db.execute("UPDATE email_provider_accounts SET is_enabled=0,updated_at=?", (now,))
            db.execute("UPDATE email_jobs SET status='Uncertain',updated_at=? WHERE status='Sending'", (now,))
            db.execute("UPDATE email_jobs SET approval_status='pending',requires_overdue_confirmation=1,updated_at=? WHERE status IN ('Scheduled','Queued')", (now,))
            db.execute("UPDATE email_bulk_dispatches SET background=0")
            db.execute("UPDATE email_bulk_dispatches SET status='Paused',updated_at=? WHERE status IN ('Running','Ready')", (now,))
            for run in db.execute("SELECT id,configuration_json FROM word_replace_runs WHERE status<>'Completed'").fetchall():
                config = json.loads(run["configuration_json"])
                config["restored_requires_review"] = True
                db.execute("UPDATE word_replace_runs SET status='Paused',owner_token=NULL,configuration_json=?,updated_at=? WHERE id=?", (json.dumps(config), now, run["id"]))
        if cancelled():
            raise ProjectError(_ui_tr('Wiederherstellung abgebrochen.'))
        # On Windows rename refuses an existing target, including a racing creator.
        if destination.exists() or destination.is_symlink():
            raise ProjectError(_ui_tr('Zielordner wurde zwischenzeitlich angelegt.'))
        os.rename(staging, destination)
        return str(destination.resolve())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise ProjectError(_ui_format('Wiederherstellung fehlgeschlagen: {0}', str(error))) from error
    finally:
        if staging.exists():
            if staging.parent.resolve() != destination.parent.resolve():
                raise ProjectError('Restore staging left its expected parent directory.')
            shutil.rmtree(_filesystem_path(staging))


def prune_backups(project, directory, keep):
    """Only remove own verified archives with an unchanged recorded hash."""
    if not keep:
        return
    directory = Path(directory).resolve()
    candidates = []
    for row in project.connection.execute("SELECT * FROM backup_metadata WHERE status='Verified' ORDER BY created_at DESC,rowid DESC"):
        candidate = Path(row["file_path"])
        if not candidate.is_absolute():
            candidate = project.file_path(candidate)
        if candidate.is_symlink() or candidate.parent.resolve() != directory or not candidate.is_file():
            continue
        if _sha256(candidate) != row["file_hash"]:
            continue
        try:
            review = inspect_backup(candidate)
        except ProjectError:
            continue
        if review["project_id"] == project.project_id:
            candidates.append((row["id"], candidate))
    for identifier, candidate in candidates[keep:]:
        candidate.unlink()
        project.connection.execute("UPDATE backup_metadata SET status='Deleted' WHERE id=?", (identifier,))
