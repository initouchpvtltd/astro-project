"""Reference tables: bodies, signs and house systems.

Naming follows the ZET 9 Geo formula specification, which accepts a body as a
two-letter code (SO), a trigram (SUN) or a full name (Sun).
"""

import swisseph as swe

# Speed below which ZET marks a planet stationary. The client measured this as
# 8.78 arcseconds per day in his own charts: 8.78 / 3600 = 0.00244 deg/day.
STATIONARY_THRESHOLD_DEG_PER_DAY = 0.0024

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

SIGN_TRIGRAMS = [
    "ARI", "TAU", "GEM", "CNC", "LEO", "VIR",
    "LIB", "SCO", "SGR", "CAP", "AQR", "PSC",
]


class Body:
    """A calculable point, with the three notations ZET accepts."""

    def __init__(self, code, trigram, name, swe_id, derived=None):
        self.code = code
        self.trigram = trigram
        self.name = name
        self.swe_id = swe_id
        # Points swisseph does not return directly, e.g. the South Node, which
        # is always opposite the North Node.
        self.derived = derived


BODIES = [
    Body("SO", "SUN", "Sun", swe.SUN),
    Body("MO", "LUN", "Moon", swe.MOON),
    Body("ME", "MER", "Mercury", swe.MERCURY),
    Body("VE", "VEN", "Venus", swe.VENUS),
    Body("MA", "MAR", "Mars", swe.MARS),
    Body("JU", "JUP", "Jupiter", swe.JUPITER),
    Body("SA", "SAT", "Saturn", swe.SATURN),
    Body("UR", "URA", "Uranus", swe.URANUS),
    Body("NE", "NEP", "Neptune", swe.NEPTUNE),
    Body("PL", "PLU", "Pluto", swe.PLUTO),
    # The mean node, not the true one. They sit up to a degree and a half
    # apart, and the client reads this chart against Astro-Seek, whose
    # traditional chart prints the mean node and labels it "Node (M)".
    Body("KN", "NOD", "North Node", swe.MEAN_NODE),
    Body("SN", "SND", "South Node", swe.MEAN_NODE, derived="opposite"),
    Body("LI", "LIL", "Lilith", swe.MEAN_APOG),
    Body("SE", "SEL", "Selene", swe.WHITE_MOON),
    Body("PR", "PRO", "Proserpine", swe.PROSERPINA),
    Body("CH", "CHI", "Chiron", swe.CHIRON),
    # The Hamburg School bodies. Swiss Ephemeris carries orbital elements for
    # these, so they cost nothing to support even though traditional horary
    # does not use them.
    Body("CU", "CUP", "Cupido", swe.CUPIDO),
    Body("HA", "HAD", "Hades", swe.HADES),
    Body("ZE", "ZEU", "Zeus", swe.ZEUS),
    Body("KR", "KRO", "Kronos", swe.KRONOS),
    Body("AP", "APO", "Apollon", swe.APOLLON),
    Body("AD", "ADM", "Admetos", swe.ADMETOS),
    Body("VU", "VUL", "Volcanus", swe.VULKANUS),
    Body("PO", "POS", "Poseidon", swe.POSEIDON),
]

# Lookup accepts any of the three notations, case-insensitively. The spec also
# allows a planet name trimmed to three letters, which the trigram already
# covers for Sun through Pluto.
BODY_LOOKUP = {}
for _b in BODIES:
    for _key in (_b.code, _b.trigram, _b.name):
        BODY_LOOKUP[_key.upper()] = _b


HOUSE_SYSTEMS = {
    "R": "Regiomontanus",
    "P": "Placidus",
    "K": "Koch",
    "C": "Campanus",
    "O": "Porphyry",
    "B": "Alcabitius",
    "M": "Morinus",
    "T": "Topocentric",
    "W": "Whole Sign",
    "E": "Equal",
}

DEFAULT_HOUSE_SYSTEM = "R"  # Regiomontanus, the traditional choice for horary

# Average daily motion in degrees, used to decide what counts as "fast" for the
# 'V' phase. Defining fast relative to a body's own average avoids inventing a
# single threshold that would be meaningless across bodies as different as the
# Moon and Pluto.
MEAN_DAILY_MOTION = {
    "SO": 0.9856,
    "MO": 13.1764,
    "ME": 1.3833,
    "VE": 1.6021,
    "MA": 0.5240,
    "JU": 0.0831,
    "SA": 0.0335,
    "UR": 0.0117,
    "NE": 0.0060,
    "PL": 0.0040,
    "KN": 0.0529,
    "SN": 0.0529,
    "LI": 0.1114,
    "CH": 0.0500,
    "SE": 0.0200,
    "PR": 0.0070,
    # The Hamburg bodies move very slowly; these are rough averages.
    "CU": 0.0080,
    "HA": 0.0050,
    "ZE": 0.0040,
    "KR": 0.0030,
    "AP": 0.0025,
    "AD": 0.0020,
    "VU": 0.0018,
    "PO": 0.0016,
}
