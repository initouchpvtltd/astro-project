"""Lilly's table of essential dignities.

Five ways a planet can be at home in a degree, and two ways it can be a
stranger there. The tables are Lilly's as printed in *Christian Astrology*,
which is the table the client works from.

Terms are the one place astrologers genuinely disagree, so both sets are here:
the Egyptian terms, which is what Astro-Seek shows by default, and Ptolemy's,
which is the set printed in Lilly's own table. The caller picks.

A degree is worth scoring because that is how a traditional astrologer decides
which planet rules a question: the one with the most dignity in the degree.
"""

from .constants import SIGNS
from .planetary_hours import CHALDEAN_ORDER

# The seven planets of the tradition. The outer three were not discovered and
# have no dignities, so they are simply absent from every table below.
RULERS = ["MA", "VE", "ME", "MO", "SO", "ME", "VE", "MA", "JU", "SA", "SA", "JU"]

# A planet is in detriment in the sign opposite the one it rules.
DETRIMENTS = [RULERS[(index + 6) % 12] for index in range(12)]

# Exaltations carry a degree: the Sun is exalted in Aries, most strongly at
# the nineteenth. Fall is the same degree in the opposite sign.
EXALTATIONS = {
    "SO": (0, 19), "MO": (1, 3), "ME": (5, 15), "VE": (11, 27),
    "MA": (9, 28), "JU": (3, 15), "SA": (6, 21), "KN": (2, 3),
}
FALLS = {code: ((sign + 6) % 12, degree) for code, (sign, degree) in EXALTATIONS.items()}

# Triplicity, by element, as Lilly gives it. Lilly assigns Mars to the water
# triplicity both by day and by night, which is where his table parts company
# with Dorotheus; the specification names Lilly, so Lilly is what is used.
TRIPLICITIES = {
    "fire":  ("SO", "JU"),   # Aries, Leo, Sagittarius
    "earth": ("VE", "MO"),   # Taurus, Virgo, Capricorn
    "air":   ("SA", "ME"),   # Gemini, Libra, Aquarius
    "water": ("MA", "MA"),   # Cancer, Scorpio, Pisces
}
ELEMENTS = ["fire", "earth", "air", "water"] * 3

# Terms: five unequal stretches per sign, each with its own ruler. The figure
# is the degree the stretch ends at.
EGYPTIAN_TERMS = [
    [("JU", 6), ("VE", 12), ("ME", 20), ("MA", 25), ("SA", 30)],   # Aries
    [("VE", 8), ("ME", 14), ("JU", 22), ("SA", 27), ("MA", 30)],   # Taurus
    [("ME", 6), ("JU", 12), ("VE", 17), ("MA", 24), ("SA", 30)],   # Gemini
    [("MA", 7), ("VE", 13), ("ME", 19), ("JU", 26), ("SA", 30)],   # Cancer
    [("JU", 6), ("VE", 11), ("SA", 18), ("ME", 24), ("MA", 30)],   # Leo
    [("ME", 7), ("VE", 17), ("JU", 21), ("MA", 28), ("SA", 30)],   # Virgo
    [("SA", 6), ("ME", 14), ("JU", 21), ("VE", 28), ("MA", 30)],   # Libra
    [("MA", 7), ("VE", 11), ("ME", 19), ("JU", 24), ("SA", 30)],   # Scorpio
    [("JU", 12), ("VE", 17), ("ME", 21), ("SA", 26), ("MA", 30)],  # Sagittarius
    [("ME", 7), ("JU", 14), ("VE", 22), ("SA", 26), ("MA", 30)],   # Capricorn
    [("ME", 7), ("VE", 13), ("JU", 20), ("MA", 25), ("SA", 30)],   # Aquarius
    [("VE", 12), ("JU", 16), ("ME", 19), ("MA", 28), ("SA", 30)],  # Pisces
]

PTOLEMAIC_TERMS = [
    [("JU", 6), ("VE", 14), ("ME", 21), ("MA", 26), ("SA", 30)],   # Aries
    [("VE", 8), ("ME", 15), ("JU", 22), ("SA", 26), ("MA", 30)],   # Taurus
    [("ME", 7), ("JU", 14), ("VE", 21), ("SA", 25), ("MA", 30)],   # Gemini
    [("MA", 6), ("JU", 13), ("ME", 20), ("VE", 27), ("SA", 30)],   # Cancer
    [("SA", 6), ("ME", 13), ("VE", 19), ("JU", 25), ("MA", 30)],   # Leo
    [("ME", 7), ("VE", 13), ("JU", 18), ("SA", 24), ("MA", 30)],   # Virgo
    [("SA", 6), ("VE", 11), ("JU", 19), ("ME", 24), ("MA", 30)],   # Libra
    [("MA", 6), ("JU", 14), ("VE", 21), ("ME", 27), ("SA", 30)],   # Scorpio
    [("JU", 8), ("VE", 14), ("ME", 19), ("SA", 25), ("MA", 30)],   # Sagittarius
    [("VE", 6), ("ME", 12), ("JU", 19), ("MA", 25), ("SA", 30)],   # Capricorn
    [("SA", 6), ("ME", 12), ("VE", 20), ("JU", 25), ("MA", 30)],   # Aquarius
    [("VE", 8), ("JU", 14), ("ME", 19), ("MA", 26), ("SA", 30)],   # Pisces
]

TERM_SYSTEMS = {"egyptian": EGYPTIAN_TERMS, "ptolemaic": PTOLEMAIC_TERMS}
DEFAULT_TERMS = "egyptian"

# Lilly's scores. Negative for the two debilities, which is what lets a single
# number say whether a planet is at home in a degree or a stranger to it.
SCORES = {
    "domicile": 5, "exaltation": 4, "triplicity": 3, "term": 2, "face": 1,
    "detriment": -5, "fall": -4,
}

# The seven that have dignities at all.
DIGNIFIED = ("SO", "MO", "ME", "VE", "MA", "JU", "SA")


class UnknownTermSystem(ValueError):
    pass


def _face_ruler(sign, degree):
    """The ruler of a ten-degree face.

    The thirty-six faces are simply the Chaldean order running round the
    zodiac from Mars at the first degree of Aries, so they are generated
    rather than typed out: a table copied by hand is a table with a mistake
    in it.
    """
    index = sign * 3 + int(degree // 10)
    start = CHALDEAN_ORDER.index("MA")
    return CHALDEAN_ORDER[(start + index) % 7]


def _term_ruler(sign, degree, system):
    table = TERM_SYSTEMS.get((system or DEFAULT_TERMS).lower())
    if table is None:
        raise UnknownTermSystem(
            f"Unknown term system {system!r}. Use one of: "
            + ", ".join(sorted(TERM_SYSTEMS))
        )
    for ruler, ends_at in table[sign]:
        if degree < ends_at:
            return ruler
    return table[sign][-1][0]


def rulers_of(sign):
    """Every planet with a claim on a sign, for the Lord of the Year and such."""
    return {"domicile": RULERS[sign], "detriment": DETRIMENTS[sign]}


def dignities_for(code, longitude, is_day=True, term_system=None):
    """Which dignities a body holds in the degree it occupies.

    Returns the list of dignities, the ruler of each place whether the body
    holds it or not, and Lilly's score. A planet with no dignity anywhere is
    peregrine, which is a condition in its own right.
    """
    sign = int(longitude // 30) % 12
    degree = longitude % 30

    term = _term_ruler(sign, degree, term_system)
    face = _face_ruler(sign, degree)
    triplicity = TRIPLICITIES[ELEMENTS[sign]][0 if is_day else 1]

    held = []
    if code in DIGNIFIED or code in EXALTATIONS:
        if RULERS[sign] == code:
            held.append("domicile")
        if EXALTATIONS.get(code, (None,))[0] == sign:
            held.append("exaltation")
        if triplicity == code:
            held.append("triplicity")
        if term == code:
            held.append("term")
        if face == code:
            held.append("face")
        if DETRIMENTS[sign] == code:
            held.append("detriment")
        if FALLS.get(code, (None,))[0] == sign:
            held.append("fall")

    score = sum(SCORES[name] for name in held)
    # Peregrine is the absence of any relationship to the degree, not the
    # presence of a bad one. Skyscript, which the specification cites, is
    # explicit that a planet in its own detriment or fall is badly placed but
    # not a stranger, so those two rule peregrine out as surely as a dignity.
    peregrine = code in DIGNIFIED and not held

    return {
        "sign": SIGNS[sign],
        "dignities": held,
        "peregrine": peregrine,
        "score": score,
        "rulers": {
            "domicile": RULERS[sign],
            "exaltation": next(
                (c for c, (s, _) in EXALTATIONS.items() if s == sign and c in DIGNIFIED),
                None,
            ),
            "triplicity": triplicity,
            "term": term,
            "face": face,
            "detriment": DETRIMENTS[sign],
        },
        "term_system": (term_system or DEFAULT_TERMS).lower(),
    }
