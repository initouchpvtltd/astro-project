"""Astrological Formula Search API.

Milestone 1 established the calculation layer. Milestone 2 adds city lookup and
timezone conversion, so a chart can be cast from a place name rather than
coordinates. The formula parser and time scanner follow in milestone 3.
"""

from datetime import datetime, timezone

import swisseph as swe
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from . import geocoding, ratelimit, views
from .constants import (
    BODIES,
    DEFAULT_HOUSE_SYSTEM,
    HOUSE_SYSTEMS,
    STATIONARY_THRESHOLD_DEG_PER_DAY,
)
from .ephemeris import EPHEMERIS_SOURCE
from .formula.lexer import FormulaSyntaxError
from .models import ChartRequest, SearchRequest
from .dignities import DEFAULT_TERMS
from .scanner import ScanError, scan, uses_transits
from . import service as resolve
from .service import RequestError, build_chart, resolve_location, resolve_time
from .timeutils import TimeConversionError

app = FastAPI(
    title="Astrological Formula Search API",
    version="0.3.0",
    description=(
        "**Milestone 3 — Formula parser and time scanner**\n\n"
        "Cast a chart from a city name. The coordinates and timezone are looked "
        "up, and the UTC offset is worked out from the daylight saving rules as "
        "they actually stood on that date.\n\n"
        "Use **/chart** below: click *Try it out*, fill in the fields and press "
        "*Execute*. Cast the same chart in ZET and compare.\n\n"
        "Coordinates still work, for places the database does not carry. Pass "
        "`latitude` and `longitude` with either a `timezone` or a `utc_offset`.\n\n"
        "**/search** is the new one: give it a formula, a date range and a step "
        "size, and it returns the periods when that formula holds, in the same "
        "begin-and-end form ZET reports.\n\n"
        "Coming next: milestone 4 adds the WordPress plugin and deployment."
    ),
)


def _enforce(limiter, request):
    """Apply a rate limit, turning a breach into a 429 with Retry-After."""
    try:
        limiter.check(ratelimit.client_key(request))
    except ratelimit.RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after)},
        )


@app.get("/", tags=["Service"], summary="Service information")
def root():
    return {
        "service": "Astrological Formula Search API",
        "milestone": "3 — Formula parser and time scanner",
        "ephemeris_source": EPHEMERIS_SOURCE,
        "swisseph_version": swe.version,
        "test_page": "/docs",
    }


@app.get("/health", tags=["Service"], summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/bodies", tags=["Reference"], summary="Bodies and house systems available")
def bodies():
    """Every body the service calculates, in all three ZET notations."""
    return {
        "bodies": [{"code": b.code, "trigram": b.trigram, "name": b.name} for b in BODIES],
        "house_systems": HOUSE_SYSTEMS,
        "stationary_threshold_deg_per_day": STATIONARY_THRESHOLD_DEG_PER_DAY,
    }


@app.get("/cities", tags=["Reference"], summary="Search for a city")
def cities(
    request: Request,
    q: str = Query(..., description="Place name to search for", examples=["Madrid"]),
    country: str | None = Query(
        None, description="Two-letter country code to narrow the search", examples=["ES"]
    ),
    limit: int = Query(10, ge=1, le=50, description="How many matches to return"),
):
    """Find a place and its timezone.

    Useful for checking which match the chart endpoint will pick, and for
    separating places that share a name. Results come back most populous first.
    """
    _enforce(ratelimit.cities_limiter, request)
    try:
        return {"query": q, "country": country, "results": geocoding.search(q, country, limit)}
    except geocoding.CityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except geocoding.GeocodingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/search", tags=["Search"], summary="Find when a formula holds")
def search(search_request: SearchRequest, request: Request):
    """Search a date range for the periods when a formula is true.

    Steps through time at the interval you choose, tests the formula at each
    step, and returns the stretches where it held, the way ZET reports
    realization intervals.

    A location is needed only for formulas that mention houses or planetary
    hours. `Mer.S` works anywhere; `Mar.H7` does not.
    """
    _enforce(ratelimit.chart_limiter, request)

    latitude, longitude = search_request.latitude, search_request.longitude
    if search_request.city:
        try:
            place = geocoding.resolve(search_request.city, search_request.country)
            latitude, longitude = place["latitude"], place["longitude"]
        except geocoding.CityNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except geocoding.GeocodingError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    start = datetime.strptime(search_request.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(search_request.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # The natal chart, when the formula compares against one.
    # A birth chart is only consulted by formulas that carry the apostrophe.
    # Resolving one for a formula that will never read it would cost a GeoNames
    # lookup out of a limited daily allowance, and would leave the response
    # claiming a natal chart that played no part in the answer.
    try:
        wants_natal = uses_transits(search_request.formula)
    except FormulaSyntaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    unused_natal = bool(search_request.natal_date) and not wants_natal

    natal_moment = natal_latitude = natal_longitude = None
    if search_request.natal_date and wants_natal:
        try:
            place = resolve_location(
                city=search_request.natal_city,
                country=search_request.natal_country,
                latitude=search_request.natal_latitude,
                longitude=search_request.natal_longitude,
                timezone_name=search_request.natal_timezone,
            )
            moment = resolve_time(
                search_request.natal_date,
                search_request.natal_time,
                place,
                search_request.natal_utc_offset,
            )
        except (RequestError, TimeConversionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except geocoding.CityNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except geocoding.GeocodingError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        natal_latitude, natal_longitude = place["latitude"], place["longitude"]
        natal_moment = datetime.strptime(
            moment["utc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

    try:
        result = scan(
            formula=search_request.formula,
            start=start,
            end=end,
            step_seconds=search_request.step_seconds,
            latitude=latitude,
            longitude=longitude,
            house_system=search_request.house_system,
            orb_system=search_request.orb_system,
            natal_moment=natal_moment,
            natal_latitude=natal_latitude,
            natal_longitude=natal_longitude,
        )
    except FormulaSyntaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except swe.Error as exc:
        raise HTTPException(status_code=500, detail=f"Ephemeris error: {exc}")

    if unused_natal:
        # Saying so is better than silently dropping it: the birth details were
        # typed in for a reason, and the apostrophe is what would have used them.
        result["warnings"].append(
            "This formula has no apostrophe, so it reads only the sky at each "
            "moment. The birth details were not used. Write the moving body "
            "with an apostrophe, as in MA'.90.SA, to search transits against "
            "a birth chart."
        )
    return result


@app.post("/chart", tags=["Calculation"], summary="Planetary positions and house cusps")
def chart(chart_request: ChartRequest, request: Request):
    """Calculate a chart for a given moment and place.

    Give a city name and the coordinates and timezone are looked up for you,
    with daylight saving applied as it stood on that date. Or give coordinates
    with a timezone or an explicit UTC offset.

    Returns, for every body: ecliptic longitude, the position formatted as sign
    and degree, daily motion, and whether it is direct, retrograde or
    stationary. House cusps use Regiomontanus by default.
    """
    _enforce(ratelimit.chart_limiter, request)
    try:
        return build_chart(
            date=chart_request.date,
            time=chart_request.time,
            house_system=chart_request.house_system,
            city=chart_request.city,
            country=chart_request.country,
            latitude=chart_request.latitude,
            longitude=chart_request.longitude,
            timezone_name=chart_request.timezone,
            utc_offset=chart_request.utc_offset,
            term_system=chart_request.term_system,
        )
    except (RequestError, TimeConversionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except geocoding.GeocodingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except swe.Error as exc:
        raise HTTPException(status_code=500, detail=f"Ephemeris error: {exc}")


# --- Browsable pages ------------------------------------------------------
# The JSON endpoints above are the product. These render the same calls as a
# chart and a list of dates, which is the shape the WordPress plugin takes.


@app.get("/view", response_class=HTMLResponse, include_in_schema=False)
def view_home(tab: str = Query("chart")):
    tab = "search" if tab == "search" else "chart"
    body = views.search_form() if tab == "search" else views.chart_form()
    return views.page("Astrological Formula Search", body, tab=tab)


@app.get("/view/chart", response_class=HTMLResponse, include_in_schema=False)
def view_chart(
    request: Request,
    date: str = Query(None),
    time: str = Query(None),
    city: str = Query(""),
    city_country: str = Query(""),
    house_system: str = Query(DEFAULT_HOUSE_SYSTEM),
    term_system: str = Query(DEFAULT_TERMS),
    latitude: str = Query(""),
    longitude: str = Query(""),
    tz: str = Query(""),
):
    # Reached with no parameters, which is what happens if someone types the
    # address or follows an old link. Show the form rather than an error.
    if not date or not time:
        return views.page("Chart", views.chart_form(), tab="chart")

    submitted = {
        "date": date, "time": time, "city": city,
        "country": city_country, "house_system": house_system,
        "term_system": term_system, "latitude": latitude,
        "longitude": longitude, "tz": tz,
    }
    try:
        _enforce(ratelimit.chart_limiter, request)
        # Coordinates win over the place name. Someone who typed them has a
        # reason to: two towns share a name, or the gazetteer has the wrong
        # one. Leaving the place in the box is convenient, not a contradiction.
        given_latitude = resolve.read_coordinate(latitude, "N", "S")
        given_longitude = resolve.read_coordinate(longitude, "E", "W")
        placed_by_hand = given_latitude is not None and given_longitude is not None
        zone_name, zone_offset = resolve.read_zone(tz)

        chart_request = ChartRequest(
            date=date, time=time,
            city=None if placed_by_hand else (city or None),
            country=None if placed_by_hand else (city_country or None),
            latitude=given_latitude if placed_by_hand else None,
            longitude=given_longitude if placed_by_hand else None,
            timezone=zone_name if placed_by_hand else None,
            utc_offset=zone_offset if placed_by_hand else None,
            house_system=house_system,
            term_system=term_system,
        )
        chart = build_chart(
            date=chart_request.date,
            time=chart_request.time,
            house_system=chart_request.house_system,
            city=chart_request.city,
            country=chart_request.country,
            latitude=chart_request.latitude,
            longitude=chart_request.longitude,
            timezone_name=chart_request.timezone,
            utc_offset=chart_request.utc_offset,
            term_system=chart_request.term_system,
        )
    except HTTPException as exc:
        body = views.chart_form(submitted) + views.error_panel(exc.detail)
        return HTMLResponse(views.page("Chart", body, tab="chart"), status_code=exc.status_code)
    except (RequestError, TimeConversionError, ValueError, geocoding.GeocodingError) as exc:
        body = views.chart_form(submitted) + views.error_panel(_first_message(exc))
        return HTMLResponse(views.page("Chart", body, tab="chart"), status_code=400)

    return views.page("Chart", views.chart_page(chart, submitted), tab="chart")


def _placed(latitude, longitude, zone):
    """Read a hand-entered place, or None when the fields were left blank.

    Returns the four values a request wants: the two coordinates and whichever
    of the time zone's two spellings was given.
    """
    north = resolve.read_coordinate(latitude, "N", "S")
    east = resolve.read_coordinate(longitude, "E", "W")
    if north is None or east is None:
        return None
    name, offset = resolve.read_zone(zone)
    return north, east, name, offset


@app.get("/view/transits", response_class=HTMLResponse, include_in_schema=False)
def view_transits(
    request: Request,
    moment: str = Query(""),
    natal_date: str = Query(""),
    natal_time: str = Query(""),
    natal_city: str = Query(""),
    natal_city_country: str = Query(""),
    natal_latitude: str = Query(""),
    natal_longitude: str = Query(""),
    natal_tz: str = Query(""),
    house_system: str = Query(DEFAULT_HOUSE_SYSTEM),
):
    """One moment's sky drawn around a birth chart.

    Reached from a row of search results. The moving chart is cast for the
    same place as the birth chart, which is the convention: a transit is read
    against the natal houses, and those are fixed by where the person was born.
    """
    # Reached by hand, or from a link that lost its query. This page has no
    # form of its own, so it sends the reader to the one that leads here.
    if not (moment and natal_date and natal_time):
        body = views.search_form() + views.error_panel(
            "A transit chart is drawn for a moment found by a search. "
            "Run a formula with an apostrophe, then open one of its dates."
        )
        return HTMLResponse(
            views.page("Transits", body, tab="search"), status_code=400
        )

    _enforce(ratelimit.chart_limiter, request)
    try:
        given_latitude = resolve.read_coordinate(natal_latitude, "N", "S")
        given_longitude = resolve.read_coordinate(natal_longitude, "E", "W")
        placed_by_hand = given_latitude is not None and given_longitude is not None
        zone_name, zone_offset = resolve.read_zone(natal_tz)

        # Through the request model, so a time typed as 14:30 is completed the
        # same way it is everywhere else rather than only on the forms that
        # happen to go that route.
        asked = ChartRequest(
            date=natal_date, time=natal_time, house_system=house_system,
            city=None if placed_by_hand else (natal_city or None),
            country=None if placed_by_hand else (natal_city_country or None),
            latitude=given_latitude if placed_by_hand else None,
            longitude=given_longitude if placed_by_hand else None,
            timezone=zone_name if placed_by_hand else None,
            utc_offset=zone_offset if placed_by_hand else None,
        )
        natal = build_chart(
            date=asked.date, time=asked.time, house_system=asked.house_system,
            city=asked.city, country=asked.country,
            latitude=asked.latitude, longitude=asked.longitude,
            timezone_name=asked.timezone, utc_offset=asked.utc_offset,
        )
        # The sky is read at the birth place, and `moment` is already UTC, so
        # the offset is zero rather than the birth zone's.
        try:
            when = datetime.strptime(moment[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            # This link is built by the results table, so a bad one means a
            # hand-edited address. Say what the address should look like
            # rather than repeating the library's complaint.
            raise RequestError(
                f"{moment!r} is not a moment. It should read like "
                "2027-02-19T19:45:00Z."
            ) from None
        moving = build_chart(
            date=when.strftime("%Y-%m-%d"), time=when.strftime("%H:%M:%S"),
            house_system=house_system,
            latitude=natal["location"]["latitude"],
            longitude=natal["location"]["longitude"],
            utc_offset=0.0,
        )
    except (RequestError, TimeConversionError, ValueError) as exc:
        body = views.error_panel(_first_message(exc))
        return HTMLResponse(views.page("Transits", body, tab="search"), status_code=400)
    except geocoding.GeocodingError as exc:
        body = views.error_panel(str(exc))
        return HTMLResponse(views.page("Transits", body, tab="search"), status_code=502)

    return views.page(
        "Transits", views.transits_page(natal, moving, moment), tab="search"
    )


@app.get("/view/search", response_class=HTMLResponse, include_in_schema=False)
def view_search(
    request: Request,
    formula: str = Query(None),
    start: str = Query(None),
    end: str = Query(None),
    step_seconds: str = Query("900"),
    city: str = Query(""),
    city_country: str = Query(""),
    orb_system: str = Query("moiety"),
    natal_date: str = Query(""),
    natal_time: str = Query(""),
    natal_city: str = Query(""),
    natal_city_country: str = Query(""),
    latitude: str = Query(""),
    longitude: str = Query(""),
    tz: str = Query(""),
    natal_latitude: str = Query(""),
    natal_longitude: str = Query(""),
    natal_tz: str = Query(""),
):
    if not formula or not start or not end:
        return views.page("Search", views.search_form(), tab="search")

    submitted = {
        "formula": formula, "start": start, "end": end,
        "step_seconds": step_seconds, "city": city, "country": city_country,
        "orb_system": orb_system, "natal_date": natal_date,
        "natal_time": natal_time, "natal_city": natal_city,
        "natal_country": natal_city_country,
        "latitude": latitude, "longitude": longitude, "tz": tz,
        "natal_latitude": natal_latitude, "natal_longitude": natal_longitude,
        "natal_tz": natal_tz,
    }
    try:
        _enforce(ratelimit.chart_limiter, request)
        # Coordinates win over a place name, here as on the chart page: two
        # towns can share one, and a search that scans a year is a poor place
        # to discover the gazetteer picked the other one.
        here = _placed(latitude, longitude, tz)
        born = _placed(natal_latitude, natal_longitude, natal_tz)

        # The form sends one of the preset values, so anything else is a
        # hand-edited address. int() would answer that with its own complaint
        # about literals and bases, which is a sentence for a programmer.
        try:
            step = int(step_seconds or 900)
        except (TypeError, ValueError):
            raise RequestError(
                f"{step_seconds!r} is not a number of seconds. "
                "Choose a precision from the list, or give a whole number."
            ) from None

        search_request = SearchRequest(
            formula=formula, start=start, end=end,
            step_seconds=step,
            city=None if here else (city or None),
            country=None if here else (city_country or None),
            latitude=here[0] if here else None,
            longitude=here[1] if here else None,
            orb_system=orb_system or None,
            natal_date=natal_date or None, natal_time=natal_time or None,
            natal_city=None if born else (natal_city or None),
            natal_country=None if born else (natal_city_country or None),
            natal_latitude=born[0] if born else None,
            natal_longitude=born[1] if born else None,
            natal_timezone=born[2] if born else None,
            natal_utc_offset=born[3] if born else None,
        )
        result = search(search_request, request)
    except HTTPException as exc:
        body = views.search_form(submitted) + views.error_panel(exc.detail)
        return HTMLResponse(views.page("Search", body, tab="search"), status_code=exc.status_code)
    except (ValueError, geocoding.GeocodingError) as exc:
        body = views.search_form(submitted) + views.error_panel(_first_message(exc))
        return HTMLResponse(views.page("Search", body, tab="search"), status_code=400)

    return views.page("Search", views.search_page(result, submitted), tab="search")


def _first_message(exc):
    """Pydantic errors are verbose; show the part that helps."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            return errors()[0]["msg"].replace("Value error, ", "")
        except (IndexError, KeyError, TypeError):
            pass
    return str(exc)
