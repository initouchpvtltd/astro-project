"""Planetary hours.

Not clock hours. The daylight from sunrise to sunset is divided into twelve
equal parts and the night into twelve more, so a summer day hour runs well over
sixty minutes and a winter one well under. The rulers follow the Chaldean
order, and the first hour after sunrise belongs to the ruler of that weekday,
which is where the names of the days come from.

The awkward cases are real ones. Above the polar circles the Sun may not rise
or set at all for weeks, and a moment between midnight and sunrise belongs to
the previous day's night, not the coming day's.
"""

from datetime import timedelta

import swisseph as swe

from .constants import BODY_LOOKUP
from .ephemeris import EPHEMERIS_FLAG, julian_day

# Slowest to fastest by apparent motion, the order the hours cycle through.
CHALDEAN_ORDER = ["SA", "JU", "MA", "SO", "VE", "ME", "MO"]

# The ruler of each weekday, Monday first to match Python's weekday numbering.
WEEKDAY_RULERS = ["MO", "MA", "ME", "JU", "VE", "SA", "SO"]

# Rise and set are measured by the centre of the Sun's disc rather than its
# upper limb, which is the convention traditional sources assume.
_RISE_FLAGS = swe.CALC_RISE | swe.BIT_DISC_CENTER
_SET_FLAGS = swe.CALC_SET | swe.BIT_DISC_CENTER


class NoSunriseOrSunset(ValueError):
    """The Sun does not rise or set here on this date."""


def _event(jd_start, latitude, longitude, flags):
    result, times = swe.rise_trans(
        jd_start, swe.SUN, flags, (longitude, latitude, 0.0), 0.0, 0.0, EPHEMERIS_FLAG
    )
    if result != 0:
        raise NoSunriseOrSunset(
            "The Sun neither rises nor sets at this latitude on this date, so "
            "planetary hours are undefined here. This happens above the polar "
            "circles in summer and winter."
        )
    return times[0]


def _sunrise(jd, latitude, longitude):
    return _event(jd, latitude, longitude, _RISE_FLAGS)


def _sunset(jd, latitude, longitude):
    return _event(jd, latitude, longitude, _SET_FLAGS)


def hour_at(moment_utc, latitude, longitude):
    """Which planetary hour a moment falls in.

    Returns a dict with the ruling body, the hour number from 1 to 12, whether
    it is a day or night hour, and the boundaries of that hour.
    """
    jd = julian_day(moment_utc)

    # Search from a full day earlier so a moment before today's sunrise still
    # finds the sunrise that opened the period it belongs to.
    previous_rise = _sunrise(jd - 1.0, latitude, longitude)
    rise_after = _sunrise(previous_rise + 0.01, latitude, longitude)

    if jd >= rise_after:
        day_start = rise_after
        next_rise = _sunrise(rise_after + 0.01, latitude, longitude)
    else:
        day_start = previous_rise
        next_rise = rise_after

    sunset = _sunset(day_start + 0.01, latitude, longitude)

    if jd < sunset:
        period_start, period_end, is_day = day_start, sunset, True
    else:
        period_start, period_end, is_day = sunset, next_rise, False

    length = (period_end - period_start) / 12.0
    if length <= 0:  # pragma: no cover - guards against a degenerate day
        raise NoSunriseOrSunset("Day or night length came out as zero.")

    index = int((jd - period_start) / length)
    index = max(0, min(11, index))  # the final instant must not spill into 13

    # Hours run continuously from sunrise, so a night hour is offset by the
    # twelve day hours that preceded it.
    sequence = index if is_day else index + 12
    ruler = _ruler(day_start, sequence)

    return {
        "ruler": ruler,
        "ruler_name": BODY_LOOKUP[ruler].name,
        "hour": index + 1,
        "is_day": is_day,
        "starts": swe.revjul(period_start + index * length),
        "day_ruler": _day_ruler(day_start),
    }


def _day_ruler(sunrise_jd):
    """The planet ruling the astrological day, which begins at sunrise."""
    year, month, day, _ = swe.revjul(sunrise_jd)
    from datetime import date

    return WEEKDAY_RULERS[date(int(year), int(month), int(day)).weekday()]


def _ruler(sunrise_jd, sequence):
    """The ruler of the nth hour after sunrise, counting from zero."""
    start = CHALDEAN_ORDER.index(_day_ruler(sunrise_jd))
    return CHALDEAN_ORDER[(start + sequence) % 7]


def ruler_at(moment_utc, latitude, longitude):
    """Just the ruling body's code, which is all the evaluator needs."""
    return hour_at(moment_utc, latitude, longitude)["ruler"]
