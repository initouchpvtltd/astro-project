"""Tokeniser for the ZET 9 Geo formula syntax.

The grammar is dot-separated rather than word-separated, so a formula like

    Sun.120AF.Lun & Mer.Sxt.Jup

breaks into names, dots, operators and bracketed ranges. Deciding what a name
*means* is the parser's job; here we only split the text into pieces and keep
track of where each one came from, so an error can point at the offending
character.
"""

import re

WORD = "WORD"
NUMBER = "NUMBER"
DOT = "DOT"
AND = "AND"
OR = "OR"
NOT = "NOT"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
RANGE = "RANGE"  # [131-133] or [49:39:19-53:20]
COMMA = "COMMA"
DASH = "DASH"  # interval, as in SUN-PLU
APOSTROPHE = "APOSTROPHE"  # transit marker, phase two
ASSIGN = "ASSIGN"  # := for logical variables
DEFINE = "DEFINE"  # = for macros
SEMICOLON = "SEMICOLON"
LT = "LT"  # '<' meaning "earlier in the zodiac than"
END = "END"


class FormulaSyntaxError(ValueError):
    """The formula could not be read."""

    def __init__(self, message, position=None, text=None):
        self.position = position
        self.text = text
        if position is not None and text is not None:
            pointer = " " * position + "^"
            message = f"{message}\n  {text}\n  {pointer}"
        super().__init__(message)


class Token:
    __slots__ = ("kind", "value", "position")

    def __init__(self, kind, value, position):
        self.kind = kind
        self.value = value
        self.position = position

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.position})"

    def __eq__(self, other):
        return (
            isinstance(other, Token)
            and self.kind == other.kind
            and self.value == other.value
        )


# A bracketed orb range. The spec allows plain degrees, decimals, and
# sexagesimal with degree/minute/second marks: [131-133], [119.9-120.1],
# [49°39'19"-53°20'].
_RANGE = re.compile(r"\[[^\]]*\]")
# Names may carry digits and underscores: H12, pln_hour, MoonDay.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_COMMENT = re.compile(r"//.*")

_SINGLE = {
    ".": DOT,
    "&": AND,
    "|": OR,
    "^": NOT,
    "(": LPAREN,
    ")": RPAREN,
    ",": COMMA,
    "-": DASH,
    "'": APOSTROPHE,
    ";": SEMICOLON,
    "<": LT,
}


def tokenize(text):
    """Split a formula into tokens.

    Comments and whitespace are dropped. Everything else becomes a token
    carrying its offset in the original string, which is what lets errors
    point at the right character.
    """
    if text is None:
        raise FormulaSyntaxError("No formula given.")

    tokens = []
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        if char.isspace():
            i += 1
            continue

        comment = _COMMENT.match(text, i)
        if comment:
            i = comment.end()
            continue

        # ':=' assigns a logical variable, and must be checked before ':'
        # could be mistaken for part of a sexagesimal value.
        if text.startswith(":=", i):
            tokens.append(Token(ASSIGN, ":=", i))
            i += 2
            continue

        if text.startswith("::=", i):
            tokens.append(Token(ASSIGN, "::=", i))
            i += 3
            continue

        bracket = _RANGE.match(text, i)
        if bracket:
            tokens.append(Token(RANGE, bracket.group(), i))
            i = bracket.end()
            continue

        if char == "[":
            raise FormulaSyntaxError("Unclosed '['", i, text)

        word = _WORD.match(text, i)
        if word:
            tokens.append(Token(WORD, word.group(), i))
            i = word.end()
            continue

        number = _NUMBER.match(text, i)
        if number:
            tokens.append(Token(NUMBER, number.group(), i))
            i = number.end()
            continue

        if char == "=":
            tokens.append(Token(DEFINE, "=", i))
            i += 1
            continue

        kind = _SINGLE.get(char)
        if kind:
            tokens.append(Token(kind, char, i))
            i += 1
            continue

        raise FormulaSyntaxError(f"Unexpected character {char!r}", i, text)

    tokens.append(Token(END, None, length))
    return tokens
