"""How close counts as an aspect.

Two systems, because the client works with one and his ZET file carries the
other:

- **moiety**, the traditional approach. Each body has its own orb and the
  allowance between two of them is the average. Sun 15 and Moon 12 give 13°30'.
  These figures match William Lilly's own orbs in Christian Astrology, which is
  why they suit horary.

- **fixed**, from the ZET aspect file. The orb belongs to the aspect rather
  than the pair: 9° for the Sun and Moon and 8.5° for Mercury through Pluto on
  the major aspects, much tighter on the minor ones.

Both are selectable per request. Bodies the tables do not name fall back to a
default rather than raising, so a formula is never refused over an orb.
"""

import os

MOIETY_SYSTEM = "moiety"
FIXED_SYSTEM = "fixed"
SYSTEMS = (MOIETY_SYSTEM, FIXED_SYSTEM)
DEFAULT_SYSTEM = os.environ.get("DEFAULT_ORB_SYSTEM", MOIETY_SYSTEM)

# Orb per body, from the client's table. The bold figures there are Lilly's.
MOIETY_ORBS = {
    "SO": 15.0,
    "MO": 12.0,
    "ME": 7.0,
    "VE": 7.0,
    "MA": 7.0,
    "JU": 9.0,
    "SA": 9.0,
    "UR": 5.0,
    "NE": 5.0,
    "PL": 5.0,
}

# Points the client's table does not cover. Lilly predates the outer planets
# and says nothing about the nodes, so these are a conservative default rather
# than a tradition, and can be changed without touching code.
DEFAULT_MOIETY = float(os.environ.get("DEFAULT_MOIETY_ORB", "5"))

# Orbs per aspect, read from the ZET file _Volokontsev_Horar.a2. Each entry is
# (orb for Sun and Moon, orb for Mercury through Pluto).
FIXED_ORBS = {
    0.0: (9.0, 8.5),
    30.0: (1.5, 1.0),
    36.0: (1.5, 1.0),
    40.0: (1.5, 1.0),
    45.0: (2.0, 2.0),
    60.0: (9.0, 8.5),
    72.0: (2.5, 2.0),
    80.0: (2.0, 1.0),
    90.0: (9.0, 8.5),
    108.0: (2.0, 1.5),
    120.0: (9.0, 8.5),
    135.0: (2.5, 2.0),
    144.0: (2.5, 2.0),
    150.0: (3.0, 2.5),
    180.0: (9.0, 8.5),
}

DEFAULT_FIXED = float(os.environ.get("DEFAULT_FIXED_ORB", "1"))

_LUMINARIES = ("SO", "MO")


class UnknownOrbSystem(ValueError):
    pass


def moiety(code):
    return MOIETY_ORBS.get(code, DEFAULT_MOIETY)


def _fixed_for(code, angle):
    pair = FIXED_ORBS.get(round(float(angle), 4))
    if pair is None:
        return DEFAULT_FIXED
    luminary_orb, planet_orb = pair
    return luminary_orb if code in _LUMINARIES else planet_orb


def allowance(first_code, second_code, angle, system=None):
    """The orb permitted between two bodies for a given aspect.

    Under moieties the pair decides and the aspect is irrelevant. Under the
    fixed system the aspect decides, and where the two bodies disagree the
    wider of the two applies, which is the usual reading.
    """
    system = (system or DEFAULT_SYSTEM).lower()

    if system == MOIETY_SYSTEM:
        return (moiety(first_code) + moiety(second_code)) / 2.0

    if system == FIXED_SYSTEM:
        return max(_fixed_for(first_code, angle), _fixed_for(second_code, angle))

    raise UnknownOrbSystem(
        f"Unknown orb system {system!r}. Use one of: " + ", ".join(SYSTEMS)
    )


def separation(first_longitude, second_longitude):
    """Shortest angular distance between two longitudes, 0 to 180 degrees.

    Going the short way round matters: 350° and 10° are 20° apart, not 340°.
    """
    difference = abs(first_longitude - second_longitude) % 360.0
    return 360.0 - difference if difference > 180.0 else difference


def signed_separation(first_longitude, second_longitude):
    """Separation carrying direction, in the range -180 to 180.

    Positive means the first body is ahead of the second. Used to decide
    whether an aspect is applying or separating, where the sign is the point.
    """
    difference = (first_longitude - second_longitude + 180.0) % 360.0 - 180.0
    return difference
