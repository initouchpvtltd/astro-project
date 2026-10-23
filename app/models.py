"""Request and response schemas.

These drive both the validation and the interactive documentation page, so the
descriptions and examples here are what the client sees when testing.
"""

from .dignities import DEFAULT_TERMS, TERM_SYSTEMS
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import DEFAULT_HOUSE_SYSTEM, HOUSE_SYSTEMS


def _check_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD, for example 2026-05-14")
    return value


def _check_time(value):
    # Accept HH:MM as well, since typing the seconds every time is tedious.
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            datetime.strptime(value, fmt)
            return value if fmt == "%H:%M:%S" else f"{value}:00"
        except ValueError:
            continue
    raise ValueError("time must be HH:MM:SS or HH:MM, for example 12:00:00")


def _check_term_system(value):
    if str(value).lower() not in TERM_SYSTEMS:
        raise ValueError(
            "Terms must be one of: " + ", ".join(sorted(TERM_SYSTEMS))
        )
    return str(value).lower()


def _check_house_system(value):
    value = value.upper()
    if value not in HOUSE_SYSTEMS:
        raise ValueError(
            "A house system must be one of: "
            + ", ".join(f"{k} ({v})" for k, v in HOUSE_SYSTEMS.items())
        )
    return value


class ChartRequest(BaseModel):
    """Either name a city, or give coordinates with a timezone or offset."""

    date: str = Field(..., description="Local date, YYYY-MM-DD", examples=["2026-09-22"])
    time: str = Field(..., description="Local time, HH:MM:SS", examples=["12:00:00"])

    city: str | None = Field(
        None,
        description="City name. Its coordinates and timezone are looked up, "
        "and daylight saving is applied as it stood on that date.",
        examples=["Madrid"],
    )
    country: str | None = Field(
        None,
        description="Two-letter country code, to separate places that share a "
        "name. Toledo in ES is not Toledo in US.",
        examples=["ES"],
    )

    latitude: float | None = Field(
        None, ge=-90, le=90, description="Degrees north, negative for south. Only if no city."
    )
    longitude: float | None = Field(
        None, ge=-180, le=180, description="Degrees east, negative for west. Only if no city."
    )
    timezone: str | None = Field(
        None,
        description="IANA timezone, used with coordinates instead of a city.",
        examples=["Europe/Madrid"],
    )
    utc_offset: float | None = Field(
        None,
        ge=-14,
        le=14,
        description="Hours ahead of UTC. Overrides the timezone if both are given.",
    )

    house_system: str = Field(
        DEFAULT_HOUSE_SYSTEM,
        description="One letter: " + ", ".join(f"{k}={v}" for k, v in HOUSE_SYSTEMS.items()),
        examples=["R"],
    )

    term_system: str = Field(
        DEFAULT_TERMS,
        description="Which table of terms to judge dignity by: "
                    + ", ".join(sorted(TERM_SYSTEMS)),
        examples=["egyptian"],
    )

    _v_date = field_validator("date")(classmethod(lambda cls, v: _check_date(v)))
    _v_terms = field_validator("term_system")(
        classmethod(lambda cls, v: _check_term_system(v))
    )
    _v_time = field_validator("time")(classmethod(lambda cls, v: _check_time(v)))
    _v_house = field_validator("house_system")(classmethod(lambda cls, v: _check_house_system(v)))

    @model_validator(mode="after")
    def _check_place_is_answerable(self):
        if not self.city and (self.latitude is None or self.longitude is None):
            raise ValueError(
                "Give either a city name, or both latitude and longitude."
            )
        if not self.city and self.timezone is None and self.utc_offset is None:
            raise ValueError(
                "Coordinates need a time zone as well, so the local time can "
                "be converted. Give a name such as 'Europe/Madrid', or an "
                "offset from UTC such as '+2'."
            )
        return self


class SearchRequest(BaseModel):
    """A formula, a range to search, and where to search it from."""

    formula: str = Field(
        ...,
        description="A ZET 9 Geo formula, for example Sun.120.Moon or Mer.S",
        examples=["Mer.S"],
    )
    start: str = Field(..., description="Search from this date, YYYY-MM-DD", examples=["2027-01-01"])
    end: str = Field(..., description="Search until this date, YYYY-MM-DD", examples=["2027-12-31"])
    step_seconds: int = Field(
        3600,
        ge=60,
        description="How finely to step through time. 3600 is hourly, 86400 daily. "
        "A station lasts about an hour, so use 900 or less when searching for one.",
        examples=[3600],
    )

    city: str | None = Field(
        None,
        description="Needed only for formulas using houses or planetary hours.",
        examples=["Madrid"],
    )
    country: str | None = Field(None, description="Two-letter country code", examples=["ES"])
    latitude: float | None = Field(None, ge=-90, le=90, description="Instead of a city")
    longitude: float | None = Field(None, ge=-180, le=180, description="Instead of a city")

    natal_date: str | None = Field(
        None,
        description="Birth date, YYYY-MM-DD. Needed for formulas using the "
        "apostrophe, which compare a moving body against a natal chart.",
        examples=["1990-05-03"],
    )
    natal_time: str | None = Field(None, description="Birth time, HH:MM:SS", examples=["14:30:00"])
    natal_city: str | None = Field(None, description="Birth city", examples=["Barcelona"])
    natal_country: str | None = Field(None, description="Two-letter country code")
    natal_latitude: float | None = Field(None, ge=-90, le=90)
    natal_longitude: float | None = Field(None, ge=-180, le=180)
    natal_timezone: str | None = Field(
        None, description="IANA timezone of the birth place", examples=["Europe/Madrid"]
    )
    natal_utc_offset: float | None = Field(None, ge=-14, le=14)

    house_system: str = Field(DEFAULT_HOUSE_SYSTEM, description="One letter, R is Regiomontanus")
    orb_system: str | None = Field(
        None,
        description="'moiety' for the traditional averaged orbs, 'fixed' for the "
        "aspect-based orbs from your ZET file. Defaults to moiety.",
        examples=["moiety"],
    )

    _v_start = field_validator("start")(classmethod(lambda cls, v: _check_date(v)))
    _v_end = field_validator("end")(classmethod(lambda cls, v: _check_date(v)))

    @field_validator("natal_date")
    @classmethod
    def _v_natal_date(cls, value):
        return None if value is None else _check_date(value)

    @field_validator("natal_time")
    @classmethod
    def _v_natal_time(cls, value):
        return None if value is None else _check_time(value)

    @model_validator(mode="after")
    def _natal_chart_is_complete(self):
        if self.natal_date and not self.natal_time:
            raise ValueError("A birth date needs a birth time as well.")
        if self.natal_date and not (
            self.natal_city
            or (self.natal_latitude is not None and self.natal_longitude is not None)
        ):
            raise ValueError("A birth date needs a birth place as well.")
        return self
    _v_house = field_validator("house_system")(classmethod(lambda cls, v: _check_house_system(v)))

    @field_validator("orb_system")
    @classmethod
    def _check_orb_system(cls, value):
        if value is None:
            return None
        from .orbs import SYSTEMS

        lowered = value.lower()
        if lowered not in SYSTEMS:
            raise ValueError("Orbs must be one of: " + ", ".join(SYSTEMS))
        return lowered
