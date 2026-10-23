"""Turns a token stream into a tree.

The grammar, in the order the methods below follow:

    formula    := expression
    expression := unary (('&' | '|') unary)*      left to right, equal weight
    unary      := '^' unary | primary
    primary    := '(' expression ')' | condition
    condition  := entity '.' predicate ['.' entity]
    entity     := name ("'" )? (('-' | ',') name)*

The equal precedence of AND and OR is unusual and deliberate: the
specification states that "&" and "|" are executed left to right as they
occur, so `a & b | c` means `(a & b) | c` and never `a & (b | c)`. Treating OR
as weaker, the way most languages do, would silently change the meaning of
formulas written against ZET.
"""

from . import definitions as defs
from . import lexer, vocabulary
from .lexer import FormulaSyntaxError
from .nodes import (
    And,
    MoonVoid,
    Aspect,
    Entity,
    InHouse,
    InSign,
    Motion,
    Not,
    Or,
    PlanetaryHour,
    Precedes,
)


def _span(first, last, count, offset):
    """The members that follow `first` up to `last`, the long way if need be.

    Signs and houses are both rings, so Pis-Tau means Pisces, Aries, Taurus and
    H11-H2 means the eleventh, twelfth, first and second. The run is returned
    without its first member, which the caller already holds.
    """
    steps = (last - first) % count
    return [((first + step) % count) + offset for step in range(1, steps + 1)]


class Parser:
    def __init__(self, text, variables=None):
        self.text = text
        self.tokens = lexer.tokenize(text)
        self.index = 0
        # Already-parsed logical variables, spliced in where their name appears.
        self.variables = variables or {}

    # -- token handling ----------------------------------------------------

    @property
    def current(self):
        return self.tokens[self.index]

    def advance(self):
        token = self.tokens[self.index]
        self.index += 1
        return token

    def accept(self, *kinds):
        if self.current.kind in kinds:
            return self.advance()
        return None

    def expect(self, kind, description):
        token = self.accept(kind)
        if token is None:
            raise self.error(f"Expected {description}")
        return token

    def error(self, message):
        return FormulaSyntaxError(message, self.current.position, self.text)

    # -- grammar -----------------------------------------------------------

    def parse(self):
        if self.current.kind == lexer.END:
            raise FormulaSyntaxError("The formula is empty.")
        node = self.expression()
        if self.current.kind != lexer.END:
            raise self.error(f"Unexpected {self.current.value!r}")
        return node

    def expression(self):
        node = self.unary()
        while True:
            operator = self.accept(lexer.AND, lexer.OR)
            if operator is None:
                return node
            right = self.unary()
            node = And(node, right) if operator.kind == lexer.AND else Or(node, right)

    def unary(self):
        if self.accept(lexer.NOT):
            return Not(self.unary())
        return self.primary()

    def primary(self):
        if self.accept(lexer.LPAREN):
            node = self.expression()
            self.expect(lexer.RPAREN, "a closing ')'")
            return node

        # A logical variable used on its own stands for the formula it names.
        if self.current.kind == lexer.WORD:
            name = self.current.value.upper()
            following = self.tokens[self.index + 1]
            if name in self.variables and following.kind != lexer.DOT:
                self.advance()
                return self.variables[name]

        return self.condition()

    # -- conditions --------------------------------------------------------

    def entity(self):
        """A body, a set of them, or a house cusp."""
        start = self.current.position

        # The angles stand alone, like cusps.
        if self.current.kind == lexer.WORD:
            angle = vocabulary.as_angle(self.current.value)
            if angle is not None:
                self.advance()
                transit = bool(self.accept(lexer.APOSTROPHE))
                return Entity(
                    angles=[angle],
                    transit=transit,
                    source=self.text[start : self.current.position].strip(),
                )

        # A cusp stands alone: the specification says cusps cannot form a set.
        if self.current.kind == lexer.WORD:
            house = vocabulary.as_house(self.current.value)
            if house is not None:
                token = self.advance()
                if self.current.kind == lexer.COMMA:
                    raise FormulaSyntaxError(
                        "Cusps cannot form a set, so H1,H10 is not valid here.",
                        self.current.position,
                        self.text,
                    )
                transit = bool(self.accept(lexer.APOSTROPHE))
                return Entity(
                    cusps=[house], transit=transit, source=self.text[start : self.current.position].strip()
                )

        bodies = []

        while True:
            token = self.expect(lexer.WORD, "a body name")
            body = vocabulary.as_body(token.value)
            if body is None:
                raise FormulaSyntaxError(
                    f"Unknown body {token.value!r}", token.position, self.text
                )

            if self.accept(lexer.DASH):
                end_token = self.expect(lexer.WORD, "the end of the range")
                end_body = vocabulary.as_body(end_token.value)
                if end_body is None:
                    raise FormulaSyntaxError(
                        f"Unknown body {end_token.value!r}",
                        end_token.position,
                        self.text,
                    )
                bodies.extend(self._body_range(body, end_body, end_token))
            else:
                bodies.append(body)

            if not self.accept(lexer.COMMA):
                break

        transit = bool(self.accept(lexer.APOSTROPHE))
        source = self.text[start : self.current.position].strip()
        return Entity(bodies=bodies, transit=transit, source=source)

    def _body_range(self, first, last, token):
        from ..constants import BODIES

        order = [b.code for b in BODIES]
        try:
            start, end = order.index(first.code), order.index(last.code)
        except ValueError:  # pragma: no cover - codes come from the same table
            raise FormulaSyntaxError("Unknown body in range", token.position, self.text)
        if start > end:
            start, end = end, start
        return BODIES[start : end + 1]

    def condition(self):
        start = self.current.position

        # A few conditions name no body and take no dot.
        if self.current.kind == lexer.WORD:
            standalone = vocabulary.as_standalone(self.current.value)
            if standalone == "MOONVOID":
                self.advance()
                return MoonVoid(source=self._source(start))

        left = self.entity()
        self.expect(lexer.DOT, "a '.' after the body")

        # An explicit orb range stands in for a named aspect: ME.[131-133].MA
        bracket = self.accept(lexer.RANGE)
        if bracket:
            try:
                low, high = vocabulary.parse_range(bracket.value)
            except ValueError as exc:
                raise FormulaSyntaxError(str(exc), bracket.position, self.text)
            right = self._aspect_partner()
            return Aspect(
                left,
                right,
                angles=[(low + high) / 2.0],
                orb_range=(low, high),
                source=self._source(start),
            )

        # "earlier in the zodiac than": SO.<.MO
        if self.accept(lexer.LT):
            self.expect(lexer.DOT, "a '.' before the second body")
            right = self.entity()
            return Precedes(left, right, source=self._source(start))

        # A numeric aspect, with dynamics possibly following: Sun.120AF.Lun
        number = self.accept(lexer.NUMBER)
        if number:
            # A range written without its brackets is the easiest thing in the
            # syntax to get wrong, so say what the right form looks like rather
            # than complaining about a missing dot further along.
            if self.current.kind == lexer.DASH:
                upper = self.tokens[self.index + 1]
                high = upper.value if upper.kind == lexer.NUMBER else "..."
                raise FormulaSyntaxError(
                    "An aspect range goes in square brackets: write "
                    f"[{number.value}-{high}] rather than {number.value}-{high}",
                    self.current.position,
                    self.text,
                )
            angle = float(number.value)
            dynamics = ""
            if self.current.kind == lexer.WORD and vocabulary.is_dynamics(
                self.current.value
            ):
                dynamics = self.advance().value.upper()
            right = self._aspect_partner()
            return Aspect(
                left, right, angles=[angle], dynamics=dynamics, source=self._source(start)
            )

        word = self.expect(lexer.WORD, "a sign, house, aspect or phase")
        return self._predicate(left, word, start)

    def _predicate(self, left, word, start):
        text = word.value

        if vocabulary.as_planetary_hour(text):
            return PlanetaryHour(left, source=self._source(start))

        house = vocabulary.as_house(text)
        if house is not None:
            houses = [house]
            while True:
                if self.accept(lexer.COMMA):
                    houses.append(self._next_house())
                elif self.accept(lexer.DASH):
                    houses.extend(_span(houses[-1] - 1, self._next_house() - 1, 12, 1))
                else:
                    break
            return InHouse(left, houses, source=self._source(start))

        sign = vocabulary.as_sign(text)
        if sign is not None:
            signs, portions = [sign], [self._portion()]
            while True:
                if self.accept(lexer.COMMA):
                    signs.append(self._next_sign())
                    portions.append(self._portion())
                elif self.accept(lexer.DASH):
                    if portions[-1] is not None:
                        raise FormulaSyntaxError(
                            "A degree portion cannot be combined with a sign range",
                            self.current.position, self.text,
                        )
                    run = _span(signs[-1], self._next_sign(), 12, 0)
                    signs.extend(run)
                    portions.extend([None] * len(run))
                else:
                    break
            return InSign(left, signs, portions, source=self._source(start))

        aspect_name, dynamics = vocabulary.split_dynamics(text)
        angle = vocabulary.as_aspect(aspect_name) if aspect_name else None
        if angle is not None:
            angles = [angle]
            # A list of acceptable aspects: Mer.Sxt,Tri.Jup
            while self.accept(lexer.COMMA):
                more = self.expect(lexer.WORD, "another aspect")
                more_name, more_dynamics = vocabulary.split_dynamics(more.value)
                more_angle = vocabulary.as_aspect(more_name)
                if more_angle is None:
                    raise FormulaSyntaxError(
                        f"Unknown aspect {more.value!r}", more.position, self.text
                    )
                angles.append(more_angle)
                dynamics = dynamics or more_dynamics
            right = self._aspect_partner()
            return Aspect(
                left, right, angles=angles, dynamics=dynamics, source=self._source(start)
            )

        if vocabulary.is_motion(text):
            return Motion(left, list(text.upper()), source=self._source(start))

        raise FormulaSyntaxError(
            f"{text!r} is not a sign, house, aspect or motion phase",
            word.position,
            self.text,
        )

    def _portion(self):
        """An optional degree range after a sign: Ari[29-30], or Ari[30].

        A single figure names the degree ending there, so [30] is the stretch
        from 29 to 30, which is how the specification reads it.
        """
        bracket = self.accept(lexer.RANGE)
        if not bracket:
            return None
        try:
            low, high = vocabulary.parse_range(bracket.value)
        except ValueError as exc:
            raise FormulaSyntaxError(str(exc), bracket.position, self.text)
        if low == high:
            low = max(0.0, high - 1.0)
        if not (0 <= low < high <= 30):
            raise FormulaSyntaxError(
                f"A portion of a sign must fall between 0 and 30 degrees, not "
                f"{low:g} to {high:g}.",
                bracket.position,
                self.text,
            )
        return (low, high)

    def _next_sign(self):
        token = self.expect(lexer.WORD, "another sign")
        value = vocabulary.as_sign(token.value)
        if value is None:
            raise FormulaSyntaxError(
                f"Unknown sign {token.value!r}", token.position, self.text
            )
        return value

    def _next_house(self):
        token = self.expect(lexer.WORD, "another house")
        value = vocabulary.as_house(token.value)
        if value is None:
            raise FormulaSyntaxError(
                f"Unknown house {token.value!r}", token.position, self.text
            )
        return value

    def _more(self, convert, description):
        """Read further comma-separated values of the same kind."""
        values = []
        while self.accept(lexer.COMMA):
            token = self.expect(lexer.WORD, f"another {description}")
            value = convert(token.value)
            if value is None:
                raise FormulaSyntaxError(
                    f"Unknown {description} {token.value!r}", token.position, self.text
                )
            values.append(value)
        return values

    def _aspect_partner(self):
        self.expect(lexer.DOT, "a '.' before the second body")
        return self.entity()

    def _source(self, start):
        return self.text[start : self.current.position].strip()


def parse(text):
    """Parse a formula, including any macros and variables it declares.

    Definitions come first, separated by semicolons, and the last statement is
    the formula itself. Macros are substituted textually; variables are parsed
    once and their trees reused wherever the name appears.
    """
    declarations, formula_text = defs.parse_definitions(text)

    variables = {}
    for name, body in declarations.variables.items():
        expanded = defs.expand(body, declarations)
        variables[name] = Parser(expanded, variables=dict(variables)).parse()

    return Parser(defs.expand(formula_text, declarations), variables=variables).parse()
