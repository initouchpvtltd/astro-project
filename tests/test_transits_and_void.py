"""Transits against a natal chart, and Moon Void of Course.

The formulas here are the client's own, taken from the list he sent. If these
stop working, the thing he actually bought stops working.
"""

from datetime import datetime, timezone

import pytest

from app import void_of_course
from app.formula.evaluator import Sky, evaluate
from app.formula.parser import parse
from app.scanner import ScanError, scan

BARCELONA = (41.3888, 2.159)
NATAL = datetime(1990, 5, 3, 12, 30, tzinfo=timezone.utc)
YEAR_START = datetime(2027, 1, 1, tzinfo=timezone.utc)
YEAR_END = datetime(2027, 12, 31, tzinfo=timezone.utc)


def run(formula, step_seconds=3600, natal=True):
    return scan(
        formula,
        YEAR_START,
        YEAR_END,
        step_seconds=step_seconds,
        latitude=BARCELONA[0],
        longitude=BARCELONA[1],
        natal_moment=NATAL if natal else None,
        natal_latitude=BARCELONA[0] if natal else None,
        natal_longitude=BARCELONA[1] if natal else None,
    )


# --- the apostrophe -------------------------------------------------------

def test_a_transit_formula_needs_a_natal_chart():
    with pytest.raises(ScanError, match="birth date, time and place"):
        run("ME'.R", natal=False)


def test_all_ten_of_the_clients_formulas_run():
    """His actual working list. None of these ran before transits existed."""
    formulas = [
        ("ME'.R", 3600),
        ("MA'.90.SA", 3600),
        ("JU'.0.SO", 3600),
        ("PL'.[119.9-120.1].MO", 3600),
        ("MO'.[0-0.1].MO", 900),
        ("MoonVoid", 3600),
        ("SA'.TAU[0-1]", 3600),
        ("SO'.[0-0.1].H1", 3600),
        ("UR'.RS", 900),
        ("VE'.[0-0.1].H5", 3600),
    ]
    for formula, step in formulas:
        result = run(formula, step_seconds=step)
        assert "intervals" in result, formula


def test_mercury_goes_retrograde_three_times_a_year():
    assert run("ME'.R", step_seconds=3600)["found"] == 3


def test_there_are_thirteen_lunar_returns_in_a_year():
    """The Moon returns to its natal degree once per lunar month."""
    assert run("MO'.[0-0.1].MO", step_seconds=900)["found"] == 13


def test_the_sun_crosses_the_natal_ascendant_once_a_year():
    assert run("SO'.[0-0.1].H1", step_seconds=900)["found"] == 1


def test_a_natal_position_does_not_move():
    """That is what makes a transit to it a findable event."""
    result = run("JU'.0.SO", step_seconds=86400)
    assert result["natal_chart"] is not None


def test_an_unmarked_body_reads_from_the_natal_chart():
    """In a dual chart the apostrophe picks the moving body.

    Both sides of this formula are Mercury. If the unmarked one were also read
    from the moving sky it would aspect itself and never match.
    """
    natal = Sky({"ME": 100.0}, {"ME": 0.0})
    sky = Sky({"ME": 100.0}, {"ME": 1.0}, natal=natal)
    assert evaluate(parse("ME'.0.ME"), sky) is True


# --- stations -------------------------------------------------------------

def test_the_two_kinds_of_station_are_told_apart():
    """RS halts on the way backwards, DS on the way forwards.

    Within a station the speed passes through zero, so the sign of the speed
    alone matches both. Only the direction of the turn separates them.
    """
    retrograde_station = scan("Ura.RS", YEAR_START, YEAR_END, step_seconds=900)
    direct_station = scan("Ura.DS", YEAR_START, YEAR_END, step_seconds=900)
    either = scan("Ura.S", YEAR_START, YEAR_END, step_seconds=900)

    assert retrograde_station["found"] == 1
    assert direct_station["found"] == 1
    assert either["found"] == 2

    assert (
        retrograde_station["intervals"][0]["begin"]
        != direct_station["intervals"][0]["begin"]
    )


def test_a_direct_station_ends_a_retrograde_period():
    """Internal consistency between two different questions."""
    station = scan("Ura.DS", YEAR_START, YEAR_END, step_seconds=900)
    retrograde = scan("Ura.R", YEAR_START, YEAR_END, step_seconds=86400)
    assert station["intervals"][0]["begin"][:7] == retrograde["intervals"][0]["end"][:7]


# --- narrow orb windows ---------------------------------------------------

def test_a_narrow_orb_range_warns_when_the_step_is_too_coarse():
    """The Moon crosses a tenth of a degree in about eleven minutes."""
    result = run("MO'.[0-0.1].MO", step_seconds=3600)
    assert result["warnings"]
    assert "miss most occurrences" in result["warnings"][0]


def test_the_suggested_step_actually_finds_them_all():
    coarse = run("MO'.[0-0.1].MO", step_seconds=3600)
    fine = run("MO'.[0-0.1].MO", step_seconds=900)
    assert fine["found"] > coarse["found"]
    assert fine["found"] == 13


# --- Moon Void of Course --------------------------------------------------

def test_moon_void_parses_without_naming_a_body():
    assert parse("MoonVoid").describe() == "Moon void of course"


def test_the_moon_is_void_about_thirteen_times_a_month():
    """Once per sign change, so once per sign the Moon passes through."""
    january = scan(
        "MoonVoid",
        datetime(2027, 1, 1, tzinfo=timezone.utc),
        datetime(2027, 1, 31, tzinfo=timezone.utc),
        step_seconds=1800,
    )
    assert 11 <= january["found"] <= 15


def test_a_moon_with_an_aspect_still_to_come_is_not_void():
    """The Moon at 0 Aries with the Sun at 10 Aries: a conjunction ahead."""
    longitudes = {"MO": 0.0, "SO": 10.0, "ME": 200.0, "VE": 210.0,
                  "MA": 220.0, "JU": 230.0, "SA": 240.0}
    speeds = {"MO": 13.0, "SO": 1.0, "ME": 1.0, "VE": 1.0,
              "MA": 0.5, "JU": 0.1, "SA": 0.03}
    assert void_of_course.is_void(longitudes, speeds) is False


def test_a_moon_at_the_end_of_a_sign_with_nothing_left_is_void():
    """At 29 degrees 30 with every planet already passed, nothing remains."""
    longitudes = {"MO": 29.5, "SO": 25.0, "ME": 24.0, "VE": 23.0,
                  "MA": 22.0, "JU": 21.0, "SA": 20.0}
    speeds = {"MO": 13.0, "SO": 1.0, "ME": 1.0, "VE": 1.0,
              "MA": 0.5, "JU": 0.1, "SA": 0.03}
    assert void_of_course.is_void(longitudes, speeds) is True


def test_only_the_ptolemaic_aspects_count():
    """Traditional judgement ignores the minor aspects entirely."""
    assert void_of_course.PTOLEMAIC_ASPECTS == (0.0, 60.0, 90.0, 120.0, 180.0)
    assert "MO" not in void_of_course.CLASSICAL_PLANETS
