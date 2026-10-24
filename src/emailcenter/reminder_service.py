"""Local reminders and application follow-ups, with atomic state changes."""

from .language import translate as _ui_tr, format_text as _ui_format

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import utc_timestamp
from .database.repositories import _atomic, _write_activity
from .mail_models import parse_time, schedule_time, utc_string
from .record_service import RecordService, fingerprint


STATUS_LABELS = {"Pending": "Offen", "Completed": "Erledigt", "Dismissed": "Verworfen", "Cancelled": "Abgebrochen"}
SOURCES = """
    SELECT 'reminder' AS source, r.id AS record_id, r.title, r.description,
           r.due_at_utc, r.timezone_id, r.status, r.application_id,
           a.title AS application_title, c.name AS company_name
    FROM reminders r LEFT JOIN applications a ON a.id=r.application_id
    LEFT JOIN companies c ON c.id=a.company_id
    UNION ALL
    SELECT 'application', a.id, a.title, a.notes, a.next_follow_up_at,
           'Europe/Berlin', 'Pending', a.id, a.title, c.name
    FROM applications a JOIN application_statuses s ON s.id=a.status_id
    LEFT JOIN companies c ON c.id=a.company_id
    WHERE a.deleted_at IS NULL AND s.is_terminal=0
          AND a.next_follow_up_at IS NOT NULL AND trim(a.next_follow_up_at)<>''
"""


def reminder_zone(value):
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ValueError(_ui_tr('Unbekannte Zeitzone. Beispielsweise Europe/Berlin oder UTC eingeben.')) from error


def local_reminder_time(value, timezone_id, occurrence=None):
    """Require an explicit occurrence for a repeated local hour; reject DST gaps."""
    if occurrence is None:
        return schedule_time(value, timezone_id)
    if type(occurrence) is not int or occurrence not in (0, 1):
        raise ValueError(_ui_tr('Ungültige Auswahl für die Zeitumstellung.'))
    zone = reminder_zone(timezone_id)
    try:
        naive = datetime.fromisoformat(value)
        if naive.tzinfo is not None:
            raise ValueError()
        local = naive.replace(tzinfo=zone, fold=occurrence)
        if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
            raise ValueError()
    except (ValueError, TypeError) as error:
        raise ValueError(_ui_tr('Diese lokale Uhrzeit existiert nicht. Bitte Datum und Zeit prüfen.')) from error
    return utc_string(local)


class ReminderService:
    def __init__(self, connection, *, clock=lambda: datetime.now(timezone.utc)):
        self.connection = connection
        self.clock = clock
        # Legacy/imported timestamps may include offsets or lack a valid timezone.
        # Compare actual instants rather than sorting their text representation.
        def due_epoch(value):
            try:
                return parse_time(value).timestamp()
            except (ValueError, TypeError, OverflowError, AttributeError):
                return None
        self.connection.create_function("emailcenter_due_epoch", 1, due_epoch, deterministic=True)

    def _raw(self, source, record_id):
        if source == "application":
            return RecordService(self.connection).get("applications", record_id)
        if source != "reminder":
            raise ValueError(_ui_tr('Unbekannte Erinnerungsart.'))
        row = self.connection.execute("SELECT * FROM reminders WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise ValueError(_ui_tr('Erinnerung nicht gefunden. Bitte aktualisieren.'))
        return dict(row)

    def _check(self, source, record_id, expected_version):
        record = self._raw(source, record_id)
        if fingerprint(record) != expected_version:
            raise ValueError(_ui_tr('Termin wurde zwischenzeitlich geändert. Bitte aktualisieren und erneut öffnen.'))
        if source == "application":
            status = self.connection.execute("SELECT is_terminal FROM application_statuses WHERE id=?", (record["status_id"],)).fetchone()
            if status[0] or not record["next_follow_up_at"]:
                raise ValueError(_ui_tr('Für diese Bewerbung gibt es keinen offenen Nachfasstermin.'))
        elif record["status"] != "Pending":
            raise ValueError(_ui_tr('Diese Erinnerung ist bereits abgeschlossen.'))
        return record

    def details(self, source="reminder", record_id=None):
        if record_id is None and source != "reminder":
            raise ValueError(_ui_tr('Bitte eine Bewerbung auswählen.'))
        record = self._raw(source, record_id) if record_id else None
        if source == "application" and record:
            record = {**record, "due_at_utc": record["next_follow_up_at"], "timezone_id": "Europe/Berlin", "description": record["notes"]}
        applications = [dict(row) for row in self.connection.execute(
            "SELECT id,title FROM applications WHERE deleted_at IS NULL ORDER BY title COLLATE NOCASE,id")]
        return {"source": source, "record": record,
                "version": fingerprint(self._raw(source, record_id)) if record_id else None,
                "applications": applications}

    def _filters(self, view, timezone_id):
        now = self.clock().astimezone(timezone.utc)
        zone = reminder_zone(timezone_id)
        day = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        # Local calendar days may contain 23 or 25 hours.
        end = day + timedelta(days=1)
        invalid = "emailcenter_due_epoch(due_at_utc) IS NULL"
        filters = {
            "due": (f"status='Pending' AND ({invalid} OR emailcenter_due_epoch(due_at_utc)<=?)", [now.timestamp()]),
            "today": ("status='Pending' AND emailcenter_due_epoch(due_at_utc)>=? AND emailcenter_due_epoch(due_at_utc)<?", [day.timestamp(), end.timestamp()]),
            "upcoming": ("status='Pending' AND emailcenter_due_epoch(due_at_utc)>?", [now.timestamp()]),
            "pending": ("status='Pending'", []),
            "history": ("status<>'Pending'", []),
        }
        if view not in filters:
            raise ValueError(_ui_tr('Ungültiger Terminfilter.'))
        return filters[view], now

    def summary(self):
        (condition, args), _ = self._filters("due", "Europe/Berlin")
        row = self.connection.execute(f"WITH items AS ({SOURCES}) SELECT SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS due, "
                                      "SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending FROM items", args).fetchone()
        return {"due": row["due"] or 0, "pending": row["pending"] or 0}

    def list(self, *, view="due", search="", offset=0, limit=50, timezone_id="Europe/Berlin"):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 200:
            raise ValueError(_ui_tr('Ungültige Listenanfrage.'))
        (condition, args), now = self._filters(view, timezone_id)
        if search.strip():
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            condition += " AND (title LIKE ? ESCAPE '\\' OR application_title LIKE ? ESCAPE '\\' OR company_name LIKE ? ESCAPE '\\')"
            args += [f"%{escaped}%"] * 3
        base = f"WITH items AS ({SOURCES}) "
        total = self.connection.execute(base + f"SELECT COUNT(*) FROM items WHERE {condition}", args).fetchone()[0]
        # Clamp pages after completing the final reminder on a page.
        offset = min(offset, ((max(total, 1) - 1) // limit) * limit)
        rows = self.connection.execute(base + f"SELECT * FROM items WHERE {condition} "
                                      "ORDER BY emailcenter_due_epoch(due_at_utc),source,record_id LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["version"] = fingerprint(self._raw(record["source"], record["record_id"]))
            record["kind_label"] = "Nachfassen" if record["source"] == "application" else "Erinnerung"
            record["status_label"] = STATUS_LABELS[record["status"]]
            try:
                due = parse_time(record["due_at_utc"])
                zone = reminder_zone(timezone_id if record["source"] == "application" else record["timezone_id"])
                record["due_label"] = due.astimezone(zone).strftime("%d.%m.%Y %H:%M %Z")
                if record["status"] == "Pending":
                    record["status_label"] = "Überfällig" if due < now else "Fällig" if due == now else "Geplant"
            except ValueError:
                record["due_label"] = record["due_at_utc"]
                record["status_label"] = "Termin / Zeitzone prüfen"
            result.append(record)
        return {"rows": result, "offset": offset, "total": total, "limit": limit, "summary": self.summary()}

    def save(self, *, title, due_at_utc, timezone_id="Europe/Berlin", description=None, application_id=None,
             record_id=None, expected_version=None, source="reminder"):
        if not isinstance(title, str) or not title.strip():
            raise ValueError(_ui_tr('Bitte einen Titel für die Erinnerung eingeben.'))
        if description is not None and not isinstance(description, str):
            raise ValueError(_ui_tr('Beschreibung muss Text sein.'))
        due = utc_string(parse_time(due_at_utc))
        reminder_zone(timezone_id)
        if source not in ("reminder", "application") or (source == "application" and not record_id):
            raise ValueError(_ui_tr('Ungültige Terminart.'))
        with _atomic(self.connection):
            current = self._check(source, record_id, expected_version) if record_id else None
            if application_id and (not current or application_id != current.get("application_id")):
                RecordService(self.connection).get("applications", application_id)
            identifier, now = record_id or str(uuid4()), utc_timestamp()
            if source == "application":
                self.connection.execute("UPDATE applications SET next_follow_up_at=?,updated_at=? WHERE id=?", (due, now, identifier))
            elif current:
                self.connection.execute("UPDATE reminders SET title=?,description=?,due_at_utc=?,timezone_id=?,application_id=?,updated_at=? WHERE id=?",
                                        (title.strip(), description, due, timezone_id, application_id, now, identifier))
            else:
                self.connection.execute("INSERT INTO reminders(id,title,description,due_at_utc,timezone_id,application_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                        (identifier, title.strip(), description, due, timezone_id, application_id, now, now))
            _write_activity(self.connection, "followup.rescheduled" if source == "application" else "reminder.updated" if current else "reminder.created",
                            "applications" if source == "application" else "reminders", identifier, "Termin gespeichert.", {"due_at_utc": due}, now)
            return self._raw(source, identifier)

    def finish(self, source, record_id, expected_version, *, status="Completed"):
        if status not in ("Completed", "Dismissed", "Cancelled"):
            raise ValueError(_ui_tr('Ungültiger Abschlussstatus.'))
        with _atomic(self.connection):
            current = self._check(source, record_id, expected_version)
            now = utc_timestamp()
            if source == "application":
                self.connection.execute("UPDATE applications SET next_follow_up_at=NULL,updated_at=? WHERE id=?", (now, record_id))
            else:
                self.connection.execute("UPDATE reminders SET status=?,updated_at=?,completed_at_utc=? WHERE id=?",
                                        (status, now, now if status == "Completed" else None, record_id))
            _write_activity(self.connection, "followup.completed" if source == "application" else "reminder.closed",
                            "applications" if source == "application" else "reminders", record_id, "Termin abgeschlossen.",
                            {"status": status, "due_at_utc": current.get("due_at_utc", current.get("next_follow_up_at"))}, now)
            return self.summary()
