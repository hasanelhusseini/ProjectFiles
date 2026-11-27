import re
from datetime import datetime, timedelta

TIME_FORMAT = "%Y-%m-%d %H:%M"
EPOCH = datetime(2000, 1, 1)
SLOT_MINUTES = 5
_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


class TimeFormatError(ValueError):
    pass


def parse_ts(text):
    if not isinstance(text, str):
        raise TimeFormatError("timestamp must be text in format YYYY-MM-DD HH:MM")
    value = text.strip()
    if not _PATTERN.match(value):
        raise TimeFormatError(f"invalid timestamp '{text}' (expected YYYY-MM-DD HH:MM)")
    try:
        moment = datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        raise TimeFormatError(f"invalid calendar date/time '{text}'")
    if moment < EPOCH:
        raise TimeFormatError(f"timestamp '{text}' is before {EPOCH.strftime(TIME_FORMAT)}")
    return int((moment - EPOCH).total_seconds()) // 60


def fmt_ts(minutes):
    return (EPOCH + timedelta(minutes=minutes)).strftime(TIME_FORMAT)


def fmt_hm(minutes):
    return (EPOCH + timedelta(minutes=minutes)).strftime("%H:%M")


def day_start(minutes):
    return minutes - (minutes % (24 * 60))


def is_date_token(token):
    return re.match(r"^\d{4}-\d{2}-\d{2}$", token) is not None


def is_clock_token(token):
    return re.match(r"^\d{2}:\d{2}$", token) is not None
