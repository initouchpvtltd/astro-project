"""Asks a parsed formula whether it is true at a given moment.

The evaluator is deliberately stateless: it takes a tree and a snapshot of the
sky, and answers yes or no. The scanner supplies the snapshots. Keeping those
two apart is what lets the same tree be tested at ten thousand moments without
being rebuilt.
"""

from .. import orbs, void_of_course
from ..constants import MEAN_DAILY_MOTION, STATIONARY_THRESHOLD_DEG_PER_DAY
from . import nodes

# How far ahead to look when deciding whether an aspect is closing or opening.
# Short enough that no body changes direction within it, long enough that the
# difference in separation is well clear of floating point noise.
_LOOKAHEAD_DAYS = 0.01


class EvaluationError(ValueError):
    """The formula cannot be evaluated against this chart."""


class Sky:
    """A snapshot: where everything is, and how fast it is moving.

    Built once per moment by the scanner and handed to the evaluator.

    When a natal chart is supplied the sky becomes a dual chart, and the
    apostrophe starts to mean something. ZET reads a marked body as the
    transiting one and an unmarked body as the natal one, so PL'.120.MO is
    transiting Pluto trine the natal Moon. Without a natal chart every body is
    read from the moving sky, which is the mundane case.
    """

    __slots__ = (
        "longitudes", "speeds", "cusps", "ascendant", "midheaven",
        "hour_ruler", "moment", "natal", "later_speeds",
    )

    def __init__(
        self, longitudes, speeds, cusps=None, ascendant=None, hour_ruler=None,
        moment=None, midheaven=None, natal=None, later_speeds=None,
    ):
        self.longitudes = longitudes  # body code -> degrees
        self.speeds = speeds  # body code -> degrees per day
        self.cusps = cusps  # list of 12 cusp longitudes, or None
        self.ascendant = ascendant
        self.midheaven = midheaven
        self.hour_ruler = hour_ruler  # body code ruling the planetary hour
        self.moment = moment
        # Another Sky, frozen at the moment of birth, or None.
        self.natal = natal
        # Speeds a little later, calculated only when a formula asks about a
        # station. Comparing them against the current speeds says which way a
        # halting planet is about to turn.
        self.later_speeds = later_speeds or {}

    def longitude(self, code):
        try:
            return self.longitudes[code]
        except KeyError:
            raise EvaluationError(f"No position calculated for {code}")

    def speed(self, code):
        return self.speeds.get(code, 0.0)


def evaluate(node, sky, orb_system=None):
    """True when the formula holds in this sky."""
    kind = type(node)

    if kind is nodes.And:
        return evaluate(node.left, sky, orb_system) and evaluate(
            node.right, sky, orb_system
        )
    if kind is nodes.Or:
        return evaluate(node.left, sky, orb_system) or evaluate(
            node.right, sky, orb_system
        )
    if kind is nodes.Not:
        return not evaluate(node.operand, sky, orb_system)

    if kind is nodes.Aspect:
        return _aspect(node, sky, orb_system)
    if kind is nodes.InSign:
        return _in_sign(node, sky)
    if kind is nodes.InHouse:
        return _in_house(node, sky)
    if kind is nodes.Motion:
        return _motion(node, sky)
    if kind is nodes.PlanetaryHour:
        return _planetary_hour(node, sky)
    if kind is nodes.Precedes:
        return _precedes(node, sky)
    if kind is nodes.MoonVoid:
        return void_of_course.is_void(sky.longitudes, sky.speeds)

    raise EvaluationError(f"Cannot evaluate {kind.__name__}")


def _chart_for(entity, sky):
    """Which of the two charts an entity refers to.

    In a dual chart the apostrophe selects the moving sky and a bare name the
    natal one. With no natal chart there is only one sky to read from.
    """
    if sky.natal is None:
        return sky
    return sky if entity.transit else sky.natal


def _codes(entity, sky=None):
    """Body codes only. Used where a cusp makes no sense, such as motion."""
    if sky is None or sky.natal is None:
        _check_transit(entity)
    if entity.cusps or entity.angles:
        raise EvaluationError(
            "A cusp or angle has no motion or planetary hour of its own. "
            "They can only take part in aspects and sign placements."
        )
    return [body.code for body in entity.bodies]


def _check_transit(entity):
    if entity.transit:
        raise EvaluationError(
            "This formula uses the apostrophe, so it compares a moving body "
            "against a natal chart. Give the birth date, time and place with "
            "the search and it will run."
        )


def _points(entity, sky):
    """Every point an entity stands for, as (code, longitude, speed).

    A cusp is a point like any other for the purpose of an aspect, but it does
    not move of its own accord, so its speed is zero. A natal point does not
    move either, which is what makes a transit to it findable.
    """
    if sky.natal is None:
        _check_transit(entity)
    chart = _chart_for(entity, sky)
    natal = chart is not sky
    sky = chart

    for angle in entity.angles:
        if sky.ascendant is None:
            raise EvaluationError(
                "This formula uses the Ascendant or Midheaven, which need a "
                "location. Give a city or coordinates with the search."
            )
        base = sky.ascendant if angle in ("ASC", "DSC") else sky.midheaven
        if base is None:
            raise EvaluationError(
                "The Midheaven needs a location. Give a city or coordinates."
            )
        opposite = angle in ("DSC", "IC")
        yield angle, (base + 180.0) % 360.0 if opposite else base, 0.0

    for house in entity.cusps:
        if not sky.cusps:
            raise EvaluationError(
                "This formula aspects a house cusp, which needs a location. "
                "Give a city or coordinates with the search."
            )
        yield f"H{house}", sky.cusps[house - 1], 0.0

    for body in entity.bodies:
        # A natal position is fixed, so it contributes no motion of its own.
        speed = 0.0 if natal else sky.speed(body.code)
        label = f"{body.code}'" if not natal and entity.transit else body.code
        yield label, sky.longitude(body.code), speed


def _aspect(node, sky, orb_system):
    """A set on either side means any pairing may satisfy the aspect."""
    # Checked before resolving anything, so a formula that cannot be supported
    # says so rather than failing on whichever body happens to resolve first.
    if sky.natal is None:
        _check_transit(node.left)
        _check_transit(node.right)

    rights = list(_points(node.right, sky))
    for left in _points(node.left, sky):
        for right in rights:
            if left[0] == right[0]:
                continue  # a point cannot aspect itself
            if _pair_in_aspect(node, left, right, orb_system):
                return True
    return False


def _pair_in_aspect(node, left, right, orb_system):
    left_code, left_longitude, left_speed = left
    right_code, right_longitude, right_speed = right
    actual = orbs.separation(left_longitude, right_longitude)

    for angle in node.angles:
        if node.orb_range is not None:
            low, high = node.orb_range
            within = low <= actual <= high
        else:
            allowance = orbs.allowance(
                left_code.rstrip("'"), right_code.rstrip("'"), angle, orb_system
            )
            within = abs(actual - angle) <= allowance

        if not within:
            continue
        if not node.dynamics:
            return True
        if _dynamics_hold(node.dynamics, left, right, angle, actual):
            return True

    return False


def _dynamics_hold(dynamics, left, right, angle, actual):
    """Check the A, S, F and B letters. All present letters must hold."""
    _, left_longitude, left_speed = left
    _, right_longitude, right_speed = right

    if "A" in dynamics or "S" in dynamics:
        later = orbs.separation(
            left_longitude + left_speed * _LOOKAHEAD_DAYS,
            right_longitude + right_speed * _LOOKAHEAD_DAYS,
        )
        closing = abs(later - angle) < abs(actual - angle)
        if "A" in dynamics and not closing:
            return False
        if "S" in dynamics and closing:
            return False

    if "F" in dynamics or "B" in dynamics:
        # Positive means the first body is ahead of the second in the zodiac.
        ahead = orbs.signed_separation(left_longitude, right_longitude) > 0
        if "F" in dynamics and not ahead:
            return False
        if "B" in dynamics and ahead:
            return False

    return True


def _in_sign(node, sky):
    chart = _chart_for(node.entity, sky)
    for code in _codes(node.entity, sky):
        longitude = chart.longitude(code) % 360.0
        sign = int(longitude // 30)
        within_sign = longitude - sign * 30.0
        for index, wanted in enumerate(node.signs):
            if sign != wanted:
                continue
            portion = node.portions[index] if index < len(node.portions) else None
            if portion is None:
                return True
            low, high = portion
            if low <= within_sign < high:
                return True
    return False


def _in_house(node, sky):
    chart = _chart_for(node.entity, sky)
    if not chart.cusps:
        raise EvaluationError(
            "This formula uses houses, which need a location. Give a city or "
            "coordinates with the search."
        )
    for code in _codes(node.entity, sky):
        if _house_of(chart.longitude(code), chart.cusps) in node.houses:
            return True
    return False


def _house_of(longitude, cusps):
    """Which house a longitude falls in.

    Houses are unequal in most systems and the twelfth wraps past 0 degrees, so
    each span is measured forward from its own cusp rather than compared
    numerically.
    """
    longitude %= 360.0
    for index in range(12):
        start = cusps[index] % 360.0
        end = cusps[(index + 1) % 12] % 360.0
        span = (end - start) % 360.0
        offset = (longitude - start) % 360.0
        if offset < span or (span == 0 and offset == 0):
            return index + 1
    return 12  # pragma: no cover - the spans always cover the circle


def _motion(node, sky):
    chart = _chart_for(node.entity, sky)
    phases = [p.upper() for p in node.phases]
    for code in _codes(node.entity, sky):
        speed = chart.speed(code)
        later = chart.later_speeds.get(code)
        turning = None if later is None else later - speed
        if all(
            _phase_holds(phase, code, speed, phases, turning) for phase in phases
        ):
            return True
    return False


def _phase_holds(phase, code, speed, all_phases=(), turning=None):
    """Whether one motion letter holds.

    The specification allows combinations such as "DS" and "RS", which name the
    two kinds of station: a planet halting before it turns retrograde, and one
    halting before it resumes direct motion. So when S appears alongside D or
    R, the direction letter describes which way the turn goes rather than
    asserting the planet is currently moving that way. Read strictly the
    combination could never be true, since a stationary planet is by definition
    not moving in either direction.
    """
    stationary = abs(speed) < STATIONARY_THRESHOLD_DEG_PER_DAY

    if phase == "S":
        return stationary
    if phase == "R":
        if "S" in all_phases:
            # A retrograde station is a planet slowing to a halt on its way
            # backwards, so the speed is falling. Using the sign of the speed
            # alone would match both kinds of station, since it passes through
            # zero either way.
            return turning is not None and turning < 0
        return not stationary and speed < 0
    if phase == "D":
        if "S" in all_phases:
            return turning is not None and turning > 0
        return not stationary and speed > 0
    if phase == "V":
        mean = MEAN_DAILY_MOTION.get(code)
        return mean is not None and abs(speed) > mean
    raise EvaluationError(f"Unknown motion phase {phase!r}")


def _planetary_hour(node, sky):
    if sky.hour_ruler is None:
        raise EvaluationError(
            "Planetary hours need a location, for sunrise and sunset. Give a "
            "city or coordinates with the search."
        )
    return sky.hour_ruler in _codes(node.entity, sky)


def _precedes(node, sky):
    """Left earlier in the zodiac than right, taking the short way round."""
    if sky.natal is None:
        _check_transit(node.left)
        _check_transit(node.right)
    left_chart = _chart_for(node.left, sky)
    right_chart = _chart_for(node.right, sky)
    for left in _codes(node.left, sky):
        for right in _codes(node.right, sky):
            if left == right:
                continue
            ahead = (right_chart.longitude(right) - left_chart.longitude(left)) % 360.0
            if 0 < ahead < 180:
                return True
    return False
