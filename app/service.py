"""Turns a request into a chart.

Sits between the API and the calculation layers, deciding how a place and a
local time become a UTC moment and a pair of coordinates.
"""

import re
from datetime import datetime, timezone

from . import dignities, geocoding, lots, profections, timeutils
from .ephemeris import chart_for_utc


class RequestError(ValueError):
    """The request cannot be satisfied as written."""


_COORDINATE = re.compile(
    r"""^\s*
    (?P<lead>[NSEW+-])?\s*
    (?P<degree>\d+(?:\.\d+)?)\s*
    (?:[^\d.NSEWnsew]+(?P<minute>\d+(?:\.\d+)?)\s*
       (?:[^\d.NSEWnsew]+(?P<second>\d+(?:\.\d+)?))?
    )?
    [^\dNSEWnsew]*
    (?P<trail>[NSEW])?\s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def read_coordinate(text, positive, negative):
    """Read a latitude or longitude the way a person writes one.

    Astro-Seek prints 41\u00b023'N and a decimal is what an API wants, so both
    are accepted, as is the degrees-minutes-seconds in between. The hemisphere
    may lead or trail, or be a sign, which is how the different sources differ.

    Returns None for blank input, so a caller can fall back to a place name.
    """
    text = (text or "").strip()
    if not text:
        return None

    match = _COORDINATE.match(text)
    if not match:
        raise RequestError(
            f"{text!r} is not a coordinate. Write it as 41.3833, "
            f"or as 41\u00b023'{positive}."
        )

    degrees = float(match.group("degree"))
    degrees += float(match.group("minute") or 0) / 60.0
    degrees += float(match.group("second") or 0) / 3600.0

    marker = (match.group("lead") or match.group("trail") or "").upper()
    if marker == negative or marker == "-":
        degrees = -degrees
    elif marker and marker not in (positive, "+"):
        raise RequestError(
            f"{marker!r} is not a direction for this coordinate. "
            f"Use {positive} or {negative}."
        )
    return degrees


def read_zone(text):
    """A time zone written either as a name or as an offset from UTC.

    Returns (timezone_name, utc_offset), one of which is always None. A bare
    number is an offset: "+2" is the whole of the information Astro-Seek shows
    beside a manually entered place.
    """
    text = (text or "").strip()
    if not text:
        return None, None
    try:
        return None, float(text.replace("+", "", 1) if text.startswith("+") else text)
    except ValueError:
        # Hand it on in the gazetteer's own capitals when it is a known zone,
        # so the chart reports the zone rather than the typing.
        return timeutils.canonical_zone(text) or text, None


def resolve_location(city=None, country=None, latitude=None, longitude=None, timezone_name=None):
    """Work out where the chart is for.

    A city name is looked up. Otherwise coordinates are used as given, and the
    caller must supply either a timezone or an explicit offset for the time.
    """
    if city:
        try:
            match = geocoding.resolve(city, country=country)
        except geocoding.CityNotFound as exc:
            raise RequestError(str(exc)) from exc
        return {
            "source": "geonames",
            "name": match["name"],
            "country": match["country"],
            "country_code": match["country_code"],
            "region": match["region"],
            "latitude": match["latitude"],
            "longitude": match["longitude"],
            "timezone": match["timezone"],
        }

    if latitude is None or longitude is None:
        raise RequestError(
            "Give either a city name, or both latitude and longitude."
        )

    return {
        "source": "coordinates",
        "name": None,
        "country": None,
        "country_code": None,
        "region": None,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name,
    }


def resolve_time(date, time, location, utc_offset=None):
    """Convert the local time to UTC.

    An explicit offset always wins, since a caller who states one usually knows
    something the timezone database does not. Otherwise the place's timezone
    decides, which is what handles daylight saving for that particular date.
    """
    if utc_offset is not None:
        return timeutils.convert_with_offset(date, time, utc_offset)

    if location["timezone"]:
        return timeutils.convert(date, time, location["timezone"])

    raise RequestError(
        "No time zone for this location. Give a city name, or a time zone "
        "such as 'Europe/Madrid', or an offset from UTC such as '+2'."
    )


def build_chart(
    date,
    time,
    house_system,
    city=None,
    country=None,
    latitude=None,
    longitude=None,
    timezone_name=None,
    utc_offset=None,
    term_system=None,
    profection_on=None,
):
    location = resolve_location(city, country, latitude, longitude, timezone_name)
    moment = resolve_time(date, time, location, utc_offset)

    moment_utc = datetime.strptime(moment["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    chart = chart_for_utc(
        moment_utc, location["latitude"], location["longitude"], house_system
    )

    chart["input"] = {
        "date": date,
        "time": time,
        "house_system": house_system.upper(),
    }
    chart["location"] = location
    chart["time"] = moment
    chart["utc"] = moment["utc"]

    # The traditional reading of the same chart: which planets are at home in
    # the degrees they occupy, where the lots fall, and which sign the year
    # has profected to. All three are derived from what is already computed
    # above, so they cost nothing but the arithmetic.
    chart["lots"] = lots.for_chart(chart)
    sect_is_day = (chart["lots"] or {}).get("sect", "day") == "day"
    for body in chart["bodies"]:
        if "error" in body:
            continue
        if body["code"] in dignities.DIGNIFIED:
            body["dignity"] = dignities.dignities_for(
                body["code"], body["longitude"], sect_is_day, term_system
            )
    chart["term_system"] = (term_system or dignities.DEFAULT_TERMS).lower()
    chart["profection"] = profections.for_chart(chart, profection_on)
    return chart
