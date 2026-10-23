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
    with TestClient(app) as test_client:
        yield test_client


def search(client, **body):
    body.setdefault("start", "2027-01-01")
    body.setdefault("end", "2027-03-31")
    return client.post("/search", json=body)


def test_a_simple_search_returns_intervals(client):
    response = search(client, formula="Sun.120.Moon")
    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] == 6
    assert payload["reading"] == "Sun trine Moon"
    assert all({"begin", "end", "duration_hours"} <= set(i) for i in payload["intervals"])


def test_the_orb_system_is_reported_back(client):
    assert search(client, formula="Sun.120.Moon").json()["orb_system"] == "moiety"
    assert (
        search(client, formula="Sun.120.Moon", orb_system="fixed").json()["orb_system"]
        == "fixed"
    )


def test_applying_narrows_the_window(client):
    """Applying is the approach, so roughly half of the whole passage."""
    whole = search(client, formula="Sun.120.Moon").json()
    approaching = search(client, formula="Sun.120A.Moon").json()
    assert approaching["found"] == whole["found"]
    assert sum(i["duration_hours"] for i in approaching["intervals"]) < sum(
        i["duration_hours"] for i in whole["intervals"]
    )


def test_a_syntax_error_points_at_the_problem(client):
    response = search(client, formula="Sun.wobble.Moon")
    assert response.status_code == 400
    assert "^" in response.json()["detail"]


def test_an_unknown_body_is_refused(client):
    response = search(client, formula="Xyz.120.Sun")
    assert response.status_code == 400
    assert "Unknown body" in response.json()["detail"]


def test_houses_without_a_place_explain_what_is_missing(client):
    response = search(client, formula="Mar.H7")
    assert response.status_code == 400
    assert "location" in response.json()["detail"]


def test_a_range_that_is_too_large_suggests_a_step(client):
    response = search(client, formula="Sun.Ari", end="2027-12-31", step_seconds=60)
    assert response.status_code == 400
    assert "Use a step of at least" in response.json()["detail"]


def test_a_step_below_the_floor_is_rejected_before_it_runs(client):
    assert search(client, formula="Sun.Ari", step_seconds=1).status_code == 422


def test_an_invented_orb_system_is_rejected(client):
    response = search(client, formula="Sun.120.Moon", orb_system="invented")
    assert response.status_code == 422


def test_a_coarse_step_warns_about_missed_stations(client):
    payload = search(client, formula="Mer.S", end="2027-12-31", step_seconds=86400).json()
    assert payload["warnings"]
    assert "stationary" in payload["warnings"][0].lower()


def test_a_fine_enough_step_does_not_warn(client):
    payload = search(client, formula="Mer.S", end="2027-12-31", step_seconds=900).json()
    assert payload["warnings"] == []
    assert payload["found"] == 6


def test_a_transit_without_a_natal_chart_asks_for_one(client):
    response = search(client, formula="NE'.180.PL")
    assert response.status_code == 400
    assert "birth date, time and place" in response.json()["detail"]


def test_searches_are_rate_limited(monkeypatch, client):
    monkeypatch.setattr(ratelimit, "chart_limiter", ratelimit.SlidingWindow(2, 60))
    import app.main as main

    monkeypatch.setattr(main.ratelimit, "chart_limiter", ratelimit.chart_limiter)
    assert search(client, formula="Sun.Ari").status_code == 200
    assert search(client, formula="Sun.Ari").status_code == 200
    assert search(client, formula="Sun.Ari").status_code == 429


# --- birth details that the formula cannot use -----------------------------
# A birth place costs a GeoNames lookup out of a limited daily allowance, and a
# formula without an apostrophe would never read the chart it paid for.

def test_birth_details_are_not_resolved_for_a_formula_without_an_apostrophe(
    client, monkeypatch
):
    from app import geocoding

    def refuse(*args, **kwargs):
        raise AssertionError("the natal place should not have been looked up")

    monkeypatch.setattr(geocoding, "resolve", refuse)
    response = client.post(
        "/search",
        json={
            "formula": "MoonVoid",
            "start": "2027-01-01",
            "end": "2027-01-31",
            "latitude": 41.3888,
            "longitude": 2.159,
            "timezone": "Europe/Madrid",
            "natal_date": "1997-05-18",
            "natal_time": "20:38:00",
            "natal_city": "Khanewal",
        },
    )
    assert response.status_code == 200
    assert response.json()["natal_chart"] is None


def test_and_the_answer_says_the_birth_details_went_unused(client):
    """Dropping them silently would leave the astrologer none the wiser."""
    response = client.post(
        "/search",
        json={
            "formula": "MoonVoid",
            "start": "2027-01-01",
            "end": "2027-01-31",
            "latitude": 41.3888,
            "longitude": 2.159,
            "timezone": "Europe/Madrid",
            "natal_date": "1997-05-18",
            "natal_time": "20:38:00",
            "natal_latitude": 30.3017,
            "natal_longitude": 71.9321,
            "natal_timezone": "Asia/Karachi",
        },
    )
    warnings = response.json()["warnings"]
    assert any("apostrophe" in w for w in warnings), warnings


def test_a_formula_with_an_apostrophe_still_gets_its_birth_chart(client):
    response = client.post(
        "/search",
        json={
            "formula": "MA'.90.SA",
            "start": "2027-01-01",
            "end": "2027-12-31",
            "step_seconds": 3600,
            "latitude": 41.3888,
            "longitude": 2.159,
            "timezone": "Europe/Madrid",
            "natal_date": "1997-05-18",
            "natal_time": "20:38:00",
            "natal_latitude": 30.3017,
            "natal_longitude": 71.9321,
            "natal_timezone": "Asia/Karachi",
        },
    )
    assert response.status_code == 200
    assert response.json()["natal_chart"] == "1997-05-18T15:38:00Z"
    assert not any("apostrophe" in w for w in response.json()["warnings"])


# --- One city, one position ------------------------------------------------
# The chart and the scanner both have to cast from the same spot. They reach
# the gazetteer by different routes, and if only one of them rounds to the
# minute the two drift apart by about twenty arcseconds, which is enough to
# put a house cusp in a different minute on the page than in a search.

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


@pytest.fixture
def barcelona(monkeypatch):
    from app import geocoding

    monkeypatch.setattr(geocoding, "_request", lambda params: {"geonames": [BARCELONA]})
    monkeypatch.setattr(geocoding, "_username", lambda: "test-account")
    geocoding._CACHE.clear()
    yield
    geocoding._CACHE.clear()


def test_the_scanner_casts_from_the_rounded_city(client, barcelona, monkeypatch):
    """A city given to /search arrives at the scan on the minute."""
    from app import main

    seen = {}
    real_scan = main.scan

    def spy(**kwargs):
        seen.update(kwargs)
        return real_scan(**kwargs)

    monkeypatch.setattr(main, "scan", spy)
    response = search(client, formula="Sun.0.H1", city="Barcelona")

    assert response.status_code == 200
    assert seen["latitude"] == pytest.approx(41 + 23 / 60)
    assert seen["longitude"] == pytest.approx(2 + 10 / 60)


def test_the_scanner_and_the_chart_agree_on_where_a_city_is(client, barcelona, monkeypatch):
    """The two routes to the gazetteer must not disagree."""
    from app import main
    from app.service import resolve_location

    seen = {}
    real_scan = main.scan
    monkeypatch.setattr(main, "scan", lambda **kw: (seen.update(kw), real_scan(**kw))[1])
    search(client, formula="Sun.0.H1", city="Barcelona")

    cast_from = resolve_location(city="Barcelona")
    assert seen["latitude"] == cast_from["latitude"]
    assert seen["longitude"] == cast_from["longitude"]


# --- From a found moment to its chart --------------------------------------

def transits(client, **params):
    params.setdefault("moment", "2027-02-19T19:45:00Z")
    params.setdefault("natal_date", "1985-06-15")
    params.setdefault("natal_time", "14:30")
    params.setdefault("natal_latitude", "41°23'N")
    params.setdefault("natal_longitude", "2°10'E")
    params.setdefault("natal_tz", "Europe/Madrid")
    return client.get("/view/transits", params=params)


def test_a_moment_can_be_drawn_around_the_birth_chart(client):
    response = transits(client)
    assert response.status_code == 200
    assert "gl transit" in response.text
    assert "gl planet" in response.text


def test_a_birth_time_without_seconds_is_accepted(client):
    """The form's time input never sends them."""
    assert transits(client, natal_time="14:30").status_code == 200
    assert transits(client, natal_time="14:30:00").status_code == 200


def test_a_bad_birth_date_is_reported_on_the_page(client):
    response = transits(client, natal_date="nope")
    assert response.status_code == 400
    assert "note err" in response.text


def test_the_results_link_each_moment_to_its_chart(client, barcelona):
    """A formula with an apostrophe found the moment against a chart.

    The page, not the JSON: a link is something a reader clicks.
    """
    response = client.get("/view/search", params={
        "formula": "MA'.90.SA", "start": "2027-01-01", "end": "2027-12-31",
        "natal_date": "1985-06-15", "natal_time": "14:30",
        "natal_city": "Barcelona",
    })
    assert response.status_code == 200
    assert "/view/transits?moment=" in response.text


def test_results_without_a_birth_chart_link_nowhere(client):
    """There is nothing to draw a transit against, so the dates stay plain."""
    response = client.get("/view/search", params={
        "formula": "Sun.120.Moon", "start": "2027-01-01", "end": "2027-03-31",
    })
    assert response.status_code == 200
    assert "/view/transits" not in response.text
