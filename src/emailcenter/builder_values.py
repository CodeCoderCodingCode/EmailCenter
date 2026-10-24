"""Literal source-column lookup, reusable values and one frozen preview clock."""
from datetime import date, datetime, time, timedelta, timezone
import html
import re
from zoneinfo import ZoneInfo

from .bulk_sources import FIELD_NAME, column_fields
from .language import translate as _ui_tr, format_text as _ui_format
from .mail_models import MailError

TOKEN = re.compile(r'\{\{[ \t]*([^{}\r\n\x00]*?)[ \t]*\}\}')
DATE_FORMATS = ('dd.MM.yyyy', 'yyyy-MM-dd', 'dd.MM.', 'dd. Monat yyyy', 'Wochentag, dd.MM.yyyy')
TIME_FORMATS = ('HH:mm', 'HH:mm:ss', 'hh:mm AM/PM')
VALUE_CONFIGS = {
    'date': {'field': 'datum', 'mode': 'today', 'value': '2027-02-01', 'source_field': '', 'offset_days': 0, 'format': 'dd.MM.yyyy', 'timezone': 'Europe/Berlin', 'overwrite': False},
    'time': {'field': 'uhrzeit', 'mode': 'now', 'value': '09:00', 'source_field': '', 'format': 'HH:mm', 'timezone': 'Europe/Berlin', 'overwrite': False},
    'variable': {'field': 'variable', 'value': '', 'overwrite': False},
    'clean': {'trim': True, 'collapse_spaces': True, 'remove_empty_lines': False, 'case': 'unchanged'},
}


class FieldValues(dict):
    def __init__(self, values=(), *, headers=()):
        super().__init__(values)
        self.aliases = dict(values.aliases) if isinstance(values, FieldValues) else {h: a for a, h in column_fields(list(headers)).items()}

    def get(self, key, default=None):
        return super().get(self.aliases.get(key, key), default)

    def __getitem__(self, key):
        return super().__getitem__(self.aliases.get(key, key))


def placeholders(subject, body):
    names = sorted(set(TOKEN.findall(subject) + TOKEN.findall(body)))
    rest = TOKEN.sub('', subject + body)
    if '{{' in rest or '}}' in rest or any(not n or len(n) > 200 for n in names):
        raise MailError(_ui_tr('Platzhalter vollständig als {{Spaltenname}} oder {{company.name}} angeben; keine leeren Namen oder Zeilenumbrüche.'))
    if len(names) > 200:
        raise MailError(_ui_tr('Höchstens 200 verschiedene Platzhalter pro Text verwenden.'))
    return names


def render_text(text, fields, *, escape=False):
    missing = [name for name in placeholders('', text) if not fields.get(name, '').strip()]
    if missing:
        raise MailError(_ui_format('Fehlende Datenfelder: {0}', ', '.join(missing)))
    return TOKEN.sub(lambda match: html.escape(fields[match.group(1)], quote=True) if escape else fields[match.group(1)], text)


def frozen_clock(value=None):
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value or datetime.now(timezone.utc)
        if not isinstance(result, datetime) or result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc).replace(microsecond=0)
    except (TypeError, ValueError):
        raise MailError(_ui_tr('Zeitpunkt für die Builder-Vorschau ist ungültig.')) from None


def validate_value_config(kind, config, *, editable=False):
    if kind == 'clean':
        if any(type(config[k]) is not bool for k in ('trim', 'collapse_spaces', 'remove_empty_lines')) or config['case'] not in ('unchanged', 'lower', 'upper', 'title'):
            raise MailError(_ui_tr('Ungültige Textbereinigung.'))
        return
    field = config['field']
    if not isinstance(field, str) or len(field) > 200 or (not editable and not FIELD_NAME.fullmatch(field)) or type(config['overwrite']) is not bool:
        raise MailError(_ui_tr('Variablenname mit Buchstaben, Ziffern und Unterstrichen angeben; z. B. datum.'))
    for key in ('value', 'source_field'):
        if key in config and (not isinstance(config[key], str) or len(config[key]) > (32768 if key == 'value' else 200) or '\x00' in config[key]):
            raise MailError(_ui_tr('Ungültiger Variablenwert oder Quellspaltenname.'))
    if kind == 'variable':
        if not editable:
            placeholders('', config['value'])
        return
    try:
        ZoneInfo(config['timezone'])
    except (TypeError, ValueError, KeyError):
        raise MailError(_ui_tr('Gültige Zeitzone für Datum oder Uhrzeit auswählen.')) from None
    if config['mode'] not in (('today', 'fixed', 'source') if kind == 'date' else ('now', 'fixed', 'source')) or config['format'] not in (DATE_FORMATS if kind == 'date' else TIME_FORMATS):
        raise MailError(_ui_tr('Ungültiger Datums- oder Uhrzeitmodus.'))
    if kind == 'date' and (type(config['offset_days']) is not int or not -36500 <= config['offset_days'] <= 36500):
        raise MailError(_ui_tr('Datumsversatz muss zwischen -36500 und 36500 Tagen liegen.'))


def parse_date(value):
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        for format in ('%d.%m.%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(value.strip(), format).date()
            except ValueError:
                pass
    raise MailError(_ui_format('Datum nicht lesbar: {0}. YYYY-MM-DD oder TT.MM.JJJJ verwenden.', value))


def value_output(kind, config, fields, clock):
    validate_value_config(kind, config)
    if kind == 'variable':
        value = render_text(config['value'], fields)
    else:
        local = clock.astimezone(ZoneInfo(config['timezone']))
        if config['mode'] == 'source':
            source = fields.get(config['source_field'], '')
            if not source.strip():
                raise MailError(_ui_format('Fehlende Datenfelder: {0}', config['source_field']))
        else:
            source = config['value']
        if kind == 'date':
            result = local.date() if config['mode'] == 'today' else parse_date(source)
            try:
                result += timedelta(days=config['offset_days'])
            except OverflowError:
                raise MailError(_ui_tr('Datumsversatz liegt außerhalb des gültigen Kalenderbereichs.')) from None
            months = ('Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')
            weekdays = ('Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag')
            value = {'dd.MM.yyyy': result.strftime('%d.%m.%Y'), 'yyyy-MM-dd': result.isoformat(), 'dd.MM.': result.strftime('%d.%m.'),
                     'dd. Monat yyyy': f'{result.day:02}. {months[result.month-1]} {result.year}',
                     'Wochentag, dd.MM.yyyy': f'{weekdays[result.weekday()]}, {result:%d.%m.%Y}'}[config['format']]
        else:
            try:
                result = local.time() if config['mode'] == 'now' else time.fromisoformat(source.strip())
            except ValueError:
                raise MailError(_ui_format('Uhrzeit nicht lesbar: {0}. HH:mm oder HH:mm:ss verwenden.', source)) from None
            value = result.strftime({'HH:mm': '%H:%M', 'HH:mm:ss': '%H:%M:%S', 'hh:mm AM/PM': '%I:%M %p'}[config['format']])
    result = FieldValues(fields)
    field = config['field']
    if field in result and not config['overwrite']:
        raise MailError(_ui_format('Datenfeld {0} existiert bereits. Anderen Variablennamen wählen oder Überschreiben aktivieren.', field))
    result[field] = value
    return result, value


def clean_text(text, config):
    validate_value_config('clean', config)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if config['trim']:
        text = '\n'.join(line.strip() for line in text.split('\n')).strip()
    if config['collapse_spaces']:
        text = re.sub(r'[^\S\n]+', ' ', text)
    if config['remove_empty_lines']:
        text = '\n'.join(line for line in text.split('\n') if line.strip())
    return {'lower': str.lower, 'upper': str.upper, 'title': str.title}.get(config['case'], lambda value: value)(text)
