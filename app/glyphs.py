"""Astrological glyphs, drawn rather than typed.

The signs and planets exist in Unicode, but leaving them to the reader's fonts
means leaving them to chance: every platform resolves them from a different
fallback face, so the Moon arrives hairline thin next to a heavy Mercury, and
on some machines they come back as colour emoji. A chart whose symbols do not
match is a chart nobody trusts.

So each glyph is drawn here as vector strokes on a 100x100 square. One weight,
one style, identical on every device, no font to ship and nothing to license.

A glyph is a list of short primitives:

    "p:<path data>"   a stroked path
    "f:<path data>"   a filled path
    "c:cx,cy,r"       a stroked circle
    "d:cx,cy,r"       a filled dot
"""

# --- the twelve signs, in zodiacal order ----------------------------------

SIGNS = [
    # Aries: the ram's horns, curling outward from a single stem
    ["p:M 50,89 C 50,58 47,40 39,30 C 28,16 12,21 12,38"
     " C 12,51 23,58 32,54",
     "p:M 50,89 C 50,58 53,40 61,30 C 72,16 88,21 88,38"
     " C 88,51 77,58 68,54"],
    # Taurus: the bull's head and horns
    ["c:50,64,23",
     "p:M 20,16 C 20,42 34,41 50,41 C 66,41 80,42 80,16"],
    # Gemini: the twins
    ["p:M 18,22 C 34,13 66,13 82,22",
     "p:M 18,78 C 34,87 66,87 82,78",
     "p:M 32,19 L 32,81",
     "p:M 68,19 L 68,81"],
    # Cancer: the crab's two claws
    ["d:30,34,13",
     "p:M 43,31 C 62,23 80,31 89,47",
     "d:70,66,13",
     "p:M 57,69 C 38,77 20,69 11,53"],
    # Leo: the lion's head and sweeping tail
    ["c:30,63,17",
     "p:M 45,54 C 48,27 72,19 83,34 C 93,48 84,68 70,74"],
    # Virgo: the maiden, three strokes closed by a crossing loop
    ["p:M 11,34 C 11,23 24,23 24,34 L 24,78",
     "p:M 24,35 C 24,24 37,24 37,35 L 37,78",
     "p:M 37,35 C 37,24 50,24 50,35 L 50,78",
     "p:M 50,50 C 64,42 82,50 82,64 C 82,79 63,87 45,75"],
    # Libra: the scales
    ["p:M 8,83 L 92,83",
     "p:M 8,53 L 26,53",
     "p:M 26,53 A 24,24 0 0 1 74,53",
     "p:M 74,53 L 92,53"],
    # Scorpio: the scorpion's sting
    ["p:M 13,34 C 13,24 27,24 27,34 L 27,76",
     "p:M 27,36 C 27,26 41,26 41,36 L 41,76",
     "p:M 41,36 C 41,26 55,26 55,36 L 55,74 L 88,42",
     "p:M 70,42 L 88,42 L 88,60"],
    # Sagittarius: the arrow
    ["p:M 15,85 L 81,19",
     "p:M 59,19 L 81,19 L 81,41",
     "p:M 32,36 L 64,68"],
    # Capricorn: the sea-goat
    ["p:M 13,30 C 26,21 35,34 41,53 C 46,68 51,79 59,77"
     " C 67,75 67,61 63,51",
     "p:M 63,51 C 59,36 85,32 87,53 C 89,72 70,81 56,73"],
    # Aquarius: the water bearer's waves
    ["p:M 13,43 L 28,32 L 43,43 L 58,32 L 73,43 L 87,33",
     "p:M 13,69 L 28,58 L 43,69 L 58,58 L 73,69 L 87,59"],
    # Pisces: the two fishes
    ["p:M 34,13 C 16,31 16,69 34,87",
     "p:M 66,13 C 84,31 84,69 66,87",
     "p:M 17,50 L 83,50"],
]

# --- the bodies ------------------------------------------------------------

BODIES = {
    # Sun: the circle of spirit
    "SO": ["c:50,50,30", "d:50,50,7"],
    # Moon: the crescent
    "MO": ["f:M 67.5,16.3 A 38,38 0 1 0 67.5,83.7 A 34,34 0 0 1 67.5,16.3 Z"],
    # Mercury: crescent, circle and cross
    "ME": ["p:M 31,11 C 33,31 41,40 50,40 C 59,40 67,31 69,11",
           "c:50,55,15",
           "p:M 50,70 L 50,92",
           "p:M 35,83 L 65,83"],
    # Venus: circle over cross
    "VE": ["c:50,34,19",
           "p:M 50,53 L 50,93",
           "p:M 33,79 L 67,79"],
    # Mars: circle and arrow
    "MA": ["c:39,62,21",
           "p:M 55,47 L 86,16",
           "p:M 65,16 L 86,16 L 86,37"],
    # Jupiter
    "JU": ["p:M 23,28 C 23,10 57,8 59,29 C 61,50 29,62 25,88",
           "p:M 14,71 L 76,71"],
    # Saturn: the cross of matter over the sickle
    "SA": ["p:M 15,27 L 48,27",
           "p:M 30,9 L 30,47",
           "p:M 30,45 C 45,38 63,47 65,61 C 67,78 54,89 41,83"],
    # Uranus
    "UR": ["p:M 21,13 L 21,49",
           "p:M 79,13 L 79,49",
           "p:M 21,31 L 79,31",
           "p:M 50,31 L 50,63",
           "c:50,77,13"],
    # Neptune: the trident
    "NE": ["p:M 15,11 L 15,30 C 15,61 30,75 50,75 C 70,75 85,61 85,30 L 85,11",
           "p:M 50,13 L 50,93",
           "p:M 31,85 L 69,85"],
    # Pluto: the circle of spirit held in the crescent, over the cross
    "PL": ["p:M 25,48 C 25,23 75,23 75,48",
           "c:50,38,13",
           "p:M 50,53 L 50,93",
           "p:M 31,78 L 69,78"],
    # North Node: the horseshoe
    "KN": ["p:M 27,89 L 27,67 C 15,57 13,38 24,25 C 36,11 64,11 76,25"
           " C 87,38 85,57 73,67 L 73,89"],
    # South Node: the same, inverted
    "SN": ["p:M 27,11 L 27,33 C 15,43 13,62 24,75 C 36,89 64,89 76,75"
           " C 87,62 85,43 73,33 L 73,11"],
    # Lilith, the Black Moon: the dark crescent on the cross
    "LI": ["f:M 63.4,9.4 A 28,28 0 1 0 63.4,58.6 A 25,25 0 0 1 63.4,9.4 Z",
           "p:M 50,62 L 50,93",
           "p:M 34,81 L 66,81"],
    # Chiron: the key
    "CH": ["p:M 29,11 L 29,57",
           "p:M 59,13 L 30,36",
           "p:M 30,36 L 61,59",
           "c:44,77,15"],
}

# --- the aspects -----------------------------------------------------------

ASPECTS = {
    "conjunction": ["c:35,63,17", "p:M 48,50 L 88,10"],
    "opposition": ["c:23,75,16", "c:77,25,16", "p:M 35,63 L 65,37"],
    "square": ["p:M 19,19 L 81,19 L 81,81 L 19,81 Z"],
    "trine": ["p:M 50,14 L 88,82 L 12,82 Z"],
    "sextile": ["p:M 50,10 L 50,90",
                "p:M 15,30 L 85,70",
                "p:M 85,30 L 15,70"],
}

# Stroke weight in the glyph's own units, so it scales with the glyph rather
# than staying a fixed number of pixels.
STROKE = 7.0


def draw(glyph, x, y, size, klass, title=None, stroke=STROKE):
    """One glyph, centred on (x, y) and drawn `size` units across."""
    scale = size / 100.0
    parts = []
    for item in glyph:
        kind, _, rest = item.partition(":")
        if kind == "p":
            parts.append(f'<path d="{rest}"/>')
        elif kind == "f":
            parts.append(f'<path class="solid" d="{rest}"/>')
        elif kind in ("c", "d"):
            cx, cy, r = rest.split(",")
            solid = ' class="solid"' if kind == "d" else ""
            parts.append(f'<circle{solid} cx="{cx}" cy="{cy}" r="{r}"/>')
    if title:
        parts.append(f"<title>{title}</title>")
    return (
        f'<g class="{klass}" stroke-width="{stroke}" '
        f'transform="translate({x - size / 2:.1f} {y - size / 2:.1f}) '
        f'scale({scale:.4f})">{"".join(parts)}</g>'
    )


def inline(glyph, size=18, klass="g", title=None, stroke=STROKE):
    """A glyph as a standalone element, for use inside a table cell."""
    body = draw(glyph, 50, 50, 100, klass, title=title, stroke=stroke)
    return (
        f'<svg class="glyph-svg" viewBox="0 0 100 100" width="{size}" '
        f'height="{size}" aria-hidden="true">{body}</svg>'
    )


# Shared by the wheel and the page: strokes, never fills, except where a glyph
# is solid by tradition.
STYLE = """
.glyph-svg { display: inline-block; vertical-align: -0.18em; }
.gl path, .gl circle { fill: none; stroke: currentColor;
                       stroke-linecap: round; stroke-linejoin: round; }
.gl .solid { fill: currentColor; stroke: none; }
"""
