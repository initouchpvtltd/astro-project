"""Moon Void of Course.

The Moon is void of course when it will complete no further Ptolemaic aspect
to any of the traditional planets before it leaves the sign it is in. The
classical reading is that nothing comes of matters begun under it, which is
why horary astrologers check it before anything else.

Worked out arithmetically rather than by sampling. For each planet and each
aspect the exact point is a moving target, so the question is whether the Moon
catches it before reaching the end of the sign. Comparing the time to each
aspect against the time to the sign boundary answers that directly, and costs
a handful of divisions instead of a second scan through time.
"""

from .constants import MEAN_DAILY_MOTION

# Ptolemy's five. Traditional practice counts no others for this judgement.
PTOLEMAIC_ASPECTS = (0.0, 60.0, 90.0, 120.0, 180.0)

# The seven traditional planets, less the Moon itself.
CLASSICAL_PLANETS = ("SO", "ME", "VE", "MA", "JU", "SA")

MOON = "MO"


def _degrees_to_sign_end(longitude):
    """How far the Moon still has to travel in its current sign."""
    return 30.0 - (longitude % 30.0)


def _days_until(separation_now, closing_speed):
    """Days until a gap of this size closes at this rate, or None.

    A non-positive speed means the target is not being approached at all.
    """
    if closing_speed <= 0:
        return None
    return separation_now / closing_speed


def is_void(longitudes, speeds, planets=CLASSICAL_PLANETS, aspects=PTOLEMAIC_ASPECTS):
    """True when the Moon perfects no further aspect before changing sign."""
    moon = longitudes.get(MOON)
    if moon is None:
        return False

    moon_speed = speeds.get(MOON, MEAN_DAILY_MOTION[MOON])
    if moon_speed <= 0:
        # The Moon is never retrograde, so this means no usable speed.
        moon_speed = MEAN_DAILY_MOTION[MOON]

    days_to_boundary = _degrees_to_sign_end(moon) / moon_speed

    for code in planets:
        planet = longitudes.get(code)
        if planet is None:
            continue

        # The aspect point moves with the planet, so what matters is how fast
        # the Moon gains on it.
        closing = moon_speed - speeds.get(code, 0.0)

        for angle in aspects:
            for target in ((planet + angle) % 360.0, (planet - angle) % 360.0):
                ahead = (target - moon) % 360.0
                days = _days_until(ahead, closing)
                if days is not None and days <= days_to_boundary:
                    return False

    return True
