"""What the product does when it is given something it did not expect.

A chart is read by someone who did not write it, so every refusal has to be a
sentence they can act on. Nothing here should reach a traceback, name a field
that only exists in the API, or mention a path on our disk.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app import ratelimit
from app.main import app


@pytest.fixture(autouse=True)
def clean_limiters():
    for limiter in (ratelimit.cities_limiter, ratelimit.chart_limiter, ratelimit.geonames_budget):
        limiter.reset()
    yield


@pytest.fixture
def client():
    # Exceptions become responses, as they do in front of a real reader.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def shown(response):
    """The error a reader actually sees on the page."""
    found = re.search(r'class="note err">(.*?)</div>', response.text, re.S)
    return unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip() if found else ""


# Things that belong to the machine, not to the person reading the page.
LEAKS = (
    "Traceback", "strptime", "does not match format", "int() with base",
    "NoneType", "KeyError", "object has no attribute",
    "swisseph", ".se1", "/Applications", "/var/", "/home/",
    "natal_city", "natal_latitude", "utc_offset", "step_seconds",
)


# --- A date the ephemeris cannot reach -------------------------------------
# The bundled files cover every body between 1800 and 2400; the planets alone
# reach further. Past the edge swisseph names the file it wanted and the
# directory it searched, which is our disk layout in a message to a stranger.

OUT_OF_REACH = {
    "date": "5000-07-15", "time": "12:00:00", "house_system": "R",
    "latitude": "41", "longitude": "2", "tz": "+0",
}


def test_a_date_beyond_the_ephemeris_does_not_fall_over(client):
    """It used to: the summary cards read a position that was never there."""
    response = client.get("/view/chart", params=OUT_OF_REACH)
    assert response.status_code == 200


def test_a_date_beyond_the_ephemeris_says_which_bodies_are_missing(client):
    """A wheel with planets quietly absent is worse than no wheel at all."""
    message = shown(client.get("/view/chart", params=OUT_OF_REACH))
    assert "Jupiter" in message
    assert "not on this chart" in message
    assert "1800 and 2400" in message


def test_no_body_error_names_a_file_or_a_folder(client):
    """What a reader needs is the date, not our filing system."""
    response = client.post("/chart", json={
        "date": "5000-07-15", "time": "12:00:00",
        "latitude": 41.0, "longitude": 2.0, "utc_offset": 0,
    })
    assert response.status_code == 200
    for body in response.json()["bodies"]:
        if "error" in body:
            assert ".se1" not in body["error"]
            assert "/" not in body["error"]
            assert "swisseph" not in body["error"]


def test_a_chart_inside_the_range_says_nothing_about_missing_bodies(client):
    response = client.get("/view/chart", params={
        "date": "2026-07-15", "time": "12:00:00",
        "house_system": "R", "city": "Barcelona",
    })
    assert "not on this chart" not in response.text


# --- Hand-edited addresses -------------------------------------------------

def test_a_precision_that_is_not_a_number_is_answered_in_words(client):
    """int() answers this one with literals and bases."""
    message = shown(client.get("/view/search", params={
        "formula": "Sun.120.Moon", "start": "2027-01-01",
        "end": "2027-03-31", "step_seconds": "abc",
    }))
    assert "is not a number of seconds" in message
    assert "base 10" not in message


def test_the_transit_page_without_a_moment_offers_the_search(client):
    """It has no form of its own, so it shows the one that leads here."""
    response = client.get("/view/transits")
    assert response.status_code == 400
    assert "<form" in response.text
    assert "found by a search" in shown(response)


def test_a_transit_chart_beyond_the_ephemeris_says_so(client):
    """A ring with two planets in it looks deliberate."""
    message = shown(client.get("/view/transits", params={
        "moment": "5000-02-19T19:45:00Z", "natal_date": "1985-06-15",
        "natal_time": "14:30", "natal_latitude": "41.3833",
        "natal_longitude": "2.1667", "natal_tz": "Europe/Madrid",
    }))
    assert "not on this chart" in message


# --- Nothing the machine says reaches the page -----------------------------

ROUGH_INPUT = [
    ("/view/chart", {"date": "x", "time": "12:00:00", "city": "Barcelona"}),
    ("/view/chart", {"date": "2026-07-15", "time": "x", "city": "Barcelona"}),
    ("/view/chart", {"date": "2026-07-15", "time": "12:00:00"}),
    ("/view/chart", {"date": "2026-07-15", "time": "12:00:00", "city": "Zzzzz"}),
    ("/view/chart", {"date": "2026-07-15", "time": "12:00:00",
                     "latitude": "abc", "longitude": "2", "tz": "+2"}),
    ("/view/chart", {"date": "2026-07-15", "time": "12:00:00",
                     "latitude": "41", "longitude": "2"}),
    ("/view/chart", {"date": "2026-07-15", "time": "12:00:00",
                     "city": "Barcelona", "house_system": "ZZ"}),
    ("/view/chart", OUT_OF_REACH),
    ("/view/search", {"formula": "!!!", "start": "2027-01-01", "end": "2027-03-31"}),
    ("/view/search", {"formula": "XX.0.SO", "start": "2027-01-01", "end": "2027-03-31"}),
    ("/view/search", {"formula": "MA'.90.SA", "start": "2027-01-01", "end": "2027-03-31"}),
    ("/view/search", {"formula": "Sun.120.Moon", "start": "2027-12-31", "end": "2027-01-01"}),
    ("/view/search", {"formula": "Sun.120.Moon", "start": "2027-01-01",
                      "end": "2027-03-31", "step_seconds": "abc"}),
    ("/view/search", {"formula": "Sun.120.Moon", "start": "2027-01-01",
                      "end": "2027-03-31", "orb_system": "zz"}),
    ("/view/search", {"formula": "Sun.120.Moon", "start": "1930-01-01",
                      "end": "2030-01-01", "step_seconds": "300"}),
    ("/view/transits", {}),
    ("/view/transits", {"moment": "garbage", "natal_date": "1985-06-15",
                        "natal_time": "14:30", "natal_city": "Barcelona"}),
]


@pytest.mark.parametrize("path,params", ROUGH_INPUT)
def test_the_page_never_shows_the_machine_talking(client, path, params):
    response = client.get(path, params=params)
    assert response.status_code != 500
    message = shown(response)
    for leak in LEAKS:
        assert leak not in message, f"{path} leaked {leak!r}: {message}"


# --- Anything typed in comes back out as text ------------------------------

PAYLOADS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "<svg onload=alert(1)>",
    "</textarea><script>x</script>",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_nothing_typed_into_a_form_is_rendered_as_markup(client, payload):
    places = [
        ("/view/chart", {"date": "2026-07-15", "time": "12:00:00", "city": payload}),
        ("/view/chart", {"date": "2026-07-15", "time": "12:00:00",
                         "latitude": payload, "longitude": "2", "tz": "+2"}),
        ("/view/search", {"formula": payload, "start": "2027-01-01", "end": "2027-03-31"}),
        ("/view/search", {"formula": "SO.0.H1", "start": "2027-01-01",
                          "end": "2027-03-31", "city": payload}),
        ("/view/transits", {"moment": payload, "natal_date": "1985-06-15",
                            "natal_time": "14:30", "natal_city": "Barcelona"}),
    ]
    for path, params in places:
        response = client.get(path, params=params)
        assert payload not in response.text, f"{path} echoed {payload!r} unescaped"


# --- The two pages say where they are in the same words --------------------

def place_chips(response, how_many=2):
    import re
    from html import unescape
    return [
        unescape(re.sub(r"<[^>]+>", "", chip)).strip()
        for chip in re.findall(r'class="fact">(.*?)</span>', response.text, re.S)
    ][:how_many]


def test_both_pages_name_the_place_the_same_way(client):
    """A transit is cast from the birth place, so it is shown the same way."""
    chart = client.get("/view/chart", params={
        "date": "2026-07-15", "time": "12:00", "house_system": "R",
        "city": "Barcelona", "city_country": "ES",
    })
    transits = client.get("/view/transits", params={
        "moment": "2027-08-10T06:30:00Z", "natal_date": "2020-01-18",
        "natal_time": "19:48", "natal_city": "Barcelona",
    })
    assert place_chips(chart) == place_chips(transits) == [
        "Barcelona", "41°23′N, 2°10′E",
    ]


def test_neither_page_prints_the_coordinates_twice(client):
    """Cast from figures, the figures are the name; a chip would repeat it."""
    for path, params in [
        ("/view/chart", {"date": "2026-07-15", "time": "12:00",
                         "house_system": "R", "latitude": "41°23'N",
                         "longitude": "2°10'E", "tz": "Europe/Madrid"}),
        ("/view/transits", {"moment": "2027-08-10T06:30:00Z",
                            "natal_date": "2020-01-18", "natal_time": "19:48",
                            "natal_latitude": "41°23'N",
                            "natal_longitude": "2°10'E",
                            "natal_tz": "Europe/Madrid"}),
    ]:
        chips = place_chips(client.get(path, params=params), 4)
        written = "41°23′N, 2°10′E"
        assert chips[0] == written
        assert chips.count(written) == 1, f"{path} repeated the coordinates"
