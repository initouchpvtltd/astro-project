from datetime import timezone

import pytest

from app.constants import STATIONARY_THRESHOLD_DEG_PER_DAY
from app.ephemeris import calculate_chart, format_position, julian_day, to_utc


def test_utc_offset_is_subtracted():
    """12:00 in GMT+2 is 10:00 UTC."""
    moment = to_utc("2026-05-14", "12:00:00", 2.0)
    assert moment.hour == 10
    assert moment.tzinfo == timezone.utc


def test_utc_offset_can_cross_midnight():
    moment = to_utc("2026-05-14", "00:30:00", 2.0)
    assert (moment.year, moment.month, moment.day, moment.hour) == (2026, 5, 13, 22)


def test_julian_day_matches_known_epoch():
    """J2000.0 is 2000-01-01 12:00 UT, Julian Day 2451545.0."""
    assert julian_day(to_utc("2000-01-01", "12:00:00", 0.0)) == pytest.approx(2451545.0)


def test_format_position_splits_into_sign_and_degrees():
    # 53.5 degrees is 23.5 degrees into Taurus.
    result = format_position(53.5)
    assert result["sign"] == "Taurus"
    assert (result["degree"], result["minute"], result["second"]) == (23, 30, 0)


def test_format_position_carries_rounded_seconds():
    """59'59.6" must print as 30 degrees exactly, not 29 degrees 59'60"."""
    result = format_position(29.99999)
    assert result["second"] != 60
    assert result["minute"] != 60
    assert (result["sign"], result["degree"]) == ("Aries", 30) or result["sign"] == "Taurus"


def test_format_position_wraps_past_360():
    assert format_position(370.0)["sign"] == "Aries"


def _chart():
    return calculate_chart("2026-05-14", "12:00:00", 2.0, 40.4168, -3.7038, "R")


def test_every_body_calculates():
    from app.constants import BODIES

    bodies = _chart()["bodies"]
    assert len(bodies) == len(BODIES)
    failures = [b["name"] for b in bodies if "error" in b]
    assert not failures, f"bodies failed to calculate: {failures}"


def test_south_node_is_opposite_north_node():
    bodies = {b["name"]: b for b in _chart()["bodies"]}
    separation = (bodies["South Node"]["longitude"] - bodies["North Node"]["longitude"]) % 360
    assert separation == pytest.approx(180.0, abs=1e-6)


def test_retrograde_flag_follows_speed():
    for body in _chart()["bodies"]:
        if body["motion"] == "retrograde":
            assert body["speed_deg_per_day"] <= -STATIONARY_THRESHOLD_DEG_PER_DAY
        elif body["motion"] == "direct":
            assert body["speed_deg_per_day"] >= STATIONARY_THRESHOLD_DEG_PER_DAY
        else:
            assert abs(body["speed_deg_per_day"]) < STATIONARY_THRESHOLD_DEG_PER_DAY


def test_houses_are_regiomontanus_by_default():
    houses = _chart()["houses"]
    assert houses["system_name"] == "Regiomontanus"
    assert len(houses["cusps"]) == 12
    assert houses["cusps"][0]["longitude"] == pytest.approx(
        houses["ascendant"]["longitude"], abs=1e-6
    )


def test_house_system_is_switchable():
    placidus = calculate_chart("2026-05-14", "12:00:00", 2.0, 40.4168, -3.7038, "P")
    assert placidus["houses"]["system_name"] == "Placidus"


def test_unknown_house_system_is_rejected():
    with pytest.raises(ValueError, match="Unknown house system"):
        calculate_chart("2026-05-14", "12:00:00", 2.0, 40.4168, -3.7038, "Z")


def test_sun_moves_about_one_degree_a_day():
    sun = next(b for b in _chart()["bodies"] if b["name"] == "Sun")
    assert 0.95 < sun["speed_deg_per_day"] < 1.02


def test_data_files_are_actually_in_use():
    """Guards the silent Moshier fallback.

    The ephe/ directory ships with the repository, so any deployment that ends
    up on Moshier has a path problem. Positions would still look plausible but
    disagree with ZET in the arcseconds, which is exactly the failure this
    milestone exists to rule out.
    """
    from app.ephemeris import EPHEMERIS_SOURCE

    assert EPHEMERIS_SOURCE.startswith("Swiss Ephemeris data files"), EPHEMERIS_SOURCE


def test_chiron_resolves_from_the_asteroid_file():
    """Chiron exists only in seas_18.se1, so it proves the files loaded."""
    chiron = next(b for b in _chart()["bodies"] if b["name"] == "Chiron")
    assert "error" not in chiron, chiron.get("error")


def test_sun_is_at_zero_aries_on_the_equinox():
    """The March equinox is defined as the Sun reaching 0 degrees Aries.

    This checks the ephemeris against astronomy rather than against itself.
    Almanacs place the 2026 equinox at 20 March, 14:46 UTC.
    """
    sun = next(
        b
        for b in calculate_chart("2026-03-20", "14:46:00", 0.0, 0.0, 0.0, "R")["bodies"]
        if b["name"] == "Sun"
    )
    assert sun["longitude"] % 360 == pytest.approx(0.0, abs=0.001)


@pytest.mark.parametrize("system", ["P", "K"])
def test_quadrant_systems_fail_clearly_beyond_the_polar_circle(system):
    """Placidus and Koch have no solution at high latitudes.

    swisseph raises an opaque error there, which would surface as a 500. The
    caller should get an explanation and a usable alternative instead.
    """
    with pytest.raises(ValueError, match="beyond the polar circle"):
        calculate_chart("2026-06-21", "12:00:00", 0.0, 78.0, 15.0, system)


@pytest.mark.parametrize("system", ["R", "C", "W"])
def test_suggested_alternatives_work_beyond_the_polar_circle(system):
    """The systems the error message recommends must actually work there."""
    chart = calculate_chart("2026-06-21", "12:00:00", 0.0, 78.0, 15.0, system)
    assert len(chart["houses"]["cusps"]) == 12


@pytest.mark.parametrize("date", ["1800-01-02", "2399-12-30"])
def test_ephemeris_covers_its_stated_date_range(date):
    """The bundled .se1 files cover 1800 to 2399."""
    chart = calculate_chart(date, "12:00:00", 0.0, 51.5, -0.13, "R")
    assert not [b["name"] for b in chart["bodies"] if "error" in b]


# --- how a degree is written down ------------------------------------------
# The client reported a reading of 20°23'60" and asked for figures rounded to
# the minute, the way Astro-Seek prints them. Sixty of anything is never a
# valid reading, and neither is a thirtieth degree of a sign.

import random

from app.ephemeris import format_position


def _every_awkward_longitude():
    """Values that sit where a carry is about to happen, plus a wide sample."""
    cases = [
        (degree + fraction) % 360.0
        for degree in range(360)
        for fraction in (0, .5, .9, .99, .999, .9999, .99999, .999999)
    ]
    cases += [
        10 + minute / 60 + second / 3600
        for minute in range(60)
        for second in (59.4, 59.5, 59.6, 59.9, 59.99, 59.999)
    ]
    random.seed(20260518)
    cases += [random.uniform(0, 360) for _ in range(50000)]
    return cases


def test_no_reading_ever_shows_sixty():
    for longitude in _every_awkward_longitude():
        place = format_position(longitude)
        assert place["second"] < 60, place["formatted"]
        assert place["minute"] < 60, place["formatted"]
        assert place["minute_to_minute"] < 60, place["formatted_to_minute"]


def test_no_reading_ever_shows_a_thirtieth_degree():
    """A sign has thirty degrees, numbered 0 to 29. There is no 30th."""
    for longitude in _every_awkward_longitude():
        place = format_position(longitude)
        assert place["degree"] < 30, place["formatted"]
        assert place["degree_to_minute"] < 30, place["formatted_to_minute"]


def test_the_end_of_a_sign_carries_into_the_next_one():
    """This is the carry a field-by-field rounding forgets."""
    almost_virgo = 120 + 29 + 59 / 60 + 59.7 / 3600       # 29°59'59.7" Leo
    assert format_position(almost_virgo)["formatted"] == "0°00'00\" Virgo"


def test_the_minute_form_cuts_the_seconds_off_rather_than_rounding():
    """Astro-Seek truncates, and the client checks every figure against it.

    On their own traditional chart for 1 January 1970, fourteen of fifteen
    positions agree with the seconds simply dropped and only seven agree if
    they are rounded, so dropping them is what matches.
    """
    libra = 180 + 10 + 29 / 60 + 46 / 3600
    assert format_position(libra)["formatted"] == "10°29'46\" Libra"
    assert format_position(libra)["formatted_to_minute"] == "10°29' Libra"


def test_the_seconds_themselves_are_still_rounded():
    """They are the last unit kept, so the arcsecond after has to go somewhere."""
    almost = 10 + 20 / 60 + 53.7 / 3600
    assert format_position(almost)["second"] == 54


def test_astro_seek_agrees_position_for_position():
    """The guard that matters: their published figures for a known chart.

    Read off Astro-Seek's own traditional chart page for 1 January 1970,
    00:00 UT at 0°N 0°E, Whole Sign houses.
    """
    from app.service import build_chart

    chart = build_chart(
        "1970-01-01", "00:00:00", "W", latitude=0.0, longitude=0.0, utc_offset=0.0
    )
    published = {
        "SO": (10, 9), "MO": (10, 41), "ME": (29, 1), "VE": (4, 27),
        "MA": (12, 14), "JU": (2, 19), "SA": (2, 3),
    }
    for code, expected in published.items():
        place = next(b for b in chart["bodies"] if b["code"] == code)["position"]
        assert (place["degree_to_minute"], place["minute_to_minute"]) == expected, (
            f'{code}: {place["formatted_to_minute"]}'
        )

    lots = {
        "fortune": (10, 35), "spirit": (11, 40), "eros": (18, 20),
        "victory": (20, 28), "necessity": (29, 33), "courage": (12, 46),
        "nemesis": (2, 36),
    }
    for lot in chart["lots"]["lots"]:
        place = lot["position"]
        assert (place["degree_to_minute"], place["minute_to_minute"]) == lots[lot["key"]], (
            f'{lot["name"]}: {place["formatted_to_minute"]}'
        )


def test_the_page_prints_minutes_and_not_seconds():
    """Matching Astro-Seek's own tables, which stop at the minute."""
    from app.views import chart_table
    from app.service import build_chart

    chart = build_chart(
        "1997-05-18", "20:38:00", "R",
        latitude=30.3017, longitude=71.9321, timezone_name="Asia/Karachi",
    )
    table = chart_table(chart)
    assert "&Prime;" not in table, "seconds should not reach the page"
    assert "&prime;" in table


def test_the_api_still_carries_the_seconds():
    """The display rounds; the data must not, or precision is lost for good."""
    from app.service import build_chart

    chart = build_chart(
        "1997-05-18", "20:38:00", "R",
        latitude=30.3017, longitude=71.9321, timezone_name="Asia/Karachi",
    )
    sun = next(b for b in chart["bodies"] if b["code"] == "SO")
    assert "second" in sun["position"]
    assert '"' in sun["position"]["formatted"]


def test_the_nodes_are_the_mean_node():
    """Astro-Seek's traditional chart prints the mean node, labelled "Node (M)".

    The true node wanders up to about a degree and a half either side of it,
    which is enough to read as a mistake when the two charts sit side by side.
    """
    from app.service import build_chart

    chart = build_chart(
        "1970-01-01", "00:00:00", "W", latitude=0.0, longitude=0.0, utc_offset=0.0
    )
    north = next(b for b in chart["bodies"] if b["code"] == "KN")["position"]
    assert (north["degree_to_minute"], north["minute_to_minute"]) == (15, 17)
    assert north["sign_to_minute"] == "Pisces"


def test_the_south_node_stays_opposite_the_north():
    from app.service import build_chart

    chart = build_chart(
        "1970-01-01", "00:00:00", "W", latitude=0.0, longitude=0.0, utc_offset=0.0
    )
    north = next(b for b in chart["bodies"] if b["code"] == "KN")["longitude"]
    south = next(b for b in chart["bodies"] if b["code"] == "SN")["longitude"]
    assert abs(((south - north) % 360.0) - 180.0) < 1e-6


def test_the_barcelona_chart_the_client_checked_against_astro_seek():
    """Every figure from the chart the client sent back, 15 July 2026.

    Astro-Seek's traditional chart for 12:00 CEST at Barcelona, read off their
    page: six house cusps, seven planets and all seven Lots. Their gazetteer
    puts Barcelona at 41 degrees 23 minutes north, 2 degrees 10 minutes east,
    which is where a city lookup now lands.

    This is the chart that exposed the coordinate difference, so it is the one
    worth holding still.
    """
    from app.service import build_chart

    chart = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=41 + 23 / 60, longitude=2 + 10 / 60,
        timezone_name="Europe/Madrid",
    )

    cusps = {1: (26, 24), 2: (20, 46), 3: (19, 48), 5: (2, 13), 6: (1, 49), 10: (25, 48)}
    for cusp in chart["houses"]["cusps"]:
        if cusp["house"] in cusps:
            place = cusp["position"]
            assert (place["degree_to_minute"], place["minute_to_minute"]) == cusps[
                cusp["house"]
            ], f'house {cusp["house"]}: {place["formatted_to_minute"]}'

    planets = {
        "SO": (22, 57), "MO": (7, 2), "ME": (19, 13), "VE": (6, 18),
        "MA": (11, 41), "JU": (3, 17), "SA": (14, 38),
    }
    for code, expected in planets.items():
        place = next(b for b in chart["bodies"] if b["code"] == code)["position"]
        assert (place["degree_to_minute"], place["minute_to_minute"]) == expected, (
            f'{code}: {place["formatted_to_minute"]}'
        )

    lots = {
        "fortune": (10, 30), "spirit": (12, 18), "necessity": (17, 40),
        "eros": (20, 23), "courage": (25, 12), "victory": (17, 23),
        "nemesis": (22, 16),
    }
    for lot in chart["lots"]["lots"]:
        place = lot["position"]
        assert (place["degree_to_minute"], place["minute_to_minute"]) == lots[
            lot["key"]
        ], f'{lot["name"]}: {place["formatted_to_minute"]}'


def test_rounding_the_minutes_would_break_that_chart():
    """Guarding the decision, not just the output.

    The client read the difference as a rounding fault. It was not: on this
    chart thirteen of the twenty figures sit above thirty seconds, and Astro-
    Seek prints the lower minute for every one of them. Rounding would move
    those away from their page, not towards it.
    """
    from app.service import build_chart

    chart = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=41 + 23 / 60, longitude=2 + 10 / 60,
        timezone_name="Europe/Madrid",
    )
    published = {
        "Sun": (22, 57), "Moon": (7, 2), "Mercury": (19, 13), "Venus": (6, 18),
        "Mars": (11, 41), "Jupiter": (3, 17), "Saturn": (14, 38),
    }
    would_differ = 0
    for body in chart["bodies"]:
        if body["name"] not in published:
            continue
        place = body["position"]
        if place["second"] >= 30:
            would_differ += 1
            assert (place["degree_to_minute"], place["minute_to_minute"]) == published[
                body["name"]
            ], f'{body["name"]} is published at the lower minute'
    assert would_differ >= 3, "the chart should still discriminate the two rules"


# --- The place, written out ------------------------------------------------
# Astro-Seek prints the coordinates beside the city, and the client reads the
# two pages side by side.

def test_the_page_shows_the_coordinates_beside_the_city():
    from app.views import chart_page
    from app.service import build_chart

    chart = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=41 + 23 / 60, longitude=2 + 10 / 60,
        timezone_name="Europe/Madrid",
    )
    chart["location"] = {**chart["location"], "name": "Barcelona"}
    page = chart_page(chart, {})
    assert "41°23′N, 2°10′E" in page


def test_a_city_needs_no_seconds_in_its_coordinates():
    """It resolves on the minute, so seconds would be three empty characters."""
    from app.views import _coordinates

    written = _coordinates(
        {"location": {"latitude": 41 + 23 / 60, "longitude": 2 + 10 / 60}, "input": {}}
    )
    assert written == "41°23′N, 2°10′E"
    assert "″" not in written


def test_coordinates_typed_by_hand_keep_their_seconds():
    """Rounding them to the minute would throw away what the caller gave us."""
    from app.views import _coordinates

    written = _coordinates(
        {"location": {"latitude": 41.38879, "longitude": 2.15899}, "input": {}}
    )
    assert written == "41°23′20″N, 2°09′32″E"


def test_the_southern_and_western_hemispheres_are_named():
    from app.views import _coordinates

    assert _coordinates(
        {"location": {"latitude": -33.8688, "longitude": 151.2093}, "input": {}}
    ).endswith("151°12′33″E")
    assert _coordinates(
        {"location": {"latitude": -33.8688, "longitude": 151.2093}, "input": {}}
    ).startswith("33°52′08″S")
    assert "74°00′22″W" in _coordinates(
        {"location": {"latitude": 40.7128, "longitude": -74.0060}, "input": {}}
    )


def test_a_chart_with_no_location_at_all_does_not_break_the_page():
    from app.views import _coordinates

    assert _coordinates({"location": {}, "input": {}}) is None


# --- The forms say what they need ------------------------------------------

def test_the_fields_a_form_cannot_do_without_are_marked():
    from app.views import chart_form, search_form

    chart = chart_form()
    for needed in ("Date", "Time", "Place"):
        assert f'<label>{needed}<span class="req"' in chart, needed
    # A house system is chosen for you, so it is not the caller's to supply.
    assert '<label>House system</label>' in chart

    search = search_form()
    for needed in ("Or write your own", "From", "To"):
        assert f'<label>{needed}<span class="req"' in search, needed
    for optional in ("Precision", "Orbs"):
        assert f'<label>{optional}</label>' in search, optional


def test_the_natal_fields_say_when_they_are_needed():
    """They are required by the formula, not by the form.

    An apostrophe in the formula is what asks for a natal chart, so that is
    when the star appears. Marking them always would be a lie to anyone
    searching with a formula that never reads them.
    """
    from app.views import search_form

    assert "needed for formulas with an apostrophe" in search_form()

    plain = search_form({"formula": "MA.90.SA"})
    assert 'class=""' in plain, "no natal chart is being asked for"

    transit = search_form({"formula": "MA'.90.SA"})
    assert 'class="wants-natal"' in transit

    # The markup is the same either way; only the form's class differs, so the
    # star can follow the formula box without a page load.
    for field in ("Birth date", "Birth time", "Birth place"):
        assert f'{field}<span class="req req-natal"' in transit, field
        assert f'{field}<span class="req req-natal"' in plain, field


def test_no_error_a_reader_sees_names_a_field_in_the_api():
    """The page says 'Birth place'. An error that says natal_city is for us."""
    import pydantic
    from app.models import SearchRequest

    with pytest.raises(pydantic.ValidationError) as caught:
        SearchRequest(
            formula="MA'.90.SA", start="2027-01-01", end="2027-12-31",
            natal_date="2018-02-15", natal_time="14:30:00",
        )
    message = caught.value.errors()[0]["msg"]
    assert "natal_city" not in message
    assert "natal_latitude" not in message
    assert "birth place" in message.lower()


# --- Coordinates stay out of the way until they are wanted -----------------
# Three fields per place, on two places, is a form twice the length of the
# question. A reader wants a place name; the figures are for the day the name
# is ambiguous.

def test_the_coordinate_fields_start_folded_away():
    from app.views import chart_form, search_form

    for form in (chart_form(), search_form()):
        assert 'class="fold"' in form
        assert 'class="fold" checked' not in form
        assert "Enter coordinates instead of a place" in form


def test_a_form_that_comes_back_with_coordinates_shows_them():
    """Folding away what the reader just typed would be a disappearing act."""
    from app.views import chart_form, search_form

    assert 'class="fold" checked' in chart_form({"latitude": "41.3833"})
    assert 'class="fold" checked' in chart_form({"tz": "Europe/Madrid"})
    assert 'class="fold" checked' in search_form({"natal_latitude": "41.3833"})
    assert 'class="fold" checked' in search_form({"longitude": "2.1667"})


def test_each_place_folds_on_its_own():
    """Opening the birth coordinates should not open the search's."""
    from app.views import search_form
    import re

    folds = re.findall(r'id="([a-z-]+)" class="fold"( checked)?', search_form(
        {"natal_latitude": "41.3833"}
    ))
    assert dict((name, bool(on)) for name, on in folds) == {
        "search-coords": False, "natal-coords": True,
    }


def test_a_found_moment_does_not_look_like_a_raw_hyperlink():
    """It is part of the table, not the browser's idea of a link."""
    from app.views import page

    styles = page("x", "", tab="search")
    assert "td a {" in styles
    assert "text-decoration: none" in styles


def test_the_profected_house_is_written_as_an_ordinal():
    """It read "1th house" for a year of age nought."""
    import re
    from app.views import profection_block
    from app.service import build_chart

    seen = []
    for on in ("2026-07-15", "2027-07-15", "2028-07-15", "2029-07-15"):
        chart = build_chart(
            "2026-07-15", "12:00:00", "R", latitude=41.38, longitude=2.17,
            timezone_name="Europe/Madrid", profection_on=on,
        )
        found = re.search(r">(\d+\w\w) house", profection_block(chart))
        seen.append(found.group(1) if found else None)
    assert seen == ["1st", "2nd", "3rd", "4th"]


def test_the_toggle_marker_is_a_minus_and_not_a_stray_digit():
    """A CSS escape inside a Python string is an octal escape first."""
    from app.views import page

    styles = page("x", "", tab="chart")
    assert 'content: "−";' in styles
    assert "\x91" not in styles
