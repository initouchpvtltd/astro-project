"""Draws a chart as an SVG wheel.

The conventional layout: the Ascendant on the left, the zodiac running
anticlockwise from it, so the Midheaven falls near the top and the Imum Coeli
near the bottom. Signs occupy the outer band, houses the inner one, planets sit
between them, and the aspects are drawn as chords across the middle.

Each planet is written the way printed ephemerides write it: the glyph, with
its degree and minute on a single short line beneath. Keeping the reading to
two rows is what keeps a stellium legible, because a short line takes little
angular room however tightly the bodies are packed.

The wheel is drawn on a light face whatever the surrounding page does. That is
how every chart an astrologer has ever read is printed, it survives being
dropped into any WordPress theme, and it is the only way the thin strokes of
the glyphs stay crisp.

Built as inline SVG with Unicode glyphs, so there is no image to serve, no font
to license, and it scales to any size without blurring. It drops into a
WordPress page as plain markup.
"""

import math
from typing import NamedTuple

from . import glyphs, orbs
from .constants import SIGNS

# Drawn, not typed: see app/glyphs.py for why the Unicode characters are not
# good enough here.
SIGN_GLYPHS = glyphs.SIGNS
BODY_GLYPHS = glyphs.BODIES
ASPECT_GLYPHS = glyphs.ASPECTS

RETROGRADE = "\u211e"

# The seven traditional planets plus the modern three. The Hamburg bodies and
# the rest would crowd the wheel without telling a horary astrologer anything.
DRAWN = ("SO", "MO", "ME", "VE", "MA", "JU", "SA", "UR", "NE", "PL")

# The aspects, with the class that colours them. The orb is not fixed here:
# it comes from app.orbs, which holds the client's own moiety table, so the
# chart and the search agree about what counts as an aspect. They used not
# to: this file carried its own narrow table, and a Sun trine Saturn at
# eight degrees showed in a search and was missing from the chart beside it.
#
# A conjunction is listed beneath the wheel but not drawn as a chord: two
# bodies a few degrees apart produce a stub too short to read, and the wheel
# already shows them sitting together.
ASPECTS = [
    (0.0, "conjunction", "asp-conj"),
    (60.0, "sextile", "asp-soft"),
    (90.0, "square", "asp-hard"),
    (120.0, "trine", "asp-soft"),
    (180.0, "opposition", "asp-hard"),
]
CHORDLESS = ("conjunction",)

SIZE = 900
CENTRE = SIZE / 2

R_OUTER = 400        # outside of the zodiac band
R_SIGNS = 344        # inside of the zodiac band
R_GLYPH = 314        # the planet glyph
R_DEGREE = 284       # its degree and minute, on the line beneath
R_NUMBERS = 244      # outside of the band carrying the house numbers
R_HOUSES = 214       # inside of the house band
R_ASPECTS = 202      # the chord circle

# Two readings closer than this overlap. Eight and a half degrees at the
# radius the degree line sits on is about forty-two pixels, which is what
# "22°57′" occupies, so this is the tightest spacing that still reads.
class Rings(NamedTuple):
    """Where each part of a wheel sits, measured out from the centre.

    A single chart and a bi-wheel draw the same furniture at different radii,
    so the radii travel as an argument rather than being read off the module.
    `rim` is where a planet's pointer tick lands: the inside of the zodiac for
    a chart with one ring, and the divider between the rings for the natal
    half of a bi-wheel, so the two sets of planets never share a line.
    """

    outer: float
    signs: float
    rim: float
    glyph: float
    degree: float
    numbers: float
    houses: float
    aspects: float


SINGLE = Rings(
    outer=R_OUTER, signs=R_SIGNS, rim=R_SIGNS, glyph=R_GLYPH,
    degree=R_DEGREE, numbers=R_NUMBERS, houses=R_HOUSES, aspects=R_ASPECTS,
)

# A bi-wheel carries two sets of planets, so everything below the zodiac band
# moves inward to make room. The transiting bodies take the ring the single
# chart gives its planets; the natal ones sit inside them, where an astrologer
# expects the birth chart to be.
BI_TRANSIT = Rings(
    outer=R_OUTER, signs=R_SIGNS, rim=R_SIGNS, glyph=314,
    degree=288, numbers=178, houses=152, aspects=142,
)
BI_NATAL = Rings(
    outer=R_OUTER, signs=R_SIGNS, rim=266, glyph=236,
    degree=210, numbers=178, houses=152, aspects=142,
)

MIN_SEPARATION = 8.5

# Fire, earth, air, water, in the order the signs run.
ELEMENT_CLASSES = ("element-0", "element-1", "element-2", "element-3")

# Stroke weight for the drawn glyphs, in their own hundred-unit square.
GLYPH_STROKE = 6.5
SIGN_SIZE = 36
PLANET_SIZE = 34


def _polar(longitude, ascendant, radius):
    """Screen coordinates for an ecliptic longitude.

    The Ascendant sits at the left and the zodiac runs anticlockwise, which is
    what puts the Midheaven near the top.
    """
    angle = math.radians(180.0 + (longitude - ascendant))
    return (
        CENTRE + radius * math.cos(angle),
        CENTRE - radius * math.sin(angle),
    )


def _spread(longitudes):
    """Nudge glyphs apart so none hides another.

    Several bodies within a degree or two of each other is common, and drawn
    literally they land on top of one another. Positions are adjusted only for
    display; the degrees printed beneath them stay exact, and a thread joins
    each glyph back to its true place on the wheel.

    Pushing in one direction along the sorted order is what keeps the result
    honest: a body never ends up drawn past a neighbour it genuinely precedes.
    """
    if len(longitudes) < 2:
        return list(longitudes)

    order = sorted(range(len(longitudes)), key=lambda i: longitudes[i])

    # Unwrap into a rising sequence so the 0/360 boundary needs no special case.
    unwrapped = []
    for position, index in enumerate(order):
        value = longitudes[index]
        if position and value < unwrapped[-1]:
            value += 360.0 * math.ceil((unwrapped[-1] - value) / 360.0)
        unwrapped.append(value)

    # Push each crowded glyph forward, never backward, so the order holds.
    placed = [unwrapped[0]]
    for value in unwrapped[1:]:
        placed.append(max(value, placed[-1] + MIN_SEPARATION))

    # The run has grown forward, so slide it back by half to keep the cluster
    # sitting where it belongs rather than drifting anticlockwise.
    drift = ((placed[-1] - placed[0]) - (unwrapped[-1] - unwrapped[0])) / 2.0
    placed = [value - drift for value in placed]

    adjusted = [0.0] * len(longitudes)
    for index, value in zip(order, placed):
        adjusted[index] = value % 360.0
    return adjusted


def _disc(radius, klass):
    return f'<circle cx="{CENTRE}" cy="{CENTRE}" r="{radius:.1f}" class="{klass}"/>'


def _ring(radius, klass):
    return (
        f'<circle cx="{CENTRE}" cy="{CENTRE}" r="{radius:.1f}" '
        f'fill="none" class="{klass}"/>'
    )


def _line(x1, y1, x2, y2, klass):
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'class="{klass}"/>'
    )


def _radial(longitude, ascendant, inner, outer, klass):
    x1, y1 = _polar(longitude, ascendant, inner)
    x2, y2 = _polar(longitude, ascendant, outer)
    return _line(x1, y1, x2, y2, klass)


def _text(longitude, ascendant, radius, klass, content):
    x, y = _polar(longitude, ascendant, radius)
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{klass}">{content}</text>'


def _glyph(longitude, ascendant, radius, spec, size, klass, title=None):
    x, y = _polar(longitude, ascendant, radius)
    return glyphs.draw(spec, x, y, size, klass, title=title, stroke=GLYPH_STROKE)


def _sector(start, span, ascendant, inner, outer, klass):
    """One slice of an annulus, used to tint a band.

    Longitude increases anticlockwise on screen, which is why the outer arc is
    drawn with the sweep flag clear and the inner one with it set.
    """
    ax, ay = _polar(start, ascendant, outer)
    bx, by = _polar(start + span, ascendant, outer)
    cx, cy = _polar(start + span, ascendant, inner)
    dx, dy = _polar(start, ascendant, inner)
    large = 1 if span > 180 else 0
    return (
        f'<path class="{klass}" d="M{ax:.1f},{ay:.1f} '
        f'A{outer:.1f},{outer:.1f} 0 {large} 0 {bx:.1f},{by:.1f} '
        f'L{cx:.1f},{cy:.1f} '
        f'A{inner:.1f},{inner:.1f} 0 {large} 1 {dx:.1f},{dy:.1f} Z"/>'
    )


def _zodiac(ascendant, rings=SINGLE):
    """The outer band: a tinted slice, a glyph and a degree scale per sign."""
    parts = []
    for index in range(12):
        start = index * 30.0
        element = ELEMENT_CLASSES[index % 4]

        # The tint is what makes the four elements readable at a glance, the
        # way a printed wheel colours them.
        parts.append(
            _sector(start, 30.0, ascendant, rings.signs, rings.outer, f"sector {element}")
        )
        parts.append(_radial(start, ascendant, rings.signs, rings.outer, "sign-divide"))
        parts.append(
            _glyph(
                start + 15.0, ascendant, rings.signs + 36, SIGN_GLYPHS[index],
                SIGN_SIZE, f"gl sign-glyph {element}", title=SIGNS[index],
            )
        )

        # A tick every degree along the inner edge of the band, longer every
        # fifth and tenth. This is how the degree of a planet is read off the
        # wheel, and it is what gives a chart its instrument-like precision.
        for offset in range(30):
            if offset % 10 == 0:
                length, klass = 15, "tick-10"
            elif offset % 5 == 0:
                length, klass = 10, "tick-5"
            else:
                length, klass = 5, "tick"
            parts.append(
                _radial(start + offset, ascendant, rings.signs, rings.signs + length, klass)
            )

    return "".join(parts)


def _houses(cusps, ascendant, rings=SINGLE):
    """The inner band: alternating slices, cusp lines and house numbers."""
    parts = []
    for index, cusp in enumerate(cusps):
        longitude = cusp["longitude"]
        following = cusps[(index + 1) % 12]["longitude"]
        span = (following - longitude) % 360.0 or 30.0

        # Alternate slices give the band structure without competing with
        # anything drawn on top of it.
        if index % 2 == 0:
            parts.append(
                _sector(longitude, span, ascendant, rings.houses, rings.numbers, "house-sector")
            )

        angular = index in (0, 3, 6, 9)  # the four angles carry more weight
        parts.append(
            _radial(
                longitude, ascendant, rings.houses, rings.rim,
                "cusp-major" if angular else "cusp",
            )
        )
        parts.append(
            _text(
                longitude + span / 2.0, ascendant, (rings.houses + rings.numbers) / 2,
                "house-number", str(index + 1),
            )
        )

    return "".join(parts)


def _axes(houses, ascendant, rings=SINGLE):
    """The horizon and the meridian, drawn right across the chart.

    Two lines through the centre are what let the eye place a planet above or
    below the horizon without counting houses.
    """
    parts = []
    for longitude in (houses["ascendant"]["longitude"], houses["midheaven"]["longitude"]):
        x1, y1 = _polar(longitude, ascendant, rings.aspects)
        x2, y2 = _polar(longitude + 180.0, ascendant, rings.aspects)
        parts.append(_line(x1, y1, x2, y2, "axis"))
    return "".join(parts)


def _angles(houses, ascendant, rings=SINGLE):
    """Name the four angles, with a marker at the rim for each."""
    parts = []
    ascending = houses["ascendant"]["longitude"]
    meridian = houses["midheaven"]["longitude"]
    for longitude, label in (
        (ascending, "ASC"), (ascending + 180.0, "DSC"),
        (meridian, "MC"), (meridian + 180.0, "IC"),
    ):
        tip_x, tip_y = _polar(longitude, ascendant, rings.outer - 1)
        left_x, left_y = _polar(longitude - 1.3, ascendant, rings.outer + 13)
        right_x, right_y = _polar(longitude + 1.3, ascendant, rings.outer + 13)
        parts.append(
            f'<polygon class="angle-mark" points="{tip_x:.1f},{tip_y:.1f} '
            f'{left_x:.1f},{left_y:.1f} {right_x:.1f},{right_y:.1f}"/>'
        )
        parts.append(_text(longitude, ascendant, rings.outer + 30, "angle-label", label))
    return "".join(parts)


def aspects_between(drawn, orb_system=None):
    """Every aspect among the drawn bodies, tightest orb first.

    Shared with the page beneath the wheel so the chords in the middle and the
    rows in the table can never disagree about what is in aspect. The orb
    comes from the client's moiety table, the same one the scanner judges by.
    """
    found = []
    for i, first in enumerate(drawn):
        for second in drawn[i + 1:]:
            gap = abs(first["longitude"] - second["longitude"]) % 360.0
            if gap > 180.0:
                gap = 360.0 - gap
            for angle, name, klass in ASPECTS:
                difference = abs(gap - angle)
                orb = orbs.allowance(
                    first["code"], second["code"], angle, orb_system
                )
                if difference <= orb:
                    found.append(
                        {
                            "first": first,
                            "second": second,
                            "name": name,
                            "class": klass,
                            "orb": difference,
                            "strength": 1.0 - difference / orb if orb else 1.0,
                        }
                    )
                    break
    found.sort(key=lambda a: a["orb"])
    return found


def _aspect_lines(drawn, ascendant, rings=SINGLE):
    parts = []
    for aspect in aspects_between(drawn):
        if aspect["name"] in CHORDLESS:
            continue
        first, second = aspect["first"], aspect["second"]
        x1, y1 = _polar(first["longitude"], ascendant, rings.aspects)
        x2, y2 = _polar(second["longitude"], ascendant, rings.aspects)
        # Closer to exact draws more strongly, so a partile aspect stands out
        # from one barely inside its orb.
        strength = aspect["strength"]
        parts.append(
            f'<line class="{aspect["class"]}" x1="{x1:.1f}" y1="{y1:.1f}" '
            f'x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke-width="{0.8 + strength * 1.5:.2f}" '
            f'stroke-opacity="{0.18 + strength * 0.45:.2f}">'
            f'<title>{first["name"]} {aspect["name"]} {second["name"]}</title></line>'
        )
    return "".join(parts)


def _planets(drawn, ascendant, rings=SINGLE, klass="planet"):
    placed = _spread([b["longitude"] for b in drawn])
    parts = []

    for body, display in zip(drawn, placed):
        true_longitude = body["longitude"]
        position = body["position"]
        retrograde = bool(body.get("retrograde"))

        # A tick at the exact degree on the inner edge of the zodiac, and a
        # thread down to the glyph, so nudging one aside never misleads about
        # where the body actually is.
        parts.append(_radial(true_longitude, ascendant, rings.rim - 9, rings.rim, "pointer"))
        tx, ty = _polar(true_longitude, ascendant, rings.rim - 9)
        gx, gy = _polar(display, ascendant, rings.glyph + 17)
        parts.append(_line(tx, ty, gx, gy, "leader"))

        retro_note = f" {RETROGRADE}" if retrograde else ""
        parts.append(
            _glyph(
                display, ascendant, rings.glyph, BODY_GLYPHS[body["code"]],
                PLANET_SIZE, f"gl {klass}",
                title=f'{body["name"]} {position["formatted"]}{retro_note}',
            )
        )
        mark = f'<tspan class="retro">{RETROGRADE}</tspan>' if retrograde else ""
        parts.append(
            _text(
                display, ascendant, rings.degree, "degree",
                "{}°{:02d}′{}".format(
                    position["degree"], position["minute"], mark
                ),
            )
        )

    return "".join(parts)


# The wheel carries its own colours rather than borrowing the page's, so the
# same markup drops into a WordPress theme and still reads correctly.
STYLE = glyphs.STYLE + """
.wheel {
  --w-ink: #14110f; --w-muted: #6f6761; --w-faint: #b3aba3;
  --w-line: #cdc5b8; --w-line-soft: #e5ded4; --w-accent: #9a6a2f;
  --w-face: #ffffff; --w-band: #faf7f2; --w-house: #14110f0d;
  --w-hard: #b8402c; --w-soft: #1d7a6a;
  --w-fire: #bf4b2d; --w-earth: #6c7739; --w-air: #1d6b94; --w-water: #1a7f70;
  width: 100%; height: auto; max-width: 820px; display: block; margin: 0 auto;
}

.wheel text {
  text-anchor: middle; dominant-baseline: central; font-variant-emoji: text;
  font-family: ui-sans-serif, -apple-system, "Segoe UI Symbol", "Apple Symbols",
               "Noto Sans Symbols2", sans-serif;
}
.face { fill: var(--w-face); }
.band-fill { fill: var(--w-band); }
.ring { stroke: var(--w-line); stroke-width: 1.5; }
.ring-soft { stroke: var(--w-line-soft); stroke-width: 1; }
.sector { stroke: none; fill-opacity: .16; }
.house-sector { fill: var(--w-house); stroke: none; }
.sign-divide { stroke: var(--w-line); stroke-width: 1.3; }

.tick { stroke: var(--w-faint); stroke-width: .7; }
.tick-5 { stroke: var(--w-muted); stroke-width: .8; opacity: .65; }
.tick-10 { stroke: var(--w-muted); stroke-width: 1.2; }

.cusp { stroke: var(--w-line); stroke-width: 1.1; stroke-dasharray: 2 6; }
.cusp-major { stroke: var(--w-accent); stroke-width: 1.6; }
.axis { stroke: var(--w-accent); stroke-width: 1; opacity: .3; }
.pointer { stroke: var(--w-ink); stroke-width: 1.5; }
.leader { stroke: var(--w-muted); stroke-width: .7; opacity: .4; }

.sign-glyph { color: var(--w-ink); }
.element-0 { fill: var(--w-fire); color: var(--w-fire); }
.element-1 { fill: var(--w-earth); color: var(--w-earth); }
.element-2 { fill: var(--w-air); color: var(--w-air); }
.element-3 { fill: var(--w-water); color: var(--w-water); }

.planet { color: var(--w-ink); }
/* The transiting bodies are the same glyphs in a different voice: warmer and
   a shade lighter, so a glance tells the two rings apart without a key. */
.transit { color: #9a6a2f; }
.ring-divide { fill: none; stroke: var(--w-line); stroke-width: 1.2;
  stroke-dasharray: 3 5; opacity: .75; }
.degree { font-size: 14px; fill: #423d38; letter-spacing: -.01em;
          font-variant-numeric: tabular-nums; }
.retro { fill: var(--w-hard); font-weight: 700; font-size: 12px; }
.house-number { font-size: 15px; fill: var(--w-muted);
                font-variant-numeric: tabular-nums; }
.angle-label { font-size: 14px; font-weight: 700; letter-spacing: .1em;
               fill: var(--w-accent); }
.angle-mark { fill: var(--w-accent); }

/* On a phone the wheel is too small for the degree beneath each glyph to be
   legible, so it is dropped and the glyphs grow instead. The exact positions
   are in the table directly beneath the chart. */
@media (max-width: 560px) {
  .degree { display: none; }
  .planet, .sign-glyph { transform-box: fill-box; transform-origin: center;
                         scale: 1.35; }
  .house-number { font-size: 20px; }
  .angle-label { font-size: 19px; }
  .tick { display: none; }
}

.asp-hard { stroke: var(--w-hard); }
.asp-soft { stroke: var(--w-soft); }
.asp-conj { stroke: var(--w-muted); }
"""


def crossing_aspects(moving, natal, orb_system=None):
    """The aspects a moment's sky makes to a birth chart.

    Only the crossing pairs. Aspects within the birth chart are the birth
    chart's own business and are shown on its page; repeating them here would
    bury the handful of lines the transit is actually about.
    """
    found = []
    for mover in moving:
        for fixed in natal:
            angle = orbs.separation(mover["longitude"], fixed["longitude"])
            for exact, name, klass in ASPECTS:
                allowance = orbs.allowance(
                    mover["code"], fixed["code"], exact, orb_system
                )
                gap = abs(angle - exact)
                if gap > allowance:
                    continue
                found.append({
                    "moving": mover,
                    "natal": fixed,
                    "name": name,
                    "class": klass,
                    "angle": exact,
                    "orb": gap,
                    "strength": 1.0 - (gap / allowance if allowance else 0.0),
                })
                break
    found.sort(key=lambda a: a["orb"])
    return found


def _cross_lines(crossings, ascendant, rings):
    parts = []
    for aspect in crossings:
        if aspect["name"] in CHORDLESS:
            continue
        x1, y1 = _polar(aspect["moving"]["longitude"], ascendant, rings.aspects)
        x2, y2 = _polar(aspect["natal"]["longitude"], ascendant, rings.aspects)
        strength = aspect["strength"]
        parts.append(
            f'<line class="{aspect["class"]}" x1="{x1:.1f}" y1="{y1:.1f}" '
            f'x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke-width="{0.8 + strength * 1.5:.2f}" '
            f'stroke-opacity="{0.18 + strength * 0.45:.2f}">'
            f'<title>transiting {aspect["moving"]["name"]} {aspect["name"]} '
            f'natal {aspect["natal"]["name"]}</title></line>'
        )
    return "".join(parts)


def _for_wheel(chart):
    return [
        body for body in chart["bodies"]
        if body.get("code") in DRAWN and "error" not in body
    ]


def render_transits(natal, moving):
    """A bi-wheel: the birth chart inside, the sky of a given moment outside.

    The wheel is oriented on the natal Ascendant and carries the natal houses,
    because the question a transit answers is where the moving body has
    arrived in the birth chart. Only the chords that cross between the two
    rings are drawn.
    """
    houses = natal["houses"]
    ascendant = houses["ascendant"]["longitude"]
    inner = _for_wheel(natal)
    outer = _for_wheel(moving)

    return (
        f'<svg class="wheel" viewBox="0 0 {SIZE} {SIZE}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Transits around a natal chart">'
        f"<style>{STYLE}</style>"
        + _disc(BI_NATAL.outer, "face")
        + _disc(BI_NATAL.signs, "band-fill")
        + _disc(BI_NATAL.rim, "face")
        + _zodiac(ascendant, BI_NATAL)
        + _houses(houses["cusps"], ascendant, BI_NATAL)
        + _ring(BI_NATAL.outer, "ring")
        + _ring(BI_NATAL.signs, "ring")
        + f'<circle cx="{CENTRE}" cy="{CENTRE}" r="{BI_NATAL.rim}" class="ring-divide"/>'
        + _ring(BI_NATAL.numbers, "ring-soft")
        + _ring(BI_NATAL.houses, "ring")
        + _ring(BI_NATAL.aspects, "ring-soft")
        + _axes(houses, ascendant, BI_NATAL)
        + f'<g class="chords">{_cross_lines(crossing_aspects(outer, inner), ascendant, BI_NATAL)}</g>'
        + _planets(inner, ascendant, BI_NATAL, "planet")
        + _planets(outer, ascendant, BI_TRANSIT, "transit")
        + _angles(houses, ascendant, BI_NATAL)
        + "</svg>"
    )


def render(chart):
    """Build the wheel for a chart, as inline SVG."""
    houses = chart["houses"]
    ascendant = houses["ascendant"]["longitude"]
    drawn = [
        body
        for body in chart["bodies"]
        if body.get("code") in DRAWN and "error" not in body
    ]

    return (
        f'<svg class="wheel" viewBox="0 0 {SIZE} {SIZE}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Astrological chart wheel">'
        f"<style>{STYLE}</style>"
        + _disc(R_OUTER, "face")
        + _disc(R_SIGNS, "band-fill")
        + _disc(R_HOUSES, "face")
        + _zodiac(ascendant)
        + _houses(houses["cusps"], ascendant)
        + _ring(R_OUTER, "ring")
        + _ring(R_SIGNS, "ring")
        + _ring(R_NUMBERS, "ring-soft")
        + _ring(R_HOUSES, "ring")
        + _ring(R_ASPECTS, "ring-soft")
        + _axes(houses, ascendant)
        # The chords are grouped so a page can hide them in one rule and show
        # the chart on its own, which is how an astrologer reads placements.
        + f'<g class="chords">{_aspect_lines(drawn, ascendant)}</g>'
        + _planets(drawn, ascendant)
        + _angles(houses, ascendant)
        + "</svg>"
    )
