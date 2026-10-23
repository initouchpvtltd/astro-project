# Astrological Formula Search API

Backend service that searches time for astrological conditions written in ZET 9
Geo formula syntax.

**Current state: Milestone 3 — Formula parser and time scanner.** Give it a
ZET formula, a date range and a step size, and it returns the periods when that
formula holds.

## Running it locally

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000/docs> for the interactive test page.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service information |
| GET | `/health` | Health check, used by Render |
| GET | `/bodies` | Bodies and house systems available |
| GET | `/cities` | Search for a city and its timezone |
| POST | `/chart` | Planetary positions and house cusps |
| POST | `/search` | Find when a formula holds |

### Example

By city name, which resolves the coordinates and the timezone:

```bash
curl -X POST http://127.0.0.1:8000/chart \
  -H 'Content-Type: application/json' \
  -d '{"date": "2026-05-14", "time": "12:00", "city": "Madrid", "country": "ES"}'
```

Or by coordinates, with a timezone or an explicit offset:

```bash
curl -X POST http://127.0.0.1:8000/chart \
  -H 'Content-Type: application/json' \
  -d '{
        "date": "2026-05-14",
        "time": "12:00",
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timezone": "Europe/Madrid",
        "house_system": "R"
      }'
```

Returns, for each of the twenty-four bodies: ecliptic longitude, the position
formatted as sign and degree, ecliptic latitude, distance, daily motion, and
whether it is direct, retrograde or stationary. Plus twelve house cusps, the
Ascendant, Midheaven, ARMC and Vertex.

## Searching

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"formula": "Mer.S", "start": "2027-01-01", "end": "2027-12-31",
       "step_seconds": 900}'
```

Returns the realization intervals, as begin and end pairs, the way ZET reports
them. The scan steps through time at the interval you choose and reports the
stretches where the formula held, so the precision is the step you asked for.

### What the parser understands

| Form | Example |
|---|---|
| Aspect by degree or name | `Sun.120.Moon`, `Mer.Sxt.Jup` |
| With dynamics | `Sun.120AF.Lun` — applying, first body ahead |
| Explicit orb range | `ME.[131-133].MA` |
| Sign, or a set of them | `Sun.Ari`, `Sun.Ari,Leo,Sgr` |
| House | `Mar.H7` |
| Motion phase | `Mer.S`, `Ura.RS` |
| Planetary hour | `mo.pln_hour` |
| Earlier in the zodiac | `SO.<.MO` |
| Body range or set | `SUN-PLU.0.SA`, `SO,MO,ME.Ari` |
| Operators | `&`, `\|`, `^`, with brackets |

`&` and `|` carry **equal precedence and run left to right**, which is what the
ZET specification states. Most languages bind AND tighter, and doing that here
would silently change the meaning of existing formulas.

A location is needed only for formulas mentioning houses or planetary hours.

### Orb systems

`orb_system` selects between them, defaulting to `moiety`.

- **moiety** — each body has its own orb and the pair allowance is the mean, so
  Sun and Moon give 13°30'. These are Lilly's own figures.
- **fixed** — the orb belongs to the aspect, from the ZET file: 9° for the
  luminaries and 8.5° for Mercury through Pluto on the majors, much tighter on
  the minors.

### A note on step size

A body counts as stationary for only about an hour, because the threshold is
0.0024°/day. A step coarser than roughly 30 minutes can stride straight over a
station and report nothing, so the response carries a warning when that is a
risk.

## GeoNames

City lookup uses [GeoNames](https://www.geonames.org/), which needs a free
account. Register, enable the free web services in the account settings, then
copy the template and fill it in:

```bash
cp .env.example .env
```

`.env` is gitignored and loaded automatically at startup. Real environment
variables take precedence over it, so on Render set `GEONAMES_USERNAME` under
Environment and no `.env` is needed there.

Without it the chart endpoint still works from coordinates; only city lookup is
affected.

## Rate limits

Counted per client over a trailing window, and returned as `429` with a
`Retry-After` header. `/health` is never limited, since Render polls it.

| Setting | Default | Protects |
|---|---|---|
| `RATE_LIMIT_CITIES_PER_MINUTE` | 20 | The GeoNames allowance |
| `RATE_LIMIT_CHART_PER_MINUTE` | 60 | Processor time |
| `GEONAMES_MAX_PER_HOUR` | 500 | The account quota, across every caller |

Set any of them to `0` to disable that limit. The GeoNames ceiling is counted
on actual upstream calls, so cached lookups cost nothing.

Counters are held in process memory, which suits a single instance. Running
several would need shared storage.

## Notes on time

Local time is converted using the daylight saving rules that applied on that
date, not today's. Two edge cases are reported rather than glossed over: a time
in the repeated hour when clocks go back is marked `ambiguous` and the
alternative UTC value is given, and a time in the hour that clocks skip forward
is marked `nonexistent`.

## Notes on accuracy

The `ephe/` directory holds Swiss Ephemeris data files covering 1800–2399, which
give sub-arcsecond agreement with ZET, plus `seorbel.txt`, the orbital
elements the Hamburg School bodies and Selene need. If those files are missing the library
falls back to its built-in Moshier theory, accurate to roughly one arcsecond;
the `ephemeris_source` field in every response says which was used.

A body counts as **stationary** when its longitudinal speed falls below
0.0024°/day. That figure comes from the client's own ZET output, where a planet
is marked stationary at about 8.78 arcseconds per day.

House cusps default to **Regiomontanus**, the traditional choice for horary.
Pass `house_system` to switch: `P` Placidus, `K` Koch, `C` Campanus, `W` Whole
Sign, and others listed by `GET /bodies`.

## Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests/ -q
```

Covers the ephemeris against known astronomy (the Sun reaching 0 Aries at the
March equinox), daylight saving edge cases, malformed responses from GeoNames,
and the rate limiting.

## Deployment

`render.yaml` configures a free Render web service. Connect the repository in
Render and it builds and deploys on every push. The health check path is
`/health`.

## Roadmap

| Milestone | Scope |
|---|---|
| 1 | Proof of concept — ephemeris integration *(done)* |
| 2 | GeoNames city lookup and UTC conversion *(done)* |
| 3 | Formula parser and time scanner *(done)* |
| 4 | API hardening, deployment, WordPress plugin |

Dual charts, stored natal charts and user databases are phase two.

## Licensing

Swiss Ephemeris is dual-licensed under the AGPL or a commercial licence from
Astrodienst. Confirm which applies before commercial launch.
