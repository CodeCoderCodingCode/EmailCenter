"""Validated mail values, timezone conversion and stable MIME payloads."""

from .language import translate as _ui_tr, format_text as _ui_format

from datetime import datetime, timezone
from email.headerregistry import Address
from email.errors import HeaderParseError
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
import html
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class MailError(ValueError):
    pass


class AmbiguousTimeError(MailError):
    """A repeated local hour requires an explicit occurrence or UTC offset."""


def address(value):
    if not isinstance(value, str) or not value.strip() or any(character in value for character in "\r\n\x00"):
        raise MailError(_ui_tr('Ungültige E-Mail-Adresse.'))
    value = value.strip()
    try:
        parsed = Address(addr_spec=value)
        if not parsed.username or not parsed.domain or "." not in parsed.domain or not value.isascii():
            raise ValueError()
    except (ValueError, IndexError, HeaderParseError) as error:
        raise MailError(_ui_tr('E-Mail-Adressen ohne Anzeigenamen eingeben, z. B. name@example.com.')) from error
    return parsed.addr_spec


def recipients(values):
    if not isinstance(values, dict) or set(values) - {"to", "cc", "bcc"}:
        raise MailError(_ui_tr('Ungültige Empfängerfelder.'))
    result, seen = {}, set()
    for kind in ("to", "cc", "bcc"):
        entries = values.get(kind, [])
        if not isinstance(entries, list) or len(entries) > 100:
            raise MailError(_ui_tr('Empfänger als Liste angeben; höchstens 100 pro Feld.'))
        result[kind] = []
        for entry in entries:
            email = address(entry)
            if email.casefold() in seen:
                raise MailError(_ui_tr('Ein Empfänger darf nur einmal vorkommen.'))
            seen.add(email.casefold())
            result[kind].append(email)
    if not result["to"] or len(seen) > 100:
        raise MailError(_ui_tr('Mindestens einen An-Empfänger und höchstens 100 Empfänger insgesamt angeben.'))
    return result


def header(value, caption):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\x00") or len(value) > 998:
        raise MailError(_ui_format('{0} fehlt oder enthält ungültige Zeichen.', caption))
    return value.strip()


def utc_string(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise MailError(_ui_tr('Zeitpunkt benötigt eine Zeitzone.'))
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, AttributeError) as error:
        raise MailError(_ui_tr('Ungültiger UTC-Zeitpunkt.')) from error


def schedule_time(value, timezone_id):
    try:
        zone = ZoneInfo(timezone_id)
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
        raise MailError(_ui_tr('Datum/Zeit oder Zeitzone ungültig. Beispiel: 2026-10-20T09:30, Europe/Berlin.')) from error
    if parsed.tzinfo is not None:
        return utc_string(parsed)
    candidates = []
    for fold in (0, 1):
        local = parsed.replace(tzinfo=zone, fold=fold)
        if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == parsed:
            candidates.append(local)
    if not candidates:
        raise MailError(_ui_tr('Diese lokale Uhrzeit existiert wegen der Zeitumstellung nicht.'))
    if len(candidates) == 2 and candidates[0].utcoffset() != candidates[1].utcoffset():
        raise AmbiguousTimeError(_ui_tr('Diese Uhrzeit ist doppeldeutig. UTC-Offset ergänzen, z. B. +01:00.'))
    return utc_string(candidates[0])


def build_message(sender, targets, subject, body, body_format, message_id, created_at, attachments=()):
    message = EmailMessage(policy=SMTP)
    message["From"] = address(sender)
    message["To"] = ", ".join(targets["to"])
    for kind in ("cc", "bcc"):
        if targets[kind]:
            message[kind.capitalize()] = ", ".join(targets[kind])
    message["Subject"] = header(subject, _ui_tr('Betreff'))
    message["Message-ID"] = message_id
    message["Date"] = format_datetime(parse_time(created_at))
    if body_format == "html":
        plain = html.unescape(re.sub(r"<[^>]*>", "", body))
        message.set_content(plain)
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)
    html_part = message.get_body(preferencelist=('html',)) if body_format == 'html' else None
    used_cids = set()
    for attachment in attachments:
        filename, mime_type, content = attachment[:3]
        cid = attachment[3] if len(attachment)>3 else None
        main_type, sub_type = mime_type.split("/", 1)
        if cid:
            if html_part is None or main_type != 'image' or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,200}',cid) or cid in used_cids:
                raise MailError(_ui_tr('Ungültiges oder doppeltes Inline-Bild; HTML erforderlich.'))
            used_cids.add(cid)
            html_part.add_related(content,maintype=main_type,subtype=sub_type,cid='<'+cid+'>',disposition='inline',filename=filename)
        else:
            message.add_attachment(content, maintype=main_type, subtype=sub_type, filename=filename)
    raw = message.as_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise MailError(_ui_tr('Die erzeugte Nachricht überschreitet 32 MiB.'))
    return raw
