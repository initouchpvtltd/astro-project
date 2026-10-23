"""Essential dignities, the Hermetic Lots and annual profections.

The lots are checked against Astro-Seek's own output for a chart the client
pointed at, because a lot put in the wrong half of the chart is the easiest
mistake to make here and the hardest to notice: every figure still looks
plausible.
"""

from datetime import date

import pytest

from fastapi.testclient import TestClient

from app import dignities, lots, profections
from app.main import app
from app.service import build_chart


@pytest.fixture
def api_client():
    with TestClient(app) as client:
        yield client


# --- essential dignities ---------------------------------------------------

def test_a_planet_in_its_own_sign_holds_domicile():
    assert "domicile" in dignities.dignities_for("MA", 5.0, True)["dignities"]


def test_exaltation_belongs_to_the_whole_sign_not_only_its_degree():
    """Lilly's table gives the Sun exaltation throughout Aries, strongest at 19."""
    for degree in (0.5, 19.0, 29.9):
        assert "exaltation" in dignities.dignities_for("SO", degree, True)["dignities"]


def test_fall_is_the_sign_opposite_the_exaltation():
    assert "fall" in dignities.dignities_for("SA", 5.0, True)["dignities"]   # Aries
    assert "exaltation" in dignities.dignities_for("SA", 186.0, True)["dignities"]  # Libra


def test_detriment_is_the_sign_opposite_the_domicile():
    assert "detriment" in dignities.dignities_for("VE", 2.0, True)["dignities"]  # Aries


def test_triplicity_changes_with_the_sect():
    """Fire goes to the Sun by day and Jupiter by night."""
    assert "triplicity" in dignities.dignities_for("SO", 5.0, True)["dignities"]
    assert "triplicity" not in dignities.dignities_for("SO", 5.0, False)["dignities"]
    assert "triplicity" in dignities.dignities_for("JU", 5.0, False)["dignities"]


def test_lilly_gives_mars_the_water_triplicity_day_and_night():
    """Where Lilly's table parts company with Dorotheus, and the spec names Lilly."""
    for is_day in (True, False):
        assert dignities.TRIPLICITIES["water"][0 if is_day else 1] == "MA"


def test_the_faces_run_in_chaldean_order_from_mars_at_zero_aries():
    assert [dignities._face_ruler(0, d) for d in (0, 10, 20)] == ["MA", "SO", "VE"]
    assert [dignities._face_ruler(1, d) for d in (0, 10, 20)] == ["ME", "MO", "SA"]
    assert [dignities._face_ruler(11, d) for d in (0, 10, 20)] == ["SA", "JU", "MA"]


def test_the_thirty_six_faces_never_repeat_a_planet_in_a_row():
    run = [dignities._face_ruler(s, d) for s in range(12) for d in (0, 10, 20)]
    assert len(run) == 36
    assert all(a != b for a, b in zip(run, run[1:]))


def test_the_two_term_systems_disagree_which_is_why_both_are_offered():
    """At 13 Aries the Egyptian terms give Mercury and Ptolemy gives Venus."""
    egyptian = dignities.dignities_for("ME", 13.0, True, "egyptian")["rulers"]["term"]
    ptolemaic = dignities.dignities_for("ME", 13.0, True, "ptolemaic")["rulers"]["term"]
    assert (egyptian, ptolemaic) == ("ME", "VE")
    assert dignities.EGYPTIAN_TERMS != dignities.PTOLEMAIC_TERMS


def test_every_sign_s_terms_cover_all_thirty_degrees():
    for table in (dignities.EGYPTIAN_TERMS, dignities.PTOLEMAIC_TERMS):
        for sign in table:
            assert len(sign) == 5
            assert sign[-1][1] == 30
            assert [b for _, b in sign] == sorted(b for _, b in sign)


def test_an_unknown_term_system_is_refused_by_name():
    with pytest.raises(dignities.UnknownTermSystem, match="egyptian"):
        dignities.dignities_for("SO", 5.0, True, "babylonian")


def test_the_score_is_lillys():
    """Mars at 5 Aries has its own sign and its own face: five plus one."""
    assert dignities.dignities_for("MA", 5.0, True)["score"] == 6


def test_peregrine_means_no_relationship_at_all():
    """A planet in fall is badly placed, but it is not a stranger."""
    assert dignities.dignities_for("MO", 5.0, True)["peregrine"] is True
    assert dignities.dignities_for("SA", 5.0, True)["peregrine"] is False


def test_the_outer_planets_have_no_dignities_to_hold():
    assert dignities.dignities_for("PL", 5.0, True)["dignities"] == []


# --- the lots --------------------------------------------------------------

ASTRO_SEEK = {
    # Astro-Seek's traditional chart for 1 Jan 1970 00:00 UT at 0N 0E.
    "fortune": (10, 35, "Capricorn"),
    "spirit": (11, 40, "Cancer"),
    "eros": (18, 20, "Aries"),
    "victory": (20, 28, "Gemini"),
    "necessity": (29, 33, "Libra"),
    "courage": (12, 46, "Sagittarius"),
    "nemesis": (2, 36, "Aquarius"),
}


@pytest.fixture
def reference_chart():
    return build_chart(
        "1970-01-01", "00:00:00", "W", latitude=0.0, longitude=0.0, utc_offset=0.0
    )


def test_the_sect_is_read_from_the_suns_own_position(reference_chart):
    assert reference_chart["lots"]["sect"] == "night"


def test_every_lot_matches_astro_seek_to_the_minute(reference_chart):
    found = {l["key"]: l for l in reference_chart["lots"]["lots"]}
    assert set(found) == set(ASTRO_SEEK)
    for key, (degree, minute, sign) in ASTRO_SEEK.items():
        position = found[key]["position"]
        assert (position["degree"], position["minute"], position["sign"]) == (
            degree, minute, sign
        ), f"{key}: {position['formatted']}"


def test_fortune_and_spirit_trade_places_between_day_and_night():
    longitudes = {"SO": 280.0, "MO": 190.0, "ME": 299.0, "VE": 274.0,
                  "MA": 342.0, "JU": 212.0, "SA": 32.0}
    day = {l["key"]: l["longitude"] for l in lots.calculate(longitudes, 191.0, True)}
    night = {l["key"]: l["longitude"] for l in lots.calculate(longitudes, 191.0, False)}
    assert day["fortune"] == pytest.approx(night["spirit"])
    assert day["spirit"] == pytest.approx(night["fortune"])


def test_a_sun_above_the_horizon_is_a_day_birth():
    # Ascendant at 0 Aries: the Sun in the tenth is above the horizon.
    assert lots.is_day_birth(270.0, 0.0) is True
    # and in the fourth it is beneath it.
    assert lots.is_day_birth(90.0, 0.0) is False


def test_the_later_lots_are_built_on_fortune_and_spirit():
    """Eros is measured from Spirit, so moving Spirit has to move Eros."""
    base = {"SO": 0.0, "MO": 90.0, "ME": 10.0, "VE": 20.0, "MA": 30.0,
            "JU": 40.0, "SA": 50.0}
    moved = {**base, "MO": 120.0}
    first = {l["key"]: l["longitude"] for l in lots.calculate(base, 0.0, True)}
    second = {l["key"]: l["longitude"] for l in lots.calculate(moved, 0.0, True)}
    assert first["eros"] != second["eros"]


# --- profections -----------------------------------------------------------

LIBRA_ASC = 191.1294


def test_the_first_year_of_life_is_the_first_house():
    p = profections.profection("1970-01-01", LIBRA_ASC, date(1970, 6, 1))
    assert (p["age"], p["house"], p["sign"]) == (0, 1, "Libra")


def test_the_profection_turns_on_the_birthday_not_the_new_year():
    born, asc = "1997-05-18", LIBRA_ASC
    assert profections.profection(born, asc, date(2026, 5, 17))["age"] == 28
    assert profections.profection(born, asc, date(2026, 5, 18))["age"] == 29


def test_twelve_years_brings_the_profection_back_to_the_first_house():
    for age in (0, 12, 24, 36):
        on = date(1970 + age, 1, 1)
        assert profections.profection("1970-01-01", LIBRA_ASC, on)["house"] == 1


def test_the_lord_of_the_year_rules_the_profected_sign():
    """Age 48 on a Libra Ascendant returns to Libra, so Venus has the year."""
    p = profections.profection("1970-01-01", LIBRA_ASC, date(2018, 1, 1))
    assert (p["age"], p["sign"], p["lord_of_the_year"]) == (48, "Libra", "VE")


def test_a_leap_day_birth_turns_on_the_first_of_march_in_common_years():
    p = profections.profection("1996-02-29", LIBRA_ASC, date(2027, 3, 1))
    assert p["begins"] == "2027-03-01"


def test_a_date_before_birth_has_no_profection():
    assert profections.profection("1970-01-01", LIBRA_ASC, date(1969, 12, 31)) is None


def test_a_span_prints_one_row_per_year():
    years = profections.span("1970-01-01", LIBRA_ASC, 48, 59)
    assert len(years) == 12
    assert [y["house"] for y in years] == list(range(1, 13))


# --- all three reach the chart ---------------------------------------------

def test_a_cast_chart_carries_dignities_lots_and_the_profected_year():
    chart = build_chart(
        "1997-05-18", "20:38:00", "R",
        latitude=30.3017, longitude=71.9321, timezone_name="Asia/Karachi",
    )
    assert chart["lots"]["sect"] == "night"
    assert len(chart["lots"]["lots"]) == 7
    assert chart["profection"]["lord_of_the_year"]
    dignified = [b for b in chart["bodies"] if "dignity" in b]
    assert len(dignified) == len(dignities.DIGNIFIED)


def test_the_term_system_travels_with_the_chart():
    common = dict(latitude=30.3017, longitude=71.9321, timezone_name="Asia/Karachi")
    egyptian = build_chart("1997-05-18", "20:38:00", "R", **common)
    ptolemaic = build_chart(
        "1997-05-18", "20:38:00", "R", term_system="ptolemaic", **common
    )
    assert egyptian["term_system"] == "egyptian"
    assert ptolemaic["term_system"] == "ptolemaic"


# --- the term system travels through the request ---------------------------

def test_the_api_accepts_a_term_system(api_client):
    body = {"date": "1997-05-18", "time": "20:38:00", "latitude": 30.3017,
            "longitude": 71.9321, "timezone": "Asia/Karachi"}
    egyptian = api_client.post("/chart", json=body).json()
    ptolemaic = api_client.post(
        "/chart", json={**body, "term_system": "ptolemaic"}
    ).json()
    assert egyptian["term_system"] == "egyptian"
    assert ptolemaic["term_system"] == "ptolemaic"


def test_an_unknown_term_system_is_refused_by_the_api(api_client):
    response = api_client.post("/chart", json={
        "date": "1997-05-18", "time": "20:38:00", "latitude": 30.3017,
        "longitude": 71.9321, "timezone": "Asia/Karachi",
        "term_system": "babylonian",
    })
    assert 400 <= response.status_code < 500
    assert "egyptian" in response.text


def test_the_page_does_not_ask_which_terms_to_use(api_client):
    """The client asked for terms, not for a choice of them.

    Astro-Seek's traditional chart, which is what he pointed at, shows the
    Egyptian terms, so that is what the page shows and there is nothing to
    decide. Which table Lilly himself printed is a question only he can
    settle, and until he does a switch on the form would be inviting it.
    """
    form = api_client.get("/view").text
    assert 'name="term_system"' not in form
    assert "Egyptian" not in form and "Ptolemaic" not in form


def test_but_the_api_still_takes_one_so_the_second_table_is_not_wasted(api_client):
    body = {"date": "1997-05-18", "time": "20:38:00", "latitude": 30.3017,
            "longitude": 71.9321, "timezone": "Asia/Karachi"}
    default = api_client.post("/chart", json=body).json()
    other = api_client.post(
        "/chart", json={**body, "term_system": "ptolemaic"}
    ).json()
    assert default["term_system"] == "egyptian"
    assert other["term_system"] == "ptolemaic"

    def jupiter(chart):
        return next(b["dignity"]["score"] for b in chart["bodies"] if b["code"] == "JU")

    # The two tables genuinely disagree, which is the whole reason both exist.
    assert jupiter(default) != jupiter(other)
