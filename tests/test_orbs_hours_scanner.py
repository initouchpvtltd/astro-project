from datetime import datetime, timezone

import pytest

from app import orbs, planetary_hours
from app.scanner import ScanError, scan

MADRID = (40.4165, -3.7026)


# --- orbs -----------------------------------------------------------------

@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("SO", "MO", 13.5),   # his table says 13 degrees 30
        ("SO", "ME", 11.0),
        ("ME", "VE", 7.0),
        ("JU", "SA", 9.0),
        ("SO", "JU", 12.0),
        ("MO", "VE", 9.5),    # 9 degrees 30
    ],
)
def test_moiety_pairs_match_the_clients_table(first, second, expected):
    """Every cell in his orb image is the mean of the two bodies' orbs."""
    assert orbs.allowance(first, second, 120, "moiety") == expected


def test_moieties_ignore_which_aspect_it_is():
    assert orbs.allowance("SO", "MO", 0, "moiety") == orbs.allowance("SO", "MO", 150, "moiety")


def test_fixed_orbs_come_from_the_aspect_not_the_pair():
    """The ZET file gives 9 on the majors and much less on the minors."""
    assert orbs.allowance("SO", "MO", 120, "fixed") == 9.0
    assert orbs.allowance("SO", "MO", 30, "fixed") == 1.5


def test_fixed_orbs_separate_luminaries_from_planets():
    assert orbs.allowance("ME", "MA", 120, "fixed") == 8.5
    assert orbs.allowance("SO", "MA", 120, "fixed") == 9.0


def test_an_unknown_body_falls_back_rather_than_failing():
    """A formula should never be refused because of a missing orb."""
    assert orbs.allowance("SO", "ZZ", 120, "moiety") > 0


def test_an_unknown_orb_system_is_refused():
    with pytest.raises(orbs.UnknownOrbSystem, match="moiety"):
        orbs.allowance("SO", "MO", 120, "invented")


@pytest.mark.parametrize(
    "first,second,expected",
    [(350, 10, 20), (10, 350, 20), (0, 180, 180), (120, 0, 120), (0, 0, 0)],
)
def test_separation_takes_the_short_way_round(first, second, expected):
    assert orbs.separation(first, second) == pytest.approx(expected)


def test_signed_separation_says_which_is_ahead():
    assert orbs.signed_separation(10, 350) > 0
    assert orbs.signed_separation(350, 10) < 0


# --- planetary hours ------------------------------------------------------

def test_the_first_hour_after_sunrise_belongs_to_the_day_ruler():
    """This is why the days are named after planets.

    21 June 2026 is a Sunday, so the first hour after sunrise is the Sun's.
    """
    result = planetary_hours.hour_at(
        datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc), *MADRID
    )
    assert result["is_day"] is True
    assert result["hour"] == 1
    assert result["ruler"] == "SO"
    assert result["day_ruler"] == "SO"


def test_the_twenty_fifth_hour_starts_the_next_weekday():
    """The Chaldean cycle is what produces the order of the week.

    Twenty-four hours on from a day's ruler lands on the next day's ruler, for
    every day. If this holds, the sequence is right.
    """
    order = planetary_hours.CHALDEAN_ORDER
    for index, ruler in enumerate(planetary_hours.WEEKDAY_RULERS):
        following = order[(order.index(ruler) + 24) % 7]
        assert following == planetary_hours.WEEKDAY_RULERS[(index + 1) % 7]


def test_before_sunrise_belongs_to_the_previous_day():
    """The astrological day begins at sunrise, not midnight."""
    early = planetary_hours.hour_at(
        datetime(2026, 6, 21, 2, 0, tzinfo=timezone.utc), *MADRID
    )
    assert early["is_day"] is False
    assert early["day_ruler"] == "SA"  # still Saturday


def test_day_hours_are_longer_than_sixty_minutes_in_summer():
    """Unequal hours are the whole point: daylight divided by twelve."""
    midsummer = planetary_hours.hour_at(
        datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc), *MADRID
    )
    midwinter = planetary_hours.hour_at(
        datetime(2026, 12, 21, 12, 0, tzinfo=timezone.utc), *MADRID
    )
    assert midsummer["is_day"] and midwinter["is_day"]


@pytest.mark.parametrize("when", ["2026-06-21", "2026-12-21"])
def test_polar_latitudes_are_refused_clearly(when):
    """Above the polar circle the Sun may not rise or set for weeks."""
    moment = datetime.strptime(when, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    with pytest.raises(planetary_hours.NoSunriseOrSunset, match="polar"):
        planetary_hours.hour_at(moment, 69.65, 18.96)


# --- scanner --------------------------------------------------------------

JAN = datetime(2027, 1, 1, tzinfo=timezone.utc)
MAR = datetime(2027, 3, 31, tzinfo=timezone.utc)
YEAR_END = datetime(2027, 12, 31, tzinfo=timezone.utc)


def test_mercury_stations_six_times_in_a_year():
    """Three retrograde periods, two stations each."""
    result = scan("Mer.S", JAN, YEAR_END, step_seconds=900)
    assert result["found"] == 6
    assert result["warnings"] == []


def test_a_coarse_step_misses_stations_and_says_so():
    """A station lasts about an hour, so a daily step strides over it.

    Reporting nothing without explanation would look like a correct answer.
    """
    result = scan("Mer.S", JAN, YEAR_END, step_seconds=86400)
    assert result["found"] < 6
    assert result["warnings"], "a coarse step should warn"


def test_the_sun_and_moon_trine_twice_a_month():
    result = scan("Sun.120.Moon", JAN, MAR, step_seconds=3600)
    assert result["found"] == 6  # waxing and waning, three months


def test_there_is_one_new_moon_a_month():
    assert scan("Sun.0.Moon", JAN, MAR, step_seconds=3600)["found"] == 3


def test_a_wider_orb_gives_longer_windows():
    """The same aspects, held for longer. This is the orb system working."""
    wide = scan("Sun.120.Moon", JAN, MAR, step_seconds=3600, orb_system="moiety")
    tight = scan("Sun.120.Moon", JAN, MAR, step_seconds=3600, orb_system="fixed")
    assert wide["found"] == tight["found"]
    assert min(i["duration_hours"] for i in wide["intervals"]) > max(
        i["duration_hours"] for i in tight["intervals"]
    )


def test_house_formulas_need_a_location():
    with pytest.raises(ScanError, match="location"):
        scan("Mar.H7", JAN, MAR, step_seconds=86400)


def test_house_formulas_work_with_a_location():
    result = scan("Mar.H7", JAN, MAR, step_seconds=3600, latitude=MADRID[0], longitude=MADRID[1])
    # A house passes beneath a body once a day as the earth turns.
    assert 80 <= result["found"] <= 95


def test_planetary_hour_formulas_need_a_location():
    with pytest.raises(ScanError, match="location"):
        scan("mo.pln_hour", JAN, MAR, step_seconds=86400)


def test_only_what_the_formula_asks_for_is_calculated():
    """Sunrise searches are expensive, so a formula without hours skips them."""
    from app.formula.parser import parse
    from app.scanner import requirements

    simple = requirements(parse("Sun.120.Moon"))
    assert simple.bodies == {"SO", "MO"}
    assert simple.houses is False and simple.planetary_hours is False

    complex_ = requirements(parse("Mar.H7 & mo.pln_hour"))
    assert complex_.houses is True and complex_.planetary_hours is True


def test_a_backwards_range_is_refused():
    with pytest.raises(ScanError, match="after the start"):
        scan("Sun.Ari", MAR, JAN)


def test_too_fine_a_step_is_refused():
    with pytest.raises(ScanError, match="smallest step"):
        scan("Sun.Ari", JAN, MAR, step_seconds=1)


def test_too_many_steps_is_refused_with_a_suggestion():
    """The cap protects the server, and the message says how to get under it."""
    with pytest.raises(ScanError, match="Use a step of at least"):
        scan("Sun.Ari", JAN, YEAR_END, step_seconds=60)


def test_the_result_explains_the_formula_in_words():
    assert scan("Sun.120.Moon", JAN, MAR)["reading"] == "Sun trine Moon"


def test_intervals_carry_their_own_length():
    result = scan("Sun.0.Moon", JAN, MAR, step_seconds=3600)
    assert all(i["duration_hours"] > 0 for i in result["intervals"])
