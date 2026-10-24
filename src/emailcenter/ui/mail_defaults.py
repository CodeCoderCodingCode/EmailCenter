"""Apply defaults to new UI work only; never grant approval or modify saved jobs."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PySide6.QtCore import QTime, QDateTime


def preferences_of(widget):
    while widget is not None:
        if hasattr(widget, "preferences"):
            return widget.preferences
        widget = widget.parentWidget()
    return None


def choose_named(combo, caption):
    if caption:
        index = next((i for i in range(combo.count()) if combo.itemText(i).casefold() == caption.casefold()), -1)
        if index >= 0:
            combo.setCurrentIndex(index)


def apply_mail_defaults(widget, *, project_account=None):
    preferences = preferences_of(widget)
    if preferences is None:
        return
    if hasattr(widget, "account") and not project_account:
        choose_named(widget.account, preferences.mail_account_email)
    if hasattr(widget, "signature"):
        choose_named(widget.signature, preferences.mail_signature_name)


def apply_plan_defaults(widget):
    preferences = preferences_of(widget)
    if preferences is None:
        return
    widget.interval.setValue(preferences.mail_interval_seconds)
    widget.daily_budget.setValue(preferences.mail_daily_budget)
    widget.timezone.setEditable(True)
    widget.timezone.setCurrentText(preferences.mail_timezone_id)
    widget.window_start.setTime(QTime.fromString(preferences.mail_window_start, "HH:mm"))
    widget.window_end.setTime(QTime.fromString(preferences.mail_window_end, "HH:mm"))
    widget.schedule.setDateTime(QDateTime((datetime.now(ZoneInfo(preferences.mail_timezone_id)) + timedelta(hours=1)).replace(tzinfo=None)))
    if hasattr(widget, "delivery_mode"):
        widget.delivery_mode.setCurrentIndex(widget.delivery_mode.findData(preferences.mail_delivery_mode))
    elif hasattr(widget, "scheduled"):
        widget.scheduled.setChecked(preferences.mail_delivery_mode == "scheduled")
