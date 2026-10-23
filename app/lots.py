"""The seven Hermetic Lots.

A lot is a point measured off the Ascendant: take the arc from one body to
another and lay it out again from the degree rising. Nothing is observed
there, which is why they are points rather than bodies, but the tradition
treats them as places a planet can rule and a transit can cross.

Every one of them reverses between a day birth and a night birth. Fortune
and Spirit simply trade formulas; the rest are built on those two, so the
sect decides the whole set. Getting the sect wrong puts every lot in the
wrong half of the chart, so it is computed from the Sun's own position
rather than from the clock.
"""

from .constants import BODY_LOOKUP, SIGNS
from .ephemeris import format_position


def _readable(name):
    """A formula reads better as "Moon to Sun" than as "MO to SO"."""
    if name in ("FORTUNE", "SPIRIT"):
        return f"Lot of {name.title()}"
    body = BODY_LOOKUP.get(name)
    return body.name if body else name

# Each lot as its day formula, (from, to): by day the lot falls at the
# Ascendant plus the arc from the first to the second, and by night that arc
# is measured the other way. "FORTUNE" and "SPIRIT" stand for the two lots
# already worked out, which is how the later five are defined.
FORMULAS = [
    ("fortune", "Lot of Fortune", "SO", "MO"),
    ("spirit", "Lot of Spirit", "MO", "SO"),
    ("eros", "Lot of Eros", "SPIRIT", "VE"),
    ("victory", "Lot of Victory", "SPIRIT", "JU"),
    ("necessity", "Lot of Necessity", "ME", "FORTUNE"),
    ("courage", "Lot of Courage", "MA", "FORTUNE"),
    ("nemesis", "Lot of Nemesis", "SA", "FORTUNE"),
]


def is_day_birth(sun_longitude, ascendant):
    """Whether the Sun was above the horizon.

    Measured as the Sun's distance round the wheel from the Ascendant: the
    half from the Ascendant to the Descendant going backwards through the
    tenth is the day half. This is the chart's own answer, so it needs no
    sunrise table and it stays right at any latitude.
    """
    return 180.0 < (sun_longitude - ascendant) % 360.0 <= 360.0


def _resolve(name, longitudes, found):
    if name in found:
        return found[name]
    return longitudes.get(name)


def calculate(longitudes, ascendant, is_day):
    """Every lot, in the order the later ones depend on the earlier."""
    found, results = {}, []
    for key, name, first, second in FORMULAS:
        a = _resolve(first, longitudes, found)
        b = _resolve(second, longitudes, found)
        if a is None or b is None:
            continue

        # By day the arc runs from the first body to the second, by night the
        # reverse. The Ascendant is where that arc is laid down again.
        arc = (b - a) if is_day else (a - b)

        longitude = (ascendant + arc) % 360.0

        found[key.upper()] = longitude
        results.append(
            {
                "key": key,
                "name": name,
                "longitude": round(longitude, 6),
                "position": format_position(longitude),
                "formula": (
                    f"{_readable(first)} to {_readable(second)}" if is_day
                    else f"{_readable(second)} to {_readable(first)}"
                ),
            }
        )
    return results


def for_chart(chart):
    """The lots for a cast chart, with the sect it was judged by."""
    longitudes = {
        body["code"]: body["longitude"]
        for body in chart["bodies"]
        if "error" not in body
    }
    ascendant = chart["houses"]["ascendant"]["longitude"]
    sun = longitudes.get("SO")
    if sun is None:
        return None

    day = is_day_birth(sun, ascendant)
    return {
        "sect": "day" if day else "night",
        "lots": calculate(longitudes, ascendant, day),
    }
