"""City lookup through GeoNames.

A city name gives us three things a chart needs: latitude, longitude and the
IANA timezone. The timezone matters as much as the coordinates, because it is
what decides the UTC offset for that particular date.

GeoNames needs a free username, supplied through the GEONAMES_USERNAME
environment variable. Their demo account exists but is permanently over quota,
so it is not a usable fallback.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import ratelimit

# secure.geonames.org is the TLS endpoint. The plain api.geonames.org host is
# HTTP only, which would put the account username in clear text on the wire.
GEONAMES_URL = os.environ.get(
    "GEONAMES_URL", "https://secure.geonames.org/searchJSON"
)
REQUEST_TIMEOUT_SECONDS = 10

# Feature codes for populated places, so a search for "Madrid" returns the city
# rather than the province, a river or a hotel.
PLACE_FEATURE_CLASS = "P"

# Place coordinates do not change, and the free tier is rate limited, so the
# same lookup is never paid for twice within a process.
_CACHE = {}


class GeocodingError(RuntimeError):
    """The lookup could not be completed."""


class CityNotFound(LookupError):
    """The place name matched nothing."""


def _username():
    name = os.environ.get("GEONAMES_USERNAME", "").strip()
    if not name:
        raise GeocodingError(
            "GEONAMES_USERNAME is not set. Register a free account at "
            "geonames.org, enable the free web services in the account "
            "settings, then set the username in the environment."
        )
    return name


def _request(params):
    # Counted here rather than at the endpoint so cache hits cost nothing and
    # only real upstream calls draw down the account allowance.
    try:
        ratelimit.geonames_budget.check("global")
    except ratelimit.RateLimitExceeded as exc:
        raise GeocodingError(
            "The GeoNames lookup allowance for this hour has been used up. "
            "Charts from coordinates still work."
        ) from exc

    url = f"{GEONAMES_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GeocodingError(f"GeoNames returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise GeocodingError(f"Could not reach GeoNames: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GeocodingError("GeoNames returned a response that was not JSON") from exc

    if not isinstance(payload, dict):
        raise GeocodingError("GeoNames returned an unexpected response shape")

    # GeoNames reports quota and auth problems inside a 200 response.
    if "status" in payload:
        message = payload["status"].get("message", "unknown error")
        raise GeocodingError(f"GeoNames: {message}")

    return payload


def _shape(entry):
    """Convert one GeoNames record, or None if it is unusable.

    A third party's response is not a contract. An entry missing coordinates,
    or carrying something that will not parse as a number, is dropped rather
    than allowed to raise out of the request.
    """
    try:
        latitude = float(entry["lat"])
        longitude = float(entry["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    return {
        "name": entry.get("name"),
        "country": entry.get("countryName"),
        "country_code": entry.get("countryCode"),
        "region": entry.get("adminName1") or None,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": (entry.get("timezone") or {}).get("timeZoneId"),
        "population": entry.get("population") or 0,
        "geonames_id": entry.get("geonameId"),
    }


def _query(search_field, name, country, limit):
    params = {
        search_field: name,
        "maxRows": max(1, min(int(limit), 50)),
        "featureClass": PLACE_FEATURE_CLASS,
        "orderby": "population",
        "style": "FULL",  # FULL is what includes the timezone
        "username": _username(),
    }
    if country:
        params["country"] = country.strip().upper()
    shaped = (_shape(entry) for entry in _request(params).get("geonames", []))
    return [entry for entry in shaped if entry is not None]


def search(name, country=None, limit=10):
    """Search for places by name, most populous first.

    Exact name matches are tried first. GeoNames' general search also matches
    the province, so a plain search for "Toledo" in Spain returns Talavera de
    la Reina ahead of Toledo itself, because Talavera sits in Toledo province
    and is slightly larger. Asking for the exact name avoids that, and the
    broad search is kept as a fallback so partial names still work.

    A two-letter country code separates the many duplicated place names,
    Toledo in Spain against Toledo in Ohio being the obvious one.
    """
    if not name or not name.strip():
        raise CityNotFound("No place name given.")
    name = name.strip()

    cache_key = (name.lower(), (country or "").upper(), int(limit))
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # Exact first, so "Toledo" in Spain is Toledo and not the larger town in
    # Toledo province. Then names beginning with what was typed, which is what
    # makes an autocomplete useful. Then the broad search as a last resort.
    results, seen = [], set()
    for field in ("name_equals", "name_startsWith", "q"):
        if len(results) >= limit:
            break
        for entry in _query(field, name, country, limit):
            key = entry["geonames_id"] or (entry["name"], entry["latitude"])
            if key not in seen:
                seen.add(key)
                results.append(entry)

    if not results:
        where = f" in {country.upper()}" if country else ""
        raise CityNotFound(f"No place found matching {name!r}{where}.")

    # A place without a timezone is unusable for casting a chart.
    usable = [r for r in results if r["timezone"]]
    if not usable:
        raise GeocodingError(
            f"GeoNames returned matches for {name!r} but none carried a timezone."
        )

    _CACHE[cache_key] = usable
    return usable


def _to_arcminute(degrees):
    """Round a coordinate to the nearest minute of arc."""
    return round(degrees * 60.0) / 60.0


def resolve(name, country=None):
    """Return the single best match for a place name, ready to cast from.

    Asking for one result lets the search stop as soon as the exact-name query
    answers, so casting a chart costs a single call rather than the three an
    autocomplete needs.

    The coordinates come back on the minute of arc. GeoNames holds a city to
    five decimal places; Astro-Seek, which the client checks every figure
    against, holds its own gazetteer to the minute. The gap is small -- about
    600 metres for Barcelona -- but it moves the Ascendant by some twenty
    arcseconds, enough to drop a position into the minute below and read as a
    mistake. Rounding puts us on their gazetteer rather than ours.

    This is the one door every cast place comes through, the chart and the
    scanner alike, so the two can never end up on different coordinates.
    Coordinates a caller supplies by hand are their own and are left alone, and
    `search` still reports what GeoNames actually said.
    """
    place = search(name, country=country, limit=1)[0]
    return {
        **place,
        "latitude": _to_arcminute(place["latitude"]),
        "longitude": _to_arcminute(place["longitude"]),
    }
