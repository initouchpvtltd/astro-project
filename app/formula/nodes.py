"""The tree a parsed formula becomes.

Every node answers the same question: is this true at a given moment? The
evaluator walks the tree and asks each node in turn, so adding a new kind of
condition means adding a node and an evaluator case, not touching the parser's
structure.
"""


class Node:
    """Base class. Subclasses are plain data; evaluation lives elsewhere."""

    __slots__ = ()

    def describe(self):
        """Plain-English rendering, used in API responses and error messages."""
        raise NotImplementedError


class Entity(Node):
    """One or more calculable points.

    ZET lets a position be a set or a range, so SUN-PLU means the ten bodies
    from the Sun to Pluto and SO,MO,ME means those three. A condition holds if
    it holds for any member, which is why this is always a list even when it
    carries one item.

    A house cusp is also a point an aspect can be made to, as in SO.0.H1 for
    the Sun conjunct the Ascendant. The specification forbids a cusp forming a
    set, so cusps and bodies never mix in one entity.
    """

    __slots__ = ("bodies", "cusps", "angles", "transit", "source")

    def __init__(self, bodies=(), cusps=(), angles=(), transit=False, source=""):
        self.bodies = list(bodies)
        self.cusps = list(cusps)  # 1-based house numbers used as points
        self.angles = list(angles)  # ASC, MC, DSC, IC
        # The apostrophe marks a transiting body against a natal chart. Parsed
        # so the formula is understood, but dual charts are phase two, so the
        # evaluator refuses it rather than quietly ignoring the mark.
        self.transit = transit
        self.source = source

    def describe(self):
        if self.angles:
            names = ", ".join(self.angles)
        elif self.cusps:
            names = ", ".join(f"cusp {c}" for c in self.cusps)
        else:
            names = ", ".join(b.name for b in self.bodies)
        # The apostrophe is how ZET writes a transit and how the formula box
        # takes it. Read back it becomes a word, because "Mars'" is a mark to
        # anyone who already knows the notation and nothing to anyone else.
        return f"Transiting {names}" if self.transit else names


class Aspect(Node):
    """An angular relationship: Sun.120AF.Lun."""

    __slots__ = ("left", "right", "angles", "dynamics", "orb_range", "source")

    def __init__(self, left, right, angles, dynamics=None, orb_range=None, source=""):
        self.left = left
        self.right = right
        self.angles = list(angles)  # degrees, e.g. [120]
        self.dynamics = dynamics or ""  # any of A, S, F, B
        self.orb_range = orb_range  # (low, high) in degrees, overriding the orb table
        self.source = source

    # The five Ptolemaic angles have names an astrologer reads faster than a
    # figure. Anything else stays in degrees, because there is no word for it.
    NAMED_ANGLES = {
        0.0: "conjunct", 60.0: "sextile", 90.0: "square",
        120.0: "trine", 180.0: "opposite",
    }

    def describe(self):
        # A formula that names its own range is read back as that range. The
        # midpoint alone would be a different, and much looser, condition:
        # [0-0.1] and 0.05 look the same written down but only one of them is
        # what the astrologer asked for.
        if self.orb_range is not None:
            low, high = self.orb_range
            angles = f"{low:g}\u2013{high:g}\u00b0"
        else:
            angles = " or ".join(
                self.NAMED_ANGLES.get(float(a), f"{a:g}\u00b0") for a in self.angles
            )

        left, right = self.left.describe(), self.right.describe()
        # When one side transits and the other does not, the still side belongs
        # to the birth chart. Naming it is what turns the formula into the
        # sentence the client wrote out himself: transiting Mars square natal
        # Saturn.
        moving = getattr(self.left, "transit", False), getattr(self.right, "transit", False)
        if moving == (True, False):
            right = f"natal {right}"
        elif moving == (False, True):
            left = f"natal {left}"

        detail = f" [{self.dynamics}]" if self.dynamics else ""
        return f"{left} {angles} {right}{detail}"


class InSign(Node):
    """A body occupying a sign: Sun.Ari, or a set, Sun.Ari,Leo,Sgr.

    A sign may carry a degree portion, so Sun.Ari[29-30] means only the last
    degree of Aries. The specification writes a single figure as the degree
    ending there, so ARI[30] is 29 to 30 degrees.
    """

    __slots__ = ("entity", "signs", "portions", "source")

    def __init__(self, entity, signs, portions=None, source=""):
        self.entity = entity
        self.signs = list(signs)  # zero-based sign indexes
        # Parallel to signs: (low, high) degrees within the sign, or None.
        self.portions = list(portions) if portions else [None] * len(self.signs)
        self.source = source

    def describe(self):
        from ..constants import SIGNS

        parts = []
        for index, sign in enumerate(self.signs):
            portion = self.portions[index] if index < len(self.portions) else None
            if portion:
                parts.append(f"{SIGNS[sign]} {portion[0]:g}\u2013{portion[1]:g}\u00b0")
            else:
                parts.append(SIGNS[sign])
        return f"{self.entity.describe()} in {', '.join(parts)}"


class InHouse(Node):
    """A body occupying a house: Mar.H7."""

    __slots__ = ("entity", "houses", "source")

    def __init__(self, entity, houses, source=""):
        self.entity = entity
        self.houses = list(houses)  # 1-based house numbers
        self.source = source

    def describe(self):
        numbers = ", ".join(str(h) for h in self.houses)
        return f"{self.entity.describe()} in house {numbers}"


class Motion(Node):
    """Direction or speed: Mer.S, Ura.RS.

    The spec allows combinations, so 'RS' means retrograde and stationary. All
    named phases must hold together.
    """

    __slots__ = ("entity", "phases", "source")

    def __init__(self, entity, phases, source=""):
        self.entity = entity
        self.phases = list(phases)  # any of D, R, S, V
        self.source = source

    def describe(self):
        words = {"D": "direct", "R": "retrograde", "S": "stationary", "V": "fast"}
        named = " and ".join(words.get(p, p) for p in self.phases)
        return f"{self.entity.describe()} {named}"


class PlanetaryHour(Node):
    """Whether the moment falls in a given body's planetary hour."""

    __slots__ = ("entity", "source")

    def __init__(self, entity, source=""):
        self.entity = entity
        self.source = source

    def describe(self):
        return f"in the planetary hour of {self.entity.describe()}"


class Precedes(Node):
    """One body earlier in the zodiac than another: SO.<.MO, a waning Moon."""

    __slots__ = ("left", "right", "source")

    def __init__(self, left, right, source=""):
        self.left = left
        self.right = right
        self.source = source

    def describe(self):
        return f"{self.left.describe()} before {self.right.describe()} in the zodiac"


class MoonVoid(Node):
    """The Moon completes no further aspect before leaving its sign."""

    __slots__ = ("source",)

    def __init__(self, source=""):
        self.source = source

    def describe(self):
        return "Moon void of course"


class And(Node):
    __slots__ = ("left", "right")

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def describe(self):
        return f"({self.left.describe()} AND {self.right.describe()})"


class Or(Node):
    __slots__ = ("left", "right")

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def describe(self):
        return f"({self.left.describe()} OR {self.right.describe()})"


class Not(Node):
    __slots__ = ("operand",)

    def __init__(self, operand):
        self.operand = operand

    def describe(self):
        return f"NOT {self.operand.describe()}"
