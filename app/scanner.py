"""Searches time for the moments a formula holds.

ZET steps forward at an interval the user chooses, tests the condition at each
step, and reports the stretches where it held true. The output is a list of
realization intervals rather than single instants, and the precision is
whatever step was asked for. This follows the same model so results line up.

The scan only calculates what the formula actually asks about. Houses need a
location and sunrise needs an expensive rise-and-set search, so a formula that
mentions neither skips both. That is the difference between a year-long scan
taking a moment and taking minutes.
"""

import os
from datetime import datetime, timedelta, timezone

import swisseph as swe

from . import orbs, planetary_hours, void_of_course
from .constants import BODY_LOOKUP, DEFAULT_HOUSE_SYSTEM, MEAN_DAILY_MOTION
from .ephemeris import CALC_FLAGS, EPHEMERIS_FLAG, julian_day
from .formula import nodes
from .formula.evaluator import EvaluationError, Sky, evaluate
from .formula.parser import parse

MIN_STEP_SECONDS = int(os.environ.get("SCAN_MIN_STEP_SECONDS", "60"))
MAX_STEPS = int(os.environ.get("SCAN_MAX_STEPS", "200000"))
MAX_RANGE_DAYS = float(os.environ.get("SCAN_MAX_RANGE_DAYS", "36525"))  # a century


class ScanError(ValueError):
    """The search cannot be run as asked."""


# A body counts as stationary for only about an hour either side of its
# station, because the threshold is so tight. A step coarser than this can
# stride straight over one and report nothing.
_STATIONARY_SAFE_STEP_SECONDS = 1800

# How far ahead to look when deciding which way a stationary planet is turning.
_TURN_LOOKAHEAD_DAYS = 0.25


class Requirements:
    """What a formula needs calculated, so the rest can be skipped."""

    __slots__ = ("bodies", "houses", "planetary_hours", "stationary", "narrow")

    def __init__(self):
        self.bodies = set()
        self.houses = False
        self.planetary_hours = False
        self.stationary = False
        # Seconds the fastest narrow window stays open, or None.
        self.narrow = None


def requirements(node, found=None):
    """Walk the tree and note what it asks for."""
    found = found or Requirements()

    if isinstance(node, (nodes.And, nodes.Or)):
        requirements(node.left, found)
        requirements(node.right, found)
        return found
    if isinstance(node, nodes.Not):
        return requirements(node.operand, found)

    for attribute in ("entity", "left", "right"):
        entity = getattr(node, attribute, None)
        if isinstance(entity, nodes.Entity):
            found.bodies.update(body.code for body in entity.bodies)

    if isinstance(node, nodes.InHouse):
        found.houses = True
    # Cusps and the angles come from the same house calculation.
    for attribute in ("entity", "left", "right"):
        entity = getattr(node, attribute, None)
        if isinstance(entity, nodes.Entity) and (entity.cusps or entity.angles):
            found.houses = True
    if isinstance(node, nodes.Aspect) and node.orb_range is not None:
        low, high = node.orb_range
        width = max(high - low, 1e-6)
        # How long the window stays open depends on how fast the two sides
        # close on each other. Taking the fastest body is the safe estimate.
        speeds = [
            MEAN_DAILY_MOTION.get(body.code, 0.0)
            for entity in (node.left, node.right)
            for body in entity.bodies
        ]
        fastest = max(speeds) if speeds else 0.0
        if fastest > 0:
            seconds_open = width / fastest * 86400.0
            if found.narrow is None or seconds_open < found.narrow:
                found.narrow = seconds_open

    if isinstance(node, nodes.Motion) and "S" in [p.upper() for p in node.phases]:
        found.stationary = True
    if isinstance(node, nodes.MoonVoid):
        found.bodies.add(void_of_course.MOON)
        found.bodies.update(void_of_course.CLASSICAL_PLANETS)
    if isinstance(node, nodes.PlanetaryHour):
        found.planetary_hours = True
        # Every hour ruler is one of the seven traditional bodies.
        found.bodies.update(planetary_hours.CHALDEAN_ORDER)

    return found


def natal_sky(moment_utc, needs, latitude, longitude, house_system):
    """The birth chart, frozen.

    Built once for a whole scan rather than at every step, because it does not
    change. Speeds are kept at zero: a natal position does not move, which is
    exactly what makes a transit to it a findable event.
    """
    sky = _sky_at(moment_utc, needs, latitude, longitude, house_system)
    return Sky(
        sky.longitudes,
        {code: 0.0 for code in sky.speeds},
        sky.cusps,
        sky.ascendant,
        None,
        moment_utc,
        sky.midheaven,
    )


def _sky_at(moment, needs, latitude, longitude, house_system):
    jd = julian_day(moment)
    longitudes, speeds = {}, {}

    for code in needs.bodies:
        body = BODY_LOOKUP.get(code)
        if body is None:  # pragma: no cover - codes come from the parser
            continue
        values, _ = swe.calc_ut(jd, body.swe_id, CALC_FLAGS)
        longitude_value, speed = values[0], values[3]
        if body.derived == "opposite":
            longitude_value = (longitude_value + 180.0) % 360.0
        longitudes[code] = longitude_value
        speeds[code] = speed

    later_speeds = {}
    if needs.stationary:
        # One extra position per body, far enough ahead to show which way a
        # halting planet is turning but well inside a single station.
        for code in needs.bodies:
            body = BODY_LOOKUP.get(code)
            if body is None:
                continue
            values, _ = swe.calc_ut(jd + _TURN_LOOKAHEAD_DAYS, body.swe_id, CALC_FLAGS)
            later_speeds[code] = values[3]

    cusps = ascendant = midheaven = None
    if needs.houses:
        if latitude is None or longitude is None:
            raise ScanError(
                "This formula uses houses, so the search needs a location. "
                "Give a city, or coordinates."
            )
        raw_cusps, ascmc = swe.houses_ex(
            jd, latitude, longitude, house_system.upper().encode("ascii"), EPHEMERIS_FLAG
        )
        cusps = list(raw_cusps[:12])
        ascendant = ascmc[0]
        midheaven = ascmc[1]

    ruler = None
    if needs.planetary_hours:
        if latitude is None or longitude is None:
            raise ScanError(
                "This formula uses planetary hours, which need sunrise and "
                "sunset, so the search needs a location."
            )
        try:
            ruler = planetary_hours.ruler_at(moment, latitude, longitude)
        except planetary_hours.NoSunriseOrSunset:
            # Above the polar circles there is no hour to be in, so the
            # condition simply fails here rather than ending the scan.
            ruler = ""

    return Sky(
        longitudes, speeds, cusps, ascendant, ruler, moment, midheaven,
        later_speeds=later_speeds,
    )


def _uses_transits(node):
    """Whether any part of the formula carries the apostrophe."""
    if isinstance(node, (nodes.And, nodes.Or)):
        return _uses_transits(node.left) or _uses_transits(node.right)
    if isinstance(node, nodes.Not):
        return _uses_transits(node.operand)
    for attribute in ("entity", "left", "right"):
        entity = getattr(node, attribute, None)
        if isinstance(entity, nodes.Entity) and entity.transit:
            return True
    return False


def uses_transits(formula):
    """Whether a written formula would consult a birth chart at all.

    The endpoint asks before it resolves one, because a birth place costs a
    GeoNames lookup out of a limited daily allowance and a formula without an
    apostrophe would never read the result.
    """
    return _uses_transits(parse(formula))


def _mentions_places(node):
    """Whether any entity refers to a cusp or an angle, which need houses."""
    if isinstance(node, (nodes.And, nodes.Or)):
        return _mentions_places(node.left) or _mentions_places(node.right)
    if isinstance(node, nodes.Not):
        return _mentions_places(node.operand)
    for attribute in ("entity", "left", "right"):
        entity = getattr(node, attribute, None)
        if isinstance(entity, nodes.Entity) and (entity.cusps or entity.angles):
            return True
    return isinstance(node, nodes.InHouse)


def _validate(start, end, step_seconds):
    if end <= start:
        raise ScanError("The end of the range must come after the start.")

    if step_seconds < MIN_STEP_SECONDS:
        raise ScanError(
            f"The smallest step is {MIN_STEP_SECONDS} seconds. A finer step "
            "would take a long time without telling you much more."
        )

    span_days = (end - start).total_seconds() / 86400.0
    if span_days > MAX_RANGE_DAYS:
        raise ScanError(
            f"The range is {span_days:.0f} days, and the most that can be "
            f"searched at once is {MAX_RANGE_DAYS:.0f}."
        )

    steps = int((end - start).total_seconds() // step_seconds) + 1
    if steps > MAX_STEPS:
        suggested = int((end - start).total_seconds() / MAX_STEPS) + 1
        raise ScanError(
            f"That range and step would need {steps:,} calculations, and the "
            f"limit is {MAX_STEPS:,}. Use a step of at least {suggested:,} "
            "seconds, or search a shorter range."
        )
    return steps


def scan(
    formula,
    start,
    end,
    step_seconds=86400,
    latitude=None,
    longitude=None,
    house_system=DEFAULT_HOUSE_SYSTEM,
    orb_system=None,
    natal_moment=None,
    natal_latitude=None,
    natal_longitude=None,
):
    """Find every stretch within the range where the formula holds.

    Returns the intervals, as begin and end pairs, in the same shape ZET
    reports them.
    """
    node = parse(formula)
    needs = requirements(node)
    steps = _validate(start, end, step_seconds)

    natal = None
    if natal_moment is not None:
        # Transits are read against the birth place unless the search names
        # one of its own, which is how they are cast in practice.
        if latitude is None and natal_latitude is not None:
            latitude, longitude = natal_latitude, natal_longitude
        # A transit compares against the birth chart's houses as well as its
        # planets, so the natal chart always needs its own place.
        natal_latitude = natal_latitude if natal_latitude is not None else latitude
        natal_longitude = natal_longitude if natal_longitude is not None else longitude
        natal_needs = Requirements()
        natal_needs.bodies = set(needs.bodies)
        natal_needs.houses = needs.houses or _mentions_places(node)
        natal = natal_sky(
            natal_moment, natal_needs, natal_latitude, natal_longitude, house_system
        )
    elif _uses_transits(node):
        raise ScanError(
            "This formula uses the apostrophe, so it compares a moving body "
            "against a natal chart. Give the birth date, time and place with "
            "the search and it will run."
        )

    step = timedelta(seconds=step_seconds)
    intervals = []
    open_from = None
    last_true = None
    moment = start
    evaluated = 0

    while moment <= end:
        sky = _sky_at(moment, needs, latitude, longitude, house_system)
        sky.natal = natal
        try:
            holds = evaluate(node, sky, orb_system)
        except EvaluationError as exc:
            raise ScanError(str(exc)) from exc

        evaluated += 1
        if holds:
            if open_from is None:
                open_from = moment
            last_true = moment
        elif open_from is not None:
            intervals.append((open_from, last_true))
            open_from = None

        moment += step

    if open_from is not None:
        intervals.append((open_from, last_true))

    warnings = []
    if needs.narrow is not None and step_seconds > needs.narrow / 2:
        suggested = max(MIN_STEP_SECONDS, int(needs.narrow / 2))
        warnings.append(
            "The orb range in this formula is narrow enough that it stays open "
            f"for only about {needs.narrow / 60:.0f} minutes, so a step of "
            f"{step_seconds} seconds will miss most occurrences. Use about "
            f"{suggested} seconds instead."
        )

    if needs.stationary and step_seconds > _STATIONARY_SAFE_STEP_SECONDS:
        warnings.append(
            "A body is only stationary for roughly an hour, so a step of "
            f"{step_seconds} seconds may step over some stations entirely. "
            "Use 900 seconds or less to catch them all."
        )

    return {
        "formula": formula,
        "reading": node.describe(),
        "warnings": warnings,
        "natal_chart": (
            natal_moment.strftime("%Y-%m-%dT%H:%M:%SZ") if natal_moment else None
        ),
        "range": {
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "step_seconds": step_seconds,
        },
        "steps_evaluated": evaluated,
        "orb_system": (orb_system or orbs.DEFAULT_SYSTEM),
        "found": len(intervals),
        "intervals": [
            {
                "begin": begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": finish.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_hours": round(
                    (finish - begin).total_seconds() / 3600.0 + step_seconds / 3600.0, 3
                ),
            }
            for begin, finish in intervals
        ],
    }
