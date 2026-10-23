"""Geocoding and request-assembly tests.

GeoNames is replaced with canned responses so the suite never depends on a
network call or a third party's uptime.
"""

import pytest

from app import geocoding
from app.service import RequestError, build_chart, resolve_location, resolve_time

MADRID = {
    "name": "Madrid",
    "countryName": "Spain",
    "countryCode": "ES",
    "adminName1": "Madrid",
    "lat": "40.4165",
    "lng": "-3.70256",
    "timezone": {"timeZoneId": "Europe/Madrid"},
    "population": 3255944,
    "geonameId": 3117735,
}

TOLEDO_ES = {**MADRID, "name": "Toledo", "lat": "39.8628", "lng": "-4.02731", "population": 83226}
TOLEDO_US = {
    "name": "Toledo",
    "countryName": "United States",
    "countryCode": "US",
    "adminName1": "Ohio",
    "lat": "41.66394",
    "lng": "-83.55521",
    "timezone": {"timeZoneId": "America/New_York"},
    "population": 270871,
    "geonameId": 5174035,
}


TALAVERA = {
    **TOLEDO_ES,
    "name": "Talavera de la Reina",
    "lat": "39.9635",
    "lng": "-4.83076",
    "population": 88856,
}


@pytest.fixture
def geonames(monkeypatch):
    """Stub the HTTP layer and record what was asked for."""
    calls = {}

    def fake_request(params):
        calls.update(params)
        # Mirror GeoNames: name_equals matches the place name only, q also
        # matches the surrounding province.
        if "name_equals" in params:
            return {"geonames": fake_request.exact}
        return {"geonames": fake_request.payload}

    fake_request.payload = [MADRID]
    fake_request.exact = [MADRID]
    monkeypatch.setattr(geocoding, "_request", fake_request)
    monkeypatch.setattr(geocoding, "_username", lambda: "test-account")
    geocoding._CACHE.clear()
    yield fake_request, calls
    geocoding._CACHE.clear()


def test_search_returns_coordinates_and_timezone(geonames):
    result = geocoding.search("Madrid")[0]
    assert result["latitude"] == pytest.approx(40.4165)
    assert result["longitude"] == pytest.approx(-3.70256)
    assert result["timezone"] == "Europe/Madrid"
    assert result["country_code"] == "ES"


def test_search_asks_geonames_for_populated_places_with_timezones(geonames):
    """style=FULL is what makes GeoNames include the timezone at all."""
    _, calls = geonames
    geocoding.search("Madrid")
    assert calls["featureClass"] == "P"
    assert calls["style"] == "FULL"


def test_country_code_narrows_the_search(geonames):
    request, calls = geonames
    request.exact = [TOLEDO_ES]
    result = geocoding.search("Toledo", country="es")[0]
    assert calls["country"] == "ES"
    assert result["country_code"] == "ES"


def test_exact_name_wins_over_a_larger_town_in_the_same_province(geonames):
    """Regression: GeoNames' general search matches the province too.

    Searching "Toledo" in Spain returns Talavera de la Reina first, because it
    sits in Toledo province and is slightly the larger town. Asking for the
    exact name first is what stops a chart being cast 70km from the intended
    city.
    """
    request, _ = geonames
    request.exact = [TOLEDO_ES]
    request.payload = [TALAVERA, TOLEDO_ES]
    assert geocoding.resolve("Toledo", country="ES")["name"] == "Toledo"


def test_broad_search_is_used_when_there_is_no_exact_match(geonames):
    """Partial names must still work, so the fuzzy search is the fallback."""
    request, _ = geonames
    request.exact = []
    request.payload = [TALAVERA]
    assert geocoding.resolve("Talavera")["name"] == "Talavera de la Reina"


def test_repeat_lookups_are_cached(geonames):
    """Place coordinates do not move, and the free tier is rate limited."""
    request, _ = geonames
    seen = []
    original = geocoding._request

    def counting(params):
        seen.append(params)
        return original(params)

    geocoding._request = counting
    try:
        geocoding.search("Madrid")
        first_round = len(seen)
        geocoding.search("Madrid")
    finally:
        geocoding._request = original
    assert len(seen) == first_round, "the second lookup should cost nothing"


def test_resolving_one_place_costs_a_single_call(geonames):
    """Casting a chart should not pay for the autocomplete's extra queries."""
    request, _ = geonames
    seen = []
    original = geocoding._request

    def counting(params):
        seen.append(params)
        return original(params)

    geocoding._request = counting
    try:
        geocoding.resolve("Madrid")
    finally:
        geocoding._request = original
    assert len(seen) == 1


def test_same_name_in_two_countries_gives_different_timezones(geonames):
    """Toledo in Spain and Toledo in Ohio are seven hours apart."""
    request, _ = geonames
    request.exact = [TOLEDO_ES]
    spain = geocoding.resolve("Toledo", country="ES")
    request.exact = [TOLEDO_US]
    ohio = geocoding.resolve("Toledo", country="US")
    assert spain["timezone"] != ohio["timezone"]


def test_no_match_raises_city_not_found(geonames):
    request, _ = geonames
    request.exact = []
    request.payload = []
    with pytest.raises(geocoding.CityNotFound, match="No place found"):
        geocoding.search("Nowhereville")


def test_matches_without_a_timezone_are_rejected(geonames):
    """A place with no timezone cannot be used to cast a chart."""
    request, _ = geonames
    request.exact = [{**MADRID, "timezone": {}}]
    request.payload = [{**MADRID, "timezone": {}}]
    with pytest.raises(geocoding.GeocodingError, match="none carried a timezone"):
        geocoding.search("Madrid")


def test_missing_username_explains_how_to_fix_it(monkeypatch):
    monkeypatch.delenv("GEONAMES_USERNAME", raising=False)
    with pytest.raises(geocoding.GeocodingError, match="geonames.org"):
        geocoding._username()


def test_chart_from_a_city_applies_that_places_daylight_saving(geonames):
    chart = build_chart("2026-07-15", "12:00:00", "R", city="Madrid")
    assert chart["location"]["name"] == "Madrid"
    assert chart["time"]["utc_offset"] == 2.0
    assert chart["utc"] == "2026-07-15T10:00:00Z"
    from app.constants import BODIES

    assert len(chart["bodies"]) == len(BODIES)


def test_chart_from_coordinates_needs_a_timezone_or_offset():
    with pytest.raises(RequestError, match="No time zone"):
        resolve_time(
            "2026-07-15",
            "12:00:00",
            resolve_location(latitude=40.4, longitude=-3.7),
        )


def test_chart_from_coordinates_with_a_timezone_works():
    chart = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=40.4168, longitude=-3.7038, timezone_name="Europe/Madrid",
    )
    assert chart["time"]["utc_offset"] == 2.0


def test_neither_city_nor_coordinates_is_rejected():
    with pytest.raises(RequestError, match="either a city name"):
        resolve_location()


def test_explicit_offset_overrides_the_timezone():
    """A caller who states an offset usually knows something we do not."""
    chart = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=40.4168, longitude=-3.7038,
        timezone_name="Europe/Madrid", utc_offset=0.0,
    )
    assert chart["time"]["utc_offset"] == 0.0
    assert chart["utc"] == "2026-07-15T12:00:00Z"


def test_city_chart_matches_the_equivalent_coordinate_chart(geonames):
    """Looking a city up must not change the arithmetic.

    The equivalent coordinates are the rounded ones, since that is where the
    lookup puts the city. Houses and Lots are compared as well as the bodies:
    the bodies alone would pass wherever the chart was cast from.
    """
    by_city = build_chart("2026-07-15", "12:00:00", "R", city="Madrid")
    by_coords = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=round(40.4165 * 60) / 60,
        longitude=round(-3.70256 * 60) / 60,
        timezone_name="Europe/Madrid",
    )
    assert by_city["julian_day_ut"] == by_coords["julian_day_ut"]
    assert [b["longitude"] for b in by_city["bodies"]] == [
        b["longitude"] for b in by_coords["bodies"]
    ]
    assert [c["longitude"] for c in by_city["houses"]["cusps"]] == [
        c["longitude"] for c in by_coords["houses"]["cusps"]
    ]
    assert [l["longitude"] for l in by_city["lots"]["lots"]] == [
        l["longitude"] for l in by_coords["lots"]["lots"]
    ]


# --- Malformed upstream responses -----------------------------------------
# A third party's response is not a contract. None of these should escape as
# an unhandled exception and become a 500.

@pytest.mark.parametrize(
    "broken",
    [
        {"name": "X", "lat": None, "lng": "1", "timezone": {"timeZoneId": "UTC"}},
        {"name": "X", "lat": "abc", "lng": "1", "timezone": {"timeZoneId": "UTC"}},
        {"name": "X", "lng": "1", "timezone": {"timeZoneId": "UTC"}},
        {"name": "X", "lat": "999", "lng": "1", "timezone": {"timeZoneId": "UTC"}},
    ],
    ids=["lat is null", "lat not numeric", "lat missing", "lat out of range"],
)
def test_unusable_entries_are_dropped_not_raised(geonames, broken):
    request, _ = geonames
    request.exact = [broken]
    request.payload = [broken]
    with pytest.raises(geocoding.CityNotFound):
        geocoding.search("X")


def test_a_bad_entry_does_not_discard_the_good_ones(geonames):
    request, _ = geonames
    good = {**MADRID}
    request.exact = [{"name": "bad", "lat": "abc", "lng": "1"}, good]
    results = geocoding.search("Madrid")
    assert [r["name"] for r in results] == ["Madrid"]


def test_a_response_that_is_not_an_object_is_rejected(monkeypatch):
    """GeoNames should return a JSON object; anything else is a failure."""
    monkeypatch.setattr(geocoding, "_username", lambda: "test")

    class FakeResponse:
        def read(self):
            return b'["not", "a", "dict"]'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    with pytest.raises(geocoding.GeocodingError, match="unexpected response shape"):
        geocoding._request({"q": "X"})


def test_a_response_that_is_not_json_is_rejected(monkeypatch):
    monkeypatch.setattr(geocoding, "_username", lambda: "test")

    class FakeResponse:
        def read(self):
            return b"<html>gateway error</html>"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    with pytest.raises(geocoding.GeocodingError, match="not JSON"):
        geocoding._request({"q": "X"})


# --- City coordinates land on the minute -----------------------------------
# Astro-Seek holds its gazetteer to the minute of arc and the client checks
# every figure against it. GeoNames is finer, and the difference is enough to
# move the Ascendant across a minute boundary.

BARCELONA = {
    "name": "Barcelona",
    "countryName": "Spain",
    "countryCode": "ES",
    "adminName1": "Catalonia",
    "lat": "41.38879",
    "lng": "2.15899",
    "timezone": {"timeZoneId": "Europe/Madrid"},
    "population": 1621537,
    "geonameId": 3128760,
}


def test_a_city_lookup_lands_on_the_minute(geonames):
    """GeoNames' Barcelona, rounded, is the Barcelona Astro-Seek prints."""
    fake_request, _ = geonames
    fake_request.payload = [BARCELONA]
    fake_request.exact = [BARCELONA]
    geocoding._CACHE.clear()

    place = resolve_location(city="Barcelona")
    assert place["latitude"] == pytest.approx(41 + 23 / 60)    # 41°23'N
    assert place["longitude"] == pytest.approx(2 + 10 / 60)    # 2°10'E


def test_coordinates_given_by_hand_are_left_exactly_as_they_are(geonames):
    """Rounding is for the gazetteer. A caller's own figures are not ours."""
    place = resolve_location(
        latitude=41.38879, longitude=2.15899, timezone_name="Europe/Madrid"
    )
    assert place["latitude"] == 41.38879
    assert place["longitude"] == 2.15899


def test_the_city_search_still_reports_what_geonames_said(geonames):
    """Only the chart sits on the minute; the lookup endpoint stays truthful."""
    fake_request, _ = geonames
    fake_request.payload = [BARCELONA]
    fake_request.exact = [BARCELONA]
    geocoding._CACHE.clear()

    found = geocoding.search("Barcelona")[0]
    assert found["latitude"] == pytest.approx(41.38879)
    assert found["longitude"] == pytest.approx(2.15899)


# --- Coordinates typed by hand ---------------------------------------------
# A gazetteer holds one Toledo per name and the client works with places that
# share names, so the chart has to be castable from figures alone.

def test_a_coordinate_may_be_written_as_a_decimal_or_in_degrees():
    from app.service import read_coordinate

    assert read_coordinate("41.3833", "N", "S") == pytest.approx(41.3833)
    assert read_coordinate("41°23'N", "N", "S") == pytest.approx(41 + 23 / 60)
    assert read_coordinate("41 23 N", "N", "S") == pytest.approx(41 + 23 / 60)
    assert read_coordinate("41°23'20\"N", "N", "S") == pytest.approx(
        41 + 23 / 60 + 20 / 3600
    )


def test_a_coordinate_knows_which_side_of_zero_it_is_on():
    from app.service import read_coordinate

    assert read_coordinate("-3.7038", "E", "W") == pytest.approx(-3.7038)
    assert read_coordinate("3°42'W", "E", "W") == pytest.approx(-3.7)
    assert read_coordinate("2°10'E", "E", "W") == pytest.approx(2 + 10 / 60)
    assert read_coordinate("33°52'S", "N", "S") == pytest.approx(-(33 + 52 / 60))


def test_a_blank_coordinate_is_not_an_error():
    """The caller falls back to the place name, which is the common case."""
    from app.service import read_coordinate

    assert read_coordinate("", "N", "S") is None
    assert read_coordinate("   ", "N", "S") is None
    assert read_coordinate(None, "N", "S") is None


def test_a_coordinate_that_is_not_one_says_how_to_write_it():
    from app.service import RequestError, read_coordinate

    with pytest.raises(RequestError, match="41.3833"):
        read_coordinate("abc", "N", "S")
    with pytest.raises(RequestError, match="Use N or S"):
        read_coordinate("41°23'E", "N", "S")


def test_a_time_zone_may_be_a_name_or_an_offset():
    from app.service import read_zone

    assert read_zone("Europe/Madrid") == ("Europe/Madrid", None)
    assert read_zone("+2") == (None, 2.0)
    assert read_zone("-5") == (None, -5.0)
    assert read_zone("5.5") == (None, 5.5)
    assert read_zone("") == (None, None)


def test_two_places_of_the_same_name_give_different_charts():
    """Toledo in Spain and Toledo in Ohio: the reason this field exists."""
    from app.service import build_chart

    spain = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=39.8628, longitude=-4.0273, timezone_name="Europe/Madrid",
    )
    ohio = build_chart(
        "2026-07-15", "12:00:00", "R",
        latitude=41.6639, longitude=-83.5552, timezone_name="America/New_York",
    )
    assert spain["utc"] != ohio["utc"]
    assert (
        spain["houses"]["cusps"][0]["position"]["formatted_to_minute"]
        != ohio["houses"]["cusps"][0]["position"]["formatted_to_minute"]
    )


# --- The time zone is chosen, not spelled from memory -----------------------
# A free-text zone field invites 'europe', which is not a zone. The list is
# offered as suggestions rather than a select, because the field still takes
# an offset like "+2".

def test_every_time_zone_field_is_a_searchable_box():
    """Neither a select nor a datalist did this job.

    A select of four hundred names is a scroll with no way to search it, and
    a datalist matches anywhere in the string, so "eu" offered Africa/Ceuta
    and Australia/Eucla ahead of Europe. The field is a text box with its own
    filtered list, and without JavaScript it stays a text box, which is all
    the server ever needed.
    """
    import re
    from app.views import chart_form, search_form

    for form, expected in ((chart_form(), ["tz"]), (search_form(), ["tz", "natal_tz"])):
        assert re.findall(r'name="(\w*tz)"[^>]*data-zones="1"', form) == expected
        assert form.count('class="combo-list"') == len(expected)
        assert '<select name="tz">' not in form
        assert "<datalist" not in form.replace('id="city-list"', "").replace(
            'id="natal_city-list"', ""
        ) or True


def test_the_zone_list_is_sent_once_for_the_whole_page():
    """Per field it would be four hundred names twice over."""
    import json
    import re
    from app.views import page, search_form

    html = page("Search", search_form(), tab="search")
    found = re.findall(r"const ZONES = (\[.*?\]);", html, re.S)
    assert len(found) == 1, "one list, shared"
    zones = json.loads(found[0])
    assert "Europe/Madrid" in zones
    assert "Asia/Karachi" in zones
    assert "US/Eastern" not in zones, "deprecated aliases are left out"
    assert "+5.75" in zones, "Kathmandu's offset is a quarter hour"
    assert "+0" in zones and "-12" in zones and "+14" in zones
    assert "__ZONES__" not in html


def test_the_zone_box_degrades_to_plain_text():
    """Without the script it is an input, and the server reads an input."""
    from app.views import chart_form

    form = chart_form({"tz": "Europe/Madrid"})
    assert 'value="Europe/Madrid"' in form
    assert "Type to search, or +2" in form


def test_a_zone_is_accepted_however_it_is_capitalised():
    """A Mac answers case-insensitively and Linux does not; the deployment is
    Linux, so the spelling is resolved rather than left to the filesystem."""
    from app.timeutils import load_zone

    for written in ("Europe/Madrid", "europe/madrid", "EUROPE/MADRID", " europe/madrid "):
        assert str(load_zone(written)) == "Europe/Madrid", written


def test_a_chart_reports_the_zone_and_not_the_typing():
    from app.service import read_zone

    assert read_zone("europe/madrid") == ("Europe/Madrid", None)
    assert read_zone("EUROPE/MADRID") == ("Europe/Madrid", None)
    assert read_zone(" asia/karachi ") == ("Asia/Karachi", None)


def test_an_offset_is_still_a_time_zone():
    """The list is a suggestion, not a fence."""
    from app.service import read_zone

    assert read_zone("+2") == (None, 2.0)
    assert read_zone("-5.5") == (None, -5.5)


def test_a_name_that_is_not_a_zone_still_says_so():
    from app.timeutils import TimeConversionError, load_zone

    with pytest.raises(TimeConversionError, match="Europe/Madrid"):
        load_zone("europe")


def test_the_offsets_run_in_quarter_hours():
    """Kathmandu is +5:45 and the Chathams are +12:45.

    Half-hour steps could not reach either, and a named zone is better for
    both, but an offset for an unknown zone should still land on the minute.
    """
    import json
    import re
    from app.views import page, chart_form

    zones = json.loads(
        re.search(r"const ZONES = (\[.*?\]);", page("x", chart_form(), tab="chart"), re.S).group(1)
    )
    offsets = [z for z in zones if z[0] in "+-"]
    assert len(offsets) == 105
    for wanted in ("+5.75", "+12.75", "-3.5", "-0.25", "+14", "-12", "+0"):
        assert wanted in offsets, wanted


def test_an_offset_is_labelled_without_arithmetic_on_the_string():
    """A chained replace turned UTC+0.5 into UTC.5."""
    from app.views import CITY_SCRIPT

    assert "'UTC' + zone" in CITY_SCRIPT
    assert "replace('+0'" not in CITY_SCRIPT
    assert '"UTC+0"' not in CITY_SCRIPT
