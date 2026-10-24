"""Local account budgets and send windows; provider holds never imply a retry."""

from .language import translate as _ui_tr, format_text as _ui_format

from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from .mail_models import MailError, parse_time, utc_string


def validate_policy(daily_budget, window_start, window_end):
    if type(daily_budget) is not int or not 1 <= daily_budget <= 10000:
        raise MailError(_ui_tr('Tagesbudget muss zwischen 1 und 10000 Versandversuchen liegen.'))
    for value in (window_start, window_end):
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise MailError(_ui_tr('Versandfenster als HH:MM angeben.'))


def policy_wait(db, dispatch, now):
    zone = ZoneInfo(dispatch["timezone_id"])
    day = now.astimezone(zone).date()
    start = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)
    used = db.execute("SELECT COUNT(*) FROM email_attempts a JOIN email_jobs j ON j.id=a.email_job_id WHERE j.provider_account_id=? AND a.started_at_utc>=? AND a.started_at_utc<?",
                      (dispatch["provider_account_id"], utc_string(start), utc_string(end))).fetchone()[0]
    candidate = end if used >= dispatch["daily_budget"] else now
    reasons = [_ui_tr("Tagesbudget erreicht")] if candidate > now else []
    hold = db.execute("SELECT * FROM email_account_holds WHERE account_id=?", (dispatch["provider_account_id"],)).fetchone()
    if hold and parse_time(hold["until_utc"]) > candidate:
        candidate = parse_time(hold["until_utc"])
        reasons.append(_ui_format("Anbietersperre: {0}", hold["reason"]))
    a, b = dispatch["window_start"], dispatch["window_end"]
    def allowed(value):
        clock = value.astimezone(zone).strftime("%H:%M")
        return a == b or (a <= clock < b if a < b else clock >= a or clock < b)
    if not allowed(candidate):
        reasons.append(_ui_tr("Außerhalb des Versandfensters"))
        candidate = candidate.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(3 * 24 * 60):
            if allowed(candidate):
                break
            candidate += timedelta(minutes=1)
        else:
            raise MailError(_ui_tr('Versandfenster konnte nicht ermittelt werden.'))
    return {"daily_used": used, "wait_until": utc_string(candidate) if candidate > now else None,
            "wait_reason": " · ".join(reasons)}
