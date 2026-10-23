import pytest
from fastapi.testclient import TestClient

from app import geocoding, ratelimit
from app.main import app


@pytest.fixture(autouse=True)
def clean_limiters():
    for limiter in (
        ratelimit.cities_limiter,
        ratelimit.chart_limiter,
        ratelimit.geonames_budget,
    ):
        limiter.reset()
    yield
    for limiter in (
        ratelimit.cities_limiter,
        ratelimit.chart_limiter,
        ratelimit.geonames_budget,
    ):
        limiter.reset()


def test_window_allows_up_to_the_limit_then_refuses():
    window = ratelimit.SlidingWindow(3, 60)
    for _ in range(3):
        window.check("client", now=100.0)
    with pytest.raises(ratelimit.RateLimitExceeded):
        window.check("client", now=100.0)


def test_window_frees_up_once_events_age_out():
    window = ratelimit.SlidingWindow(2, 60)
    window.check("client", now=0.0)
    window.check("client", now=1.0)
    with pytest.raises(ratelimit.RateLimitExceeded):
        window.check("client", now=2.0)
    # The first event leaves the window at t=60.
    window.check("client", now=61.0)


def test_clients_are_counted_separately():
    window = ratelimit.SlidingWindow(1, 60)
    window.check("first", now=0.0)
    window.check("second", now=0.0)  # must not be blocked by the first


def test_retry_after_is_a_sensible_wait():
    window = ratelimit.SlidingWindow(1, 60)
    window.check("client", now=0.0)
    with pytest.raises(ratelimit.RateLimitExceeded) as caught:
        window.check("client", now=10.0)
    assert 1 <= caught.value.retry_after <= 60


def test_a_zero_limit_disables_the_check():
    window = ratelimit.SlidingWindow(0, 60)
    for _ in range(100):
        window.check("client", now=0.0)


def test_idle_clients_are_forgotten_so_memory_does_not_grow():
    window = ratelimit.SlidingWindow(5, 60)
    for i in range(50):
        window.check(f"client-{i}", now=0.0)
    assert len(window._events) == 50
    window.check("recent", now=10_000.0)
    assert len(window._events) == 1, "stale clients should have been evicted"


def test_forwarded_header_identifies_the_client_behind_a_proxy():
    class FakeRequest:
        headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
        client = None

    assert ratelimit.client_key(FakeRequest()) == "203.0.113.7"


def test_socket_address_is_used_when_there_is_no_proxy():
    class FakeClient:
        host = "198.51.100.4"

    class FakeRequest:
        headers = {}
        client = FakeClient()

    assert ratelimit.client_key(FakeRequest()) == "198.51.100.4"


def test_chart_endpoint_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(ratelimit, "chart_limiter", ratelimit.SlidingWindow(2, 60))
    import app.main as main

    monkeypatch.setattr(main.ratelimit, "chart_limiter", ratelimit.chart_limiter)

    body = {
        "date": "2026-07-15",
        "time": "12:00:00",
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timezone": "Europe/Madrid",
    }
    with TestClient(app) as client:
        assert client.post("/chart", json=body).status_code == 200
        assert client.post("/chart", json=body).status_code == 200
        blocked = client.post("/chart", json=body)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_health_is_never_rate_limited(monkeypatch):
    """Render polls this constantly; limiting it would take the service down."""
    monkeypatch.setattr(ratelimit, "chart_limiter", ratelimit.SlidingWindow(1, 60))
    with TestClient(app) as client:
        for _ in range(30):
            assert client.get("/health").status_code == 200


def test_geonames_budget_is_spent_by_upstream_calls_not_cache_hits(monkeypatch):
    """The account allowance is a shared resource, so only real calls count."""
    monkeypatch.setattr(geocoding, "_username", lambda: "test-account")
    calls = []

    def fake(params):
        calls.append(params)
        ratelimit.geonames_budget.check("global")
        return {"geonames": [
            {
                "name": "Madrid", "countryName": "Spain", "countryCode": "ES",
                "adminName1": "Madrid", "lat": "40.4", "lng": "-3.7",
                "timezone": {"timeZoneId": "Europe/Madrid"},
                "population": 1, "geonameId": 1,
            }
        ]}

    monkeypatch.setattr(geocoding, "_request", fake)
    geocoding._CACHE.clear()
    try:
        geocoding.search("Madrid")
        spent = len(calls)
        geocoding.search("Madrid")  # served from cache
        assert len(calls) == spent, "a cache hit must not draw on the allowance"
    finally:
        geocoding._CACHE.clear()
