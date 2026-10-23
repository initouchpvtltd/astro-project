"""Swiss Ephemeris wrapper.

Everything that talks to pyswisseph lives here, so the rest of the service
deals in plain dictionaries.
"""

import math
import os
from datetime import datetime, timedelta, timezone

import swisseph as swe

from .constants import (
    BODIES,
    DEFAULT_HOUSE_SYSTEM,
    HOUSE_SYSTEMS,
    SIGNS,
    SIGN_TRIGRAMS,
    STATIONARY_THRESHOLD_DEG_PER_DAY,
)

EPHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ephe")

def _data_files_load():
    """True when swisseph can actually read the .se1 files right now.

    Chiron resolves only from seas_18.se1, so it fails loudly when the data
    files are not being used. The main planets do not: swisseph silently
    substitutes its built-in Moshier theory for those, which is why a position
    can look plausible and still be wrong in the arcseconds.
    """
    try:
        swe.calc_ut(swe.julday(2026, 5, 14, 10.0), swe.CHIRON, swe.FLG_SWIEPH)
        return True
    except swe.Error:
        return False


def _init_ephemeris():
    """Point swisseph at the data files and prove it worked.

    set_ephe_path can appear to succeed while the library carries on searching
    its compiled-in defaults, which differ between the macOS and Linux builds.
    So every attempt below is verified, and if none takes effect we copy the
    files into the working directory, which is the first entry in swisseph's
    default search path on every platform.

    Returns (flag, description).
    """
    if not (os.path.isdir(EPHE_PATH) and os.listdir(EPHE_PATH)):
        return swe.FLG_MOSEPH, "Moshier (built-in, no data files present)"

    # Some builds read this at initialisation rather than via set_ephe_path.
    os.environ.setdefault("SE_EPHE_PATH", EPHE_PATH)

    for path in (EPHE_PATH, EPHE_PATH.encode("utf-8"), EPHE_PATH + os.sep):
        try:
            swe.set_ephe_path(path)
        except TypeError:
            continue
        if _data_files_load():
            return swe.FLG_SWIEPH, "Swiss Ephemeris data files"

    # Last resort: copy the files into the working directory. "." is the first
    # entry in swisseph's compiled-in search path on Linux, so this works even
    # if set_ephe_path itself is doing nothing.
    try:
        import shutil

        for name in os.listdir(EPHE_PATH):
            if name.endswith(".se1"):
                target = os.path.join(os.getcwd(), name)
                if not os.path.exists(target):
                    shutil.copy2(os.path.join(EPHE_PATH, name), target)

        # Test the default search path first, without relying on set_ephe_path.
        if _data_files_load():
            return swe.FLG_SWIEPH, "Swiss Ephemeris data files (working directory)"

        try:
            swe.set_ephe_path(os.getcwd())
        except TypeError:
            pass
        if _data_files_load():
            return swe.FLG_SWIEPH, "Swiss Ephemeris data files (working directory)"
    except OSError:
        pass

    # Present but unusable. Say so plainly rather than serving lower-precision
    # numbers as though nothing were wrong.
    return swe.FLG_MOSEPH, "Moshier (data files present but swisseph could not load them)"


EPHEMERIS_FLAG, EPHEMERIS_SOURCE = _init_ephemeris()

CALC_FLAGS = EPHEMERIS_FLAG | swe.FLG_SPEED


def to_utc(date_str, time_str, utc_offset_hours):
    """Combine a local date and time with its UTC offset."""
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    return (naive - timedelta(hours=utc_offset_hours)).replace(tzinfo=timezone.utc)


def julian_day(moment_utc):
    hour = (
        moment_utc.hour
        + moment_utc.minute / 60.0
        + (moment_utc.second + moment_utc.microsecond / 1e6) / 3600.0
    )
    return swe.julday(moment_utc.year, moment_utc.month, moment_utc.day, hour)


def format_position(longitude):
    """Split an ecliptic longitude into sign, degrees, minutes and seconds.

    The rounding is done once, on the whole arc, rather than field by field.
    Carrying by hand afterwards looks right and is not: rounding the seconds
    up to sixty has to carry into the minutes, sixty minutes into the degrees,
    and thirty degrees into the *next sign* — and that last step is the one a
    hand-written carry forgets, so 29°59'59.7" Leo prints as "30°00'00" Leo",
    a degree that does not exist.

    Both forms are returned. The seconds are what the ephemeris actually says.
    The minute form drops the seconds rather than rounding them, because that
    is what Astro-Seek does and the client checks every figure against it: on
    their own traditional chart, fourteen of fifteen positions agree with the
    seconds simply cut off, and only seven agree if they are rounded. A chart
    read as "20°23'" is the twenty-third minute, not a figure nearest to it.
    """
    longitude %= 360.0

    def split(total, per_sign, per_degree):
        """Carry the whole way up, from the smallest unit to the sign."""
        units = int(total)
        sign_index, within = divmod(units, per_sign)
        degree, rest = divmod(within, per_degree)
        return int(sign_index) % 12, int(degree), rest

    # The seconds are rounded, because that is the last unit kept and the
    # arcsecond after it has to go somewhere.
    sign_index, degree, rest = split(math.floor(longitude * 3600.0 + 0.5), 108000, 3600)
    minute, second = divmod(int(rest), 60)

    # The minute form cuts the seconds off, which is what Astro-Seek shows.
    m_sign, m_degree, m_rest = split(longitude * 60.0, 1800, 60)
    m_minute = int(m_rest)

    return {
        "sign": SIGNS[sign_index],
        "sign_trigram": SIGN_TRIGRAMS[sign_index],
        "degree": degree,
        "minute": minute,
        "second": second,
        "formatted": f"{degree}°{minute:02d}'{second:02d}\" {SIGNS[sign_index]}",
        # Degrees and minutes only, the way a chart is normally printed.
        "sign_to_minute": SIGNS[m_sign],
        "degree_to_minute": m_degree,
        "minute_to_minute": m_minute,
        "formatted_to_minute": f"{m_degree}°{m_minute:02d}' {SIGNS[m_sign]}",
    }


def _motion(speed):
    """Classify a body's motion from its longitudinal speed.

    Stationary is checked before direction: at a station the sign of the speed
    is about to flip and is not meaningful on its own.
    """
    if abs(speed) < STATIONARY_THRESHOLD_DEG_PER_DAY:
        return "stationary"
    return "retrograde" if speed < 0 else "direct"


# Every body resolves between these years. The planets themselves reach a good
# deal further either side, on a different set of files, so the bound is only
# quoted as the span where a chart is complete, never as the planets' own.
COMPLETE_FROM = 1800
COMPLETE_TO = 2400


def _readable(exc):
    """What went wrong, without the server's filing system in it.

    swisseph reports a date it cannot reach by naming the data file it went
    looking for and the directory it searched, which tells a reader nothing
    and tells them where our disk is. How far the data reaches differs from
    one body to the next, so the message says the date is out of reach and
    leaves the arithmetic of which years to the page.
    """
    message = str(exc)
    if "not found" in message or ".se1" in message:
        return "the ephemeris does not reach this date."
    return (
        message.split(":")[-1].strip().rstrip(".").lower() + "."
        if ":" in message
        else "the position could not be calculated."
    )


def calculate_bodies(jd_ut):
    results = []
    for body in BODIES:
        try:
            values, _ = swe.calc_ut(jd_ut, body.swe_id, CALC_FLAGS)
        except swe.Error as exc:
            results.append(
                {
                    "code": body.code,
                    "trigram": body.trigram,
                    "name": body.name,
                    "error": _readable(exc),
                }
            )
            continue

        longitude, latitude, distance, speed_long = values[0], values[1], values[2], values[3]

        # The South Node is not a body swisseph returns; it sits exactly
        # opposite the North Node and shares its motion.
        if body.derived == "opposite":
            longitude = (longitude + 180.0) % 360.0
            latitude = -latitude

        motion = _motion(speed_long)
        results.append(
            {
                "code": body.code,
                "trigram": body.trigram,
                "name": body.name,
                "longitude": round(longitude, 6),
                "position": format_position(longitude),
                "latitude": round(latitude, 6),
                "distance_au": round(distance, 8),
                "speed_deg_per_day": round(speed_long, 6),
                "motion": motion,
                "retrograde": motion == "retrograde",
                "stationary": motion == "stationary",
            }
        )
    return results


def calculate_houses(jd_ut, latitude, longitude, system=DEFAULT_HOUSE_SYSTEM):
    system = system.upper()
    if system not in HOUSE_SYSTEMS:
        raise ValueError(
            f"Unknown house system {system!r}. Available: "
            + ", ".join(f"{k} ({v})" for k, v in HOUSE_SYSTEMS.items())
        )

    try:
        cusps, ascmc = swe.houses_ex(
            jd_ut, latitude, longitude, system.encode("ascii"), EPHEMERIS_FLAG
        )
    except swe.Error as exc:
        # Placidus and Koch divide the semi-arc between the horizon and the
        # meridian, which has no solution above the polar circles where a body
        # may never rise or set. Whole Sign and Regiomontanus are defined
        # everywhere, so point the caller at those rather than failing opaquely.
        if abs(latitude) > 66.0 and system in {"P", "K"}:
            raise ValueError(
                f"{HOUSE_SYSTEMS[system]} houses are undefined at latitude "
                f"{latitude}, beyond the polar circle. Use R (Regiomontanus), "
                f"C (Campanus) or W (Whole Sign) at this latitude."
            )
        raise ValueError(
            f"House calculation failed for {HOUSE_SYSTEMS[system]} at "
            f"latitude {latitude}, longitude {longitude}: {exc}"
        )

    return {
        "system": system,
        "system_name": HOUSE_SYSTEMS[system],
        "cusps": [
            {"house": i + 1, "longitude": round(c, 6), "position": format_position(c)}
            for i, c in enumerate(cusps[:12])
        ],
        "ascendant": {"longitude": round(ascmc[0], 6), "position": format_position(ascmc[0])},
        "midheaven": {"longitude": round(ascmc[1], 6), "position": format_position(ascmc[1])},
        "armc": round(ascmc[2], 6),
        "vertex": {"longitude": round(ascmc[3], 6), "position": format_position(ascmc[3])},
    }


def chart_for_utc(moment_utc, latitude, longitude, house_system):
    """Build a chart from a UTC moment and a place.

    The caller decides how that UTC moment was arrived at, whether from a city
    lookup or an explicit offset, so this stays free of timezone concerns.
    """
    jd_ut = julian_day(moment_utc)
    return {
        "julian_day_ut": round(jd_ut, 9),
        "ephemeris_source": EPHEMERIS_SOURCE,
        "stationary_threshold_deg_per_day": STATIONARY_THRESHOLD_DEG_PER_DAY,
        "bodies": calculate_bodies(jd_ut),
        "houses": calculate_houses(jd_ut, latitude, longitude, house_system),
    }


def calculate_chart(date_str, time_str, utc_offset_hours, latitude, longitude, house_system):
    """Chart from a local time and an explicit UTC offset."""
    moment_utc = to_utc(date_str, time_str, utc_offset_hours)
    chart = chart_for_utc(moment_utc, latitude, longitude, house_system)
    chart["input"] = {
        "date": date_str,
        "time": time_str,
        "utc_offset": utc_offset_hours,
        "latitude": latitude,
        "longitude": longitude,
        "house_system": house_system.upper(),
    }
    chart["utc"] = moment_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    return chart
