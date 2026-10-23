"""Annual profections.

The oldest time-lord technique there is, and the simplest: the Ascendant
advances one whole sign for each year of life. At thirty the chart has turned
thirty signs, which is two and a half laps, so the thirty-first year is read
from the seventh house. The planet ruling the sign arrived at becomes Lord of
the Year, and the year is judged largely by how that planet sits in the natal
chart.

A profection year runs birthday to birthday, not January to January, which is
the only part anyone gets wrong.
"""

from datetime import date

from .constants import SIGNS
from .dignities import RULERS

HOUSE_NAMES = [
    "self and body", "resources", "siblings and short journeys", "home and family",
    "children and pleasure", "illness and service", "marriage and partners",
    "death and inheritance", "travel and belief", "career and standing",
    "friends and hopes", "hidden things and enemies",
]


def _completed_years(born, on):
    """Whole years lived, counting the birthday itself as the turn.

    February the twenty-ninth has no birthday in most years, so the comparison
    is made on month and day and a leap-day birth turns on the first of March.
    """
    years = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        years -= 1
    return years


def _birthday_in(year, born):
    try:
        return date(year, born.month, born.day)
    except ValueError:          # 29 February in a common year
        return date(year, 3, 1)


def profection(birth_date, ascendant_longitude, on=None):
    """The profected sign and the Lord of the Year for a given date."""
    born = birth_date if isinstance(birth_date, date) else date.fromisoformat(str(birth_date)[:10])
    on = on or date.today()
    on = on if isinstance(on, date) else date.fromisoformat(str(on)[:10])

    age = _completed_years(born, on)
    if age < 0:
        return None

    natal_sign = int(ascendant_longitude // 30) % 12
    step = age % 12
    sign = (natal_sign + step) % 12
    house = step + 1
    begins = _birthday_in(born.year + age, born)
    ends = _birthday_in(born.year + age + 1, born)

    return {
        "age": age,
        "house": house,
        "house_meaning": HOUSE_NAMES[step],
        "sign": SIGNS[sign],
        "lord_of_the_year": RULERS[sign],
        "begins": begins.isoformat(),
        "ends": ends.isoformat(),
    }


def span(birth_date, ascendant_longitude, first_age=0, last_age=None):
    """A run of profection years, the way the tables are printed."""
    born = birth_date if isinstance(birth_date, date) else date.fromisoformat(str(birth_date)[:10])
    last_age = first_age + 11 if last_age is None else last_age
    years = []
    for age in range(max(0, first_age), last_age + 1):
        years.append(profection(born, ascendant_longitude, _birthday_in(born.year + age, born)))
    return years


def for_chart(chart, on=None):
    """The current profection for a cast chart."""
    birth = chart.get("input", {}).get("date")
    if not birth:
        return None
    return profection(birth, chart["houses"]["ascendant"]["longitude"], on)
