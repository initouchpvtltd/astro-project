"""Macros and logical variables.

A formula may be written as several statements separated by semicolons, where
everything before the last one defines something the last one uses:

    PP = SO-PL;              a macro, plain text substitution
    x1 := ME.0.SA;           a logical variable, a named sub-formula
    x1 & PP.Sco              the formula itself, always last

Macros are expanded textually before parsing, which is what the specification
describes. Logical variables are parsed on their own and their trees spliced
in, so a variable used twice is only parsed once.
"""

import re

from .lexer import FormulaSyntaxError

# A name on its own at the start of a statement, followed by = or :=
_MACRO = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", re.DOTALL)
_VARIABLE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*::?=\s*(.+)$", re.DOTALL)

# Guards against a macro that refers to itself, directly or in a circle.
_MAX_EXPANSIONS = 50


class Definitions:
    """What a formula's opening statements declared."""

    def __init__(self):
        self.macros = {}
        self.variables = {}

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Definitions(macros={list(self.macros)}, variables={list(self.variables)})"


def split_statements(text):
    """Split on semicolons, ignoring any inside brackets or comments."""
    statements = []
    current = []
    depth = 0
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end == -1 else end
            continue

        if char in "[(":
            depth += 1
        elif char in "])":
            depth = max(0, depth - 1)

        if char == ";" and depth == 0:
            statements.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1

    statements.append("".join(current))
    return [s for s in (part.strip() for part in statements) if s]


def parse_definitions(text):
    """Separate the definitions from the formula they serve.

    Returns (definitions, formula_text).
    """
    statements = split_statements(text)
    if not statements:
        raise FormulaSyntaxError("The formula is empty.")

    definitions = Definitions()

    # Everything but the last statement is a definition.
    for statement in statements[:-1]:
        variable = _VARIABLE.match(statement)
        if variable and ":=" in statement:
            name, body = variable.group(1), variable.group(2).strip()
            definitions.variables[name.upper()] = body
            continue

        macro = _MACRO.match(statement)
        if macro:
            name, body = macro.group(1), macro.group(2).strip()
            definitions.macros[name.upper()] = body
            continue

        raise FormulaSyntaxError(
            f"{statement!r} is neither a macro (NAME = ...) nor a variable "
            "(NAME := ...). Only the last statement may be the formula itself."
        )

    return definitions, statements[-1]


def expand(text, definitions):
    """Substitute macros into a statement until nothing changes.

    Names are replaced only where they stand alone, so a macro called PP does
    not corrupt a body called PPX.
    """
    if not definitions.macros:
        return text

    expanded = text
    for _ in range(_MAX_EXPANSIONS):
        replaced = expanded
        for name, body in definitions.macros.items():
            replaced = re.sub(
                rf"\b{re.escape(name)}\b", body, replaced, flags=re.IGNORECASE
            )
        if replaced == expanded:
            return expanded
        expanded = replaced

    raise FormulaSyntaxError(
        "A macro appears to refer to itself. Check the definitions for a loop."
    )
