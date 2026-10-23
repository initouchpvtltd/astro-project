"""What the words in a formula mean.

Kept apart from the parser so the recognised aspects, dynamics and phases can
be read and extended without touching the grammar.
"""

import re

from ..constants import BODY_LOOKUP, SIGNS, SIGN_TRIGRAMS

# Aspect trigrams from the specification, with their angles.
ASPECT_TRIGRAMS = {
    "CNJ": 0.0,
    "SSX": 30.0,  # semi-sextile
    "DEC": 36.0,  # decile
    "NOV": 40.0,  # novile
    "SSQ": 45.0,  # semi-square
    "SXT": 60.0,
    "QNT": 72.0,  # quintile
    "SQR": 90.0,
    "TRI": 120.0,
    # The specification lists SQQ between TRI and QNX, which places it at the
    # sesqui-quadrate rather than the sesqui-quintile at 108.
    "SQQ": 135.0,
    "QNX": 150.0,  # quincunx
    "OPP": 180.0,
}

# Longer aliases people actually type.
ASPECT_ALIASES = {
    "CONJUNCTION": 0.0,
    "CONJ": 0.0,
    "SEXTILE": 60.0,
    "SQUARE": 90.0,
    "TRINE": 120.0,
    "OPPOSITION": 180.0,
    "QUINCUNX": 150.0,
    "SEMISEXTILE": 30.0,
    "SEMISQUARE": 45.0,
    "SESQUIQUADRATE": 135.0,
    "QUINTILE": 72.0,
    "BIQUINTILE": 144.0,
}

# Dynamics, appended to an aspect: 120AF is an applying trine, first body ahead.
DYNAMICS = {
    "A": "applying",
    "S": "separating",
    "F": "forward",
    "B": "back",
}

# Phases of movement, which may be combined as in "RS".
MOTION_PHASES = {
    "D": "direct",
    "R": "retrograde",
    "S": "stationary",
    "V": "fast",
}

PLANETARY_HOUR_WORDS = {"PLN_HOUR", "PLNHOUR"}

# Conditions that stand alone, naming no body of their own.
STANDALONE = {"MOONVOID": "MOONVOID", "MOON_VOID": "MOONVOID"}


def as_standalone(word):
    return STANDALONE.get(word.upper())

_HOUSE = re.compile(r"^H(\d{1,2})$", re.IGNORECASE)

# The Ascendant and Midheaven are points in their own right. The specification
# distinguishes them from the first and tenth cusps, which differ from them in
# Whole Sign and other non-quadrant systems.
ANGLES = {
    "ASC": "ASC",
    "ASCENDANT": "ASC",
    "AS": "ASC",
    "MC": "MC",
    "MIDHEAVEN": "MC",
    "DSC": "DSC",
    "DESC": "DSC",
    "IC": "IC",
}


def as_angle(word):
    return ANGLES.get(word.upper())

SIGN_LOOKUP = {}
for _index, (_name, _trigram) in enumerate(zip(SIGNS, SIGN_TRIGRAMS)):
    SIGN_LOOKUP[_trigram] = _index
    SIGN_LOOKUP[_name.upper()] = _index
    SIGN_LOOKUP[_name.upper()[:3]] = _index


def as_body(word):
    return BODY_LOOKUP.get(word.upper())


def as_sign(word):
    return SIGN_LOOKUP.get(word.upper())


def as_house(word):
    match = _HOUSE.match(word)
    if not match:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 12 else None


def as_aspect(word):
    """Return the angle for an aspect name, or None."""
    upper = word.upper()
    if upper in ASPECT_TRIGRAMS:
        return ASPECT_TRIGRAMS[upper]
    return ASPECT_ALIASES.get(upper)


def as_planetary_hour(word):
    return word.upper() in PLANETARY_HOUR_WORDS


def split_dynamics(word):
    """Separate trailing dynamics letters from an aspect name.

    'AF' on its own is dynamics. 'TRI' is an aspect. The awkward case is a word
    that could be either, so an aspect name always wins and only the remainder
    is read as dynamics.
    """
    upper = word.upper()
    if as_aspect(upper) is not None:
        return upper, ""

    # Down to and including 0, so a word that is nothing but dynamics letters
    # comes back with an empty aspect rather than being read as a name.
    for cut in range(len(upper), -1, -1):
        head, tail = upper[:cut], upper[cut:]
        if all(letter in DYNAMICS for letter in tail):
            if not head:
                return "", tail
            if as_aspect(head) is not None:
                return head, tail
    return upper, ""


def is_dynamics(word):
    upper = word.upper()
    return bool(upper) and all(letter in DYNAMICS for letter in upper)


def is_motion(word):
    upper = word.upper()
    return bool(upper) and all(letter in MOTION_PHASES for letter in upper)


_SEXAGESIMAL = re.compile(
    r"""^\s*(\d+(?:\.\d+)?)          # degrees
        (?:\s*[°:\s]\s*(\d+(?:\.\d+)?))?   # minutes
        (?:\s*['′:\s]\s*(\d+(?:\.\d+)?))?  # seconds
        \s*["″]?\s*$""",
    re.VERBOSE,
)


def parse_angle(text):
    """Read an angle written as degrees, decimals or sexagesimal.

    The spec allows 131, 119.9 and 49°39'19" in the same position.
    """
    match = _SEXAGESIMAL.match(text)
    if not match:
        raise ValueError(f"Could not read {text!r} as an angle")
    degrees = float(match.group(1))
    minutes = float(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return degrees + minutes / 60.0 + seconds / 3600.0


def parse_range(text):
    """Read a bracketed orb range: [131-133], [119.9-120.1], [49°39'19"-53°20'].

    Returns (low, high) in degrees.
    """
    inner = text.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    inner = inner.strip()

    # A minus between two angles is the separator. Split on the last one that
    # is not inside a sexagesimal group, which in practice means splitting on
    # the hyphen that has a digit on both sides.
    positions = [
        i
        for i, ch in enumerate(inner)
        if ch == "-" and i > 0 and inner[i - 1].isdigit() or ch == "-" and i > 0
    ]
    for position in positions:
        left, right = inner[:position], inner[position + 1 :]
        try:
            return parse_angle(left), parse_angle(right)
        except ValueError:
            continue

    # A single value is a range of zero width.
    value = parse_angle(inner)
    return value, value
