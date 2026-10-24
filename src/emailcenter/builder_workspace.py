"""Recover unfinished editor state without creating versions, jobs or previews."""

from .language import translate as _ui_tr, format_text as _ui_format

from copy import deepcopy
import json
import math

from .database import utc_timestamp
from .email_builder import validate_graph, EmailBuilderService
from .mail_bulk import digest
from .mail_models import MailError
from .mail_service import _transaction, _json


STATE_KEYS = {"graph", "name", "builder_id", "version_id", "provider_account_id", "signature_id", "last_batch",
              "delivery_mode", "scheduled_local", "timezone_id", "interval_seconds", "view"}


def validate_state(state):
    if not isinstance(state, dict) or not STATE_KEYS <= set(state) <= STATE_KEYS | {"daily_budget", "window_start", "window_end", "history", "future"} or len(_json(state).encode("utf-8")) > 12_000_000:
        raise MailError(_ui_tr('Ungültiger oder zu großer Builder-Arbeitsstand.'))
    validate_graph(state["graph"], editable=True)
    for key in ("history", "future"):
        graphs = state.get(key, [])
        if not isinstance(graphs, list) or len(graphs) > 100:
            raise MailError(_ui_tr('Ungültige Undo-/Redo-Historie.'))
        for graph in graphs:
            validate_graph(graph, editable=True)
    from .delivery_policy import validate_policy
    validate_policy(state.get("daily_budget", 100), state.get("window_start", "00:00"), state.get("window_end", "00:00"))
    for key, maximum in (("name", 200), ("timezone_id", 100), ("scheduled_local", 100)):
        value = state[key]
        if not isinstance(value, str) or len(value) > maximum or any(c in value for c in "\x00\r\n"):
            raise MailError(_ui_format('Ungültiges Arbeitsstand-Feld: {0}', key))
    for key in ("builder_id", "version_id", "provider_account_id", "signature_id", "last_batch"):
        value = state[key]
        if value is not None and (not isinstance(value, str) or not value or len(value) > 100):
            raise MailError(_ui_format('Ungültiger Arbeitsstand-Bezug: {0}', key))
    if bool(state["builder_id"]) != bool(state["version_id"]):
        raise MailError(_ui_tr('Builder und Basisversion gemeinsam angeben.'))
    if state["delivery_mode"] not in ("drafts", "now", "scheduled") or type(state["interval_seconds"]) is not int or not 1 <= state["interval_seconds"] <= 3600:
        raise MailError(_ui_tr('Ungültige Arbeitsstand-Planung.'))
    view = state["view"]
    if not isinstance(view, dict) or set(view) != {"zoom", "x", "y"} or any(type(v) not in (int, float) or not math.isfinite(v) for v in view.values()) or not .25 <= view["zoom"] <= 2.5 or max(abs(view["x"]), abs(view["y"])) > 100000:
        raise MailError(_ui_tr('Ungültige Builder-Ansicht.'))


class BuilderWorkspaceService:
    def __init__(self, project):
        self.project, self.db = project, project.connection

    def load(self):
        record = self.db.execute("SELECT * FROM email_builder_workspace WHERE id=1").fetchone()
        result = {"project_id": self.project.project_id, "revision": record["revision"] if record else 0, "state": None, "warning": "", "base_version": None}
        if record:
            try:
                state = json.loads(record["state_json"])
                validate_state(state)
                if digest(state) != record["content_hash"]:
                    raise MailError(_ui_tr('Hash des Arbeitsstands stimmt nicht überein.'))
                result["state"] = state
                if state["version_id"]:
                    version = EmailBuilderService(self.project).version(state["version_id"])
                    if version["builder_id"] != state["builder_id"]:
                        raise MailError(_ui_tr('Builder-Basisversion passt nicht zum Arbeitsstand.'))
                    result["base_version"] = version
            except (ValueError, TypeError, KeyError) as error:
                result["state"] = None
                result["warning"] = _ui_format('Arbeitsstand konnte nicht geladen werden; gespeicherte Versionen bleiben verfügbar. {0}', str(error))
        return result

    def save(self, project_id, state, expected_revision):
        if project_id != self.project.project_id or type(expected_revision) is not int or expected_revision < 0:
            raise MailError(_ui_tr('Projekt oder Arbeitsstand-Revision stimmt nicht überein.'))
        validate_state(state)
        with _transaction(self.db):
            record = self.db.execute("SELECT revision,content_hash,state_json FROM email_builder_workspace WHERE id=1").fetchone()
            revision = record["revision"] if record else 0
            if revision != expected_revision:
                raise MailError(_ui_tr('Arbeitsstand wurde in einem anderen Fenster geändert. Sicherung pausiert; gespeicherten Arbeitsstand neu laden oder aktuelle Version als Kopie speichern.'))
            checksum = digest(state)
            if record and record["content_hash"] == checksum and record["state_json"] == _json(state):
                return {"project_id": project_id, "revision": revision, "state_hash": checksum}
            revision += 1
            self.db.execute("INSERT INTO email_builder_workspace(id,revision,state_json,content_hash,updated_at) VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state_json=excluded.state_json,content_hash=excluded.content_hash,updated_at=excluded.updated_at",
                            (revision, _json(state), checksum, utc_timestamp()))
        return {"project_id": project_id, "revision": revision, "state_hash": checksum}


def arrange_graph(graph):
    """Deterministic left-to-right layout; preserve configs and edge ordering."""
    nodes, incoming, order = validate_graph(graph, editable=True)
    result, levels, columns = deepcopy(graph), {}, {}
    for identifier in order:
        levels[identifier] = max((levels[e["from"]] + 1 for e in incoming[identifier]), default=0)
        columns.setdefault(levels[identifier], []).append(identifier)
    positions = {}
    from .email_builder import NODE_TYPES
    for column, identifiers in columns.items():
        y = 0
        for identifier in sorted(identifiers, key=lambda key: (nodes[key]["y"], order.index(key))):
            positions[identifier] = column * 340, y
            spec = NODE_TYPES[nodes[identifier]["kind"]]
            y += max(115, 88 + max(len(spec["inputs"]), len(spec["outputs"])) * 29) + 45
    for item in result["nodes"]:
        item["x"], item["y"] = positions[item["id"]]
    return result
