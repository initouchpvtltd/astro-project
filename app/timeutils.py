"""Local time to UTC conversion.

Converting a local time to UTC is only simple when you ignore daylight saving.
Twice a year a place either repeats an hour or skips one, and a birth or horary
time that falls in those windows has no single answer. This module resolves
what it can and reports honestly when a time is genuinely ambiguous.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
    available_timezones,
)


class TimeConversionError(ValueError):
    """The local time cannot be converted for this place and date."""


def parse_local(date_str, time_str):
    """Combine a date and a time into a naive datetime."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise TimeConversionError(
            f"Could not read '{date_str} {time_str}'. Expected YYYY-MM-DD and HH:MM:SS."
        ) from exc


@lru_cache(maxsize=1)
def _zones_by_lowercase():
    """The IANA names keyed by their own lowercase, built once."""
    return {name.lower(): name for name in available_timezones()}


def canonical_zone(timezone_name):
    """The IANA spelling of a name, or None if it is not one.

    Lets a caller record the zone it really used rather than the capitals the
    reader happened to type, so a chart does not print EUROPE/MADRID back.
    """
    return _zones_by_lowercase().get(str(timezone_name or "").strip().lower())


def load_zone(timezone_name):
    """The zone, however the caller happened to capitalise it.

    Someone typing a zone by hand rarely types the capitals, and the name is
    unambiguous without them. The canonical spelling is looked up first rather
    than relied on from the filesystem, which answers case-insensitively on a
    Mac and case-sensitively on the Linux box this is deployed to.
    """
    spelled = _zones_by_lowercase().get(str(timezone_name).strip().lower())
    if spelled is None:
        raise TimeConversionError(
            f"Unknown timezone {timezone_name!r}. Expected an IANA name such as "
            "'Europe/Madrid' or 'Asia/Karachi'."
        )
    try:
        return ZoneInfo(spelled)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimeConversionError(
            f"Unknown timezone {timezone_name!r}. Expected an IANA name such as "
            "'Europe/Madrid' or 'Asia/Karachi'."
        ) from exc


def convert(date_str, time_str, timezone_name):
    """Convert a local time in a named zone to UTC.

    Returns a dict carrying the UTC moment, the offset actually applied, and
    flags for the two daylight-saving edge cases:

    - ambiguous: the clocks went back, so this local time happened twice. We
      take the first occurrence, still on summer time, and report the other.
    - nonexistent: the clocks went forward, so this local time never happened.
      We report it rather than silently inventing a moment.
    """
    naive = parse_local(date_str, time_str)
    zone = load_zone(timezone_name)

    # fold distinguishes the two passes through a repeated hour.
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)

    utc = first.astimezone(timezone.utc)

    # A local time in the spring-forward gap does not exist. Python still hands
    # back a datetime, so detect it by converting to UTC and back: if the local
    # time changes on the way home, it was never on the clock.
    round_trip = utc.astimezone(zone).replace(tzinfo=None)
    nonexistent = round_trip != naive

    # fold also changes the offset inside a gap, so the two-offset test alone
    # would call a skipped hour ambiguous. A time cannot both never happen and
    # happen twice, and not existing is the more specific answer.
    ambiguous = (not nonexistent) and first.utcoffset() != second.utcoffset()

    offset_hours = first.utcoffset().total_seconds() / 3600.0

    result = {
        "local": naive.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": timezone_name,
        "utc_offset": round(offset_hours, 4),
        "utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dst_in_effect": bool(first.dst()),
        "ambiguous": ambiguous,
        "nonexistent": nonexistent,
    }

    if ambiguous:
        other = second.astimezone(timezone.utc)
        result["note"] = (
            "The clocks went back, so this local time occurred twice. Using the "
            "first occurrence. The second would be "
            f"{other.strftime('%Y-%m-%dT%H:%M:%SZ')} UTC."
        )
        result["alternative_utc"] = other.strftime("%Y-%m-%dT%H:%M:%SZ")

    if nonexistent:
        result["note"] = (
            "The clocks went forward, so this local time never occurred in "
            f"{timezone_name}. Interpreting it as "
            f"{round_trip.strftime('%Y-%m-%dT%H:%M:%S')} local."
        )

    return result


def convert_with_offset(date_str, time_str, utc_offset_hours):
    """Convert using an explicit UTC offset, bypassing timezone rules.

    Kept so charts can still be cast for places with no timezone, and so a
    caller who already knows the historical offset can state it outright.
    """
    naive = parse_local(date_str, time_str)
    utc = (naive - timedelta(hours=utc_offset_hours)).replace(tzinfo=timezone.utc)
    return {
        "local": naive.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": None,
        "utc_offset": utc_offset_hours,
        "utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dst_in_effect": None,
        "ambiguous": False,
        "nonexistent": False,
    }
