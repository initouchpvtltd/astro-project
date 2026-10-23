"""The drawn chart wheel.

Geometry rather than appearance: that the Ascendant lands on the left, that
the zodiac runs the right way round, and that nothing is drawn outside the
canvas.
"""

import math
import re

import pytest

from app import wheel
from app.service import build_chart

BARCELONA = {"latitude": 41.3888, "longitude": 2.159, "timezone_name": "Europe/Madrid"}


@pytest.fixture
def chart():
    return build_chart("2026-07-15", "12:00:00", "R", **BARCELONA)


def test_the_ascendant_sits_on_the_left(chart):
    """The convention every astrologer reads a wheel by."""
    ascendant = chart["houses"]["ascendant"]["longitude"]
    x, y = wheel._polar(ascendant, ascendant, wheel.R_OUTER)
    assert x == pytest.approx(wheel.CENTRE - wheel.R_OUTER, abs=0.5)
    assert y == pytest.approx(wheel.CENTRE, abs=0.5)


def test_the_zodiac_runs_anticlockwise(chart):
    """Ninety degrees on from the Ascendant belongs at the bottom.

    That is what puts the Imum Coeli below and the Midheaven above. Running it
    the other way would produce a mirror image of every chart.
    """
    ascendant = chart["houses"]["ascendant"]["longitude"]
    _, y = wheel._polar(ascendant + 90, ascendant, wheel.R_OUTER)
    assert y > wheel.CENTRE  # downward on screen


def test_the_descendant_is_opposite_the_ascendant(chart):
    ascendant = chart["houses"]["ascendant"]["longitude"]
    x, _ = wheel._polar(ascendant + 180, ascendant, wheel.R_OUTER)
    assert x == pytest.approx(wheel.CENTRE + wheel.R_OUTER, abs=0.5)


def test_nothing_is_drawn_outside_the_canvas(chart):
    """Labels sit beyond the outer ring, so the margin has to be enough."""
    svg = wheel.render(chart)
    values = [float(v) for v in re.findall(r'[xy][12]?="([\d.]+)"', svg)]
    assert min(values) >= 0
    assert max(values) <= wheel.SIZE


def test_every_drawn_body_appears(chart):
    svg = wheel.render(chart)
    assert svg.count('gl planet"') == len(wheel.DRAWN)


def test_each_sign_gets_a_glyph(chart):
    """Every sign's drawn strokes have to be in there, not a font's guess."""
    svg = wheel.render(chart)
    for glyph in wheel.SIGN_GLYPHS:
        stroke = next(p[2:] for p in glyph if p.startswith(("p:", "f:")))
        assert stroke in svg


def test_no_glyph_is_left_to_the_readers_fonts(chart):
    """A Unicode sign or planet character would be resolved by whatever font
    the reader happens to have, which is what made the glyphs inconsistent."""
    svg = wheel.render(chart)
    for character in "\u2648\u2649\u264b\u2609\u263d\u263f\u2640\u2642":
        assert character not in svg


def test_all_twelve_cusps_are_drawn(chart):
    svg = wheel.render(chart)
    assert svg.count('class="cusp"') + svg.count('class="cusp-major"') == 12


def test_the_four_angles_are_drawn_more_strongly(chart):
    """Houses 1, 4, 7 and 10 carry more weight than the rest."""
    assert wheel.render(chart).count('class="cusp-major"') == 4


def test_crowded_glyphs_are_pushed_apart():
    """Several bodies within a degree is common and would otherwise overlap."""
    spread = wheel._spread([10.0, 10.5, 11.0])
    gaps = [
        (spread[b] - spread[a]) % 360.0
        for a, b in zip(range(len(spread) - 1), range(1, len(spread)))
    ]
    assert all(gap >= wheel.MIN_SEPARATION - 0.01 for gap in gaps)


def test_spreading_keeps_the_original_order():
    """Nudging a glyph aside must not move it past its neighbour."""
    spread = wheel._spread([10.0, 10.2, 10.4, 60.0])
    assert spread[0] < spread[1] < spread[2] < spread[3]


def test_a_lone_body_is_not_moved():
    assert wheel._spread([123.0]) == [123.0]


def test_aspects_are_drawn_between_bodies(chart):
    svg = wheel.render(chart)
    assert "stroke-opacity" in svg
    assert any(name in svg for _, name, _ in wheel.ASPECTS)


def test_the_svg_carries_no_external_references(chart):
    """It has to work inside WordPress with no network and no font files."""
    svg = wheel.render(chart)
    assert "http://www.w3.org/2000/svg" in svg
    assert "<image" not in svg
    assert "@import" not in svg
    assert "url(" not in svg


# --- the chart and the search have to agree about what is an aspect --------

def test_the_chart_uses_the_same_orbs_as_the_search(chart):
    """They used not to, and the difference showed.

    This file once carried its own narrow table — trine six degrees, sextile
    five — while the scanner judged by the client's moiety table. A Sun trine
    Saturn at eight degrees was therefore found by a search and missing from
    the chart printed beside it.
    """
    from app import orbs

    for aspect in wheel.aspects_between(
        [b for b in chart["bodies"] if b.get("code") in wheel.DRAWN]
    ):
        allowed = orbs.allowance(
            aspect["first"]["code"], aspect["second"]["code"],
            next(a for a, name, _ in wheel.ASPECTS if name == aspect["name"]),
            None,
        )
        assert aspect["orb"] <= allowed, f'{aspect["name"]} {aspect["orb"]}'


def test_astro_seek_agrees_aspect_for_aspect():
    """Their own traditional chart for 1 January 1970, 00:00 UT at 0°N 0°E."""
    from app.service import build_chart

    published = {
        frozenset(("Sun", "Moon")): ("square", 0.53),
        frozenset(("Sun", "Venus")): ("conjunction", 5.70),
        frozenset(("Sun", "Mars")): ("sextile", 2.07),
        frozenset(("Sun", "Saturn")): ("trine", 8.08),
        frozenset(("Moon", "Venus")): ("square", 6.23),
        frozenset(("Mercury", "Jupiter")): ("square", 3.30),
        frozenset(("Mercury", "Saturn")): ("square", 3.03),
        frozenset(("Venus", "Jupiter")): ("sextile", 2.12),
        frozenset(("Venus", "Saturn")): ("trine", 2.38),
        frozenset(("Jupiter", "Saturn")): ("opposition", 0.25),
    }
    traditional = ("SO", "MO", "ME", "VE", "MA", "JU", "SA")
    chart = build_chart(
        "1970-01-01", "00:00:00", "W", latitude=0.0, longitude=0.0, utc_offset=0.0
    )
    ours = {
        frozenset((a["first"]["name"], a["second"]["name"])): (a["name"], a["orb"])
        for a in wheel.aspects_between(
            [b for b in chart["bodies"] if b.get("code") in traditional]
        )
    }
    for pair, (name, orb) in published.items():
        assert pair in ours, f"{tuple(pair)} missing"
        assert ours[pair][0] == name
        assert abs(ours[pair][1] - orb) < 0.03, f"{tuple(pair)}: {ours[pair][1]}"


# --- The bi-wheel ----------------------------------------------------------
# A transit formula names a moment. This is what that moment looks like drawn
# around the chart it was measured against.

def _pair():
    from app.service import build_chart

    natal = build_chart(
        "1985-06-15", "14:30:00", "R",
        latitude=41 + 23 / 60, longitude=2 + 10 / 60, timezone_name="Europe/Madrid",
    )
    moving = build_chart(
        "2027-02-19", "19:45:00", "R",
        latitude=41 + 23 / 60, longitude=2 + 10 / 60, utc_offset=0.0,
    )
    return natal, moving


def test_a_bi_wheel_carries_both_sets_of_planets():
    from app.wheel import DRAWN, render_transits

    svg = render_transits(*_pair())
    assert svg.count("gl planet") == len(DRAWN)
    assert svg.count("gl transit") == len(DRAWN)


def test_the_two_rings_do_not_sit_on_top_of_each_other():
    """The whole point of a bi-wheel is telling the two charts apart."""
    from app.wheel import BI_NATAL, BI_TRANSIT

    assert BI_TRANSIT.glyph > BI_NATAL.glyph
    # Room for a glyph and its degree between the two, or they read as one ring.
    assert BI_TRANSIT.degree - BI_NATAL.glyph >= 40
    # The natal pointer ticks land on the divider, not on the zodiac, so the
    # two sets of leader lines never share a rim.
    assert BI_NATAL.rim < BI_TRANSIT.rim


def test_the_single_wheel_is_untouched_by_the_bi_wheel():
    """The chart page must look exactly as it did."""
    from app.wheel import SINGLE, R_OUTER, R_SIGNS, R_GLYPH, R_DEGREE
    from app.wheel import R_NUMBERS, R_HOUSES, R_ASPECTS

    assert SINGLE.outer == R_OUTER
    assert SINGLE.signs == R_SIGNS == SINGLE.rim
    assert SINGLE.glyph == R_GLYPH
    assert SINGLE.degree == R_DEGREE
    assert SINGLE.numbers == R_NUMBERS
    assert SINGLE.houses == R_HOUSES
    assert SINGLE.aspects == R_ASPECTS


def test_only_the_crossing_aspects_are_counted():
    """A natal chart's own aspects belong on its own page."""
    from app.wheel import crossing_aspects, _for_wheel

    natal, moving = _pair()
    inner, outer = _for_wheel(natal), _for_wheel(moving)
    crossings = crossing_aspects(outer, inner)

    assert crossings, "a year's transits should touch a birth chart somewhere"
    for aspect in crossings:
        assert aspect["moving"] in outer
        assert aspect["natal"] in inner


def test_the_crossings_are_ordered_by_how_exact_they_are():
    """The tightest aspect is the one the astrologer wants first."""
    from app.wheel import crossing_aspects, _for_wheel

    natal, moving = _pair()
    orbs_found = [
        a["orb"] for a in crossing_aspects(_for_wheel(moving), _for_wheel(natal))
    ]
    assert orbs_found == sorted(orbs_found)


def test_a_crossing_names_both_charts_in_its_title():
    """Hovering a chord should say which body is which."""
    from app.wheel import render_transits

    svg = render_transits(*_pair())
    assert "<title>transiting " in svg
    assert " natal " in svg


def test_the_transit_wheel_stays_put_while_the_aspects_scroll():
    """Thirty-odd aspects is a column of reading, and the wheel is the thing
    being read against. It pins, the way the chart page's does."""
    from app.views import transits_page, page

    html = transits_page(*_pair(), "2027-02-19T19:45:00Z")
    assert 'class="card chartcard nobar"' in html

    styles = page("x", "", tab="search")
    assert ".chartcard { position: sticky;" in styles
    # No sticky bar over this page, so it starts at the top of the viewport.
    assert ".chartcard.nobar { top: 16px; }" in styles
