"""A browsable front end for the API.

The JSON endpoints are the product, but JSON is a poor way to show an
astrologer what the service does. These pages render the same calls as a chart
and a list of dates, which is also the shape the WordPress plugin will take, so
the markup here is the prototype for that.

Server-rendered on purpose: no build step, no JavaScript framework, and the
whole thing drops into a WordPress shortcode with the styles intact.
"""

from datetime import datetime
from html import escape
import json
from functools import lru_cache
from urllib.parse import quote
from zoneinfo import available_timezones

from . import dignities as dig, glyphs, wheel
from .constants import BODIES, HOUSE_SYSTEMS, SIGNS

SIGN_INDEX = {name: index for index, name in enumerate(SIGNS)}


def body_glyph(code, size=18):
    """A body's drawn glyph, or its code where tradition gives it none.

    The Hamburg bodies and the asteroids have no settled symbol, so showing
    the two letters the formulas use is more useful than inventing one.
    """
    spec = glyphs.BODIES.get(code)
    if spec is None:
        return f'<span class="code">{escape(code)}</span>'
    return glyphs.inline(spec, size, "gl")


def sign_glyph(name, size=15):
    index = SIGN_INDEX.get(name)
    return "" if index is None else glyphs.inline(glyphs.SIGNS[index], size, "gl")


def aspect_glyph(name, size=16):
    return glyphs.inline(glyphs.ASPECTS[name], size, "gl")


STYLE = glyphs.STYLE + """
:root {
  --bg: #f6f4f1;
  --panel: #ffffff;
  --panel-2: #fbfaf8;
  --ink: #1c1917;
  --ink-soft: #44403c;
  --muted: #8a827b;
  --line: #e6e2dc;
  --line-soft: #f0ece6;
  --accent: #9a6a2f;
  --accent-soft: #f3e9db;
  --deep: #2b2440;
  --retro: #b23b2a;
  --station: #9a7b1f;
  --fire: #b8502c; --earth: #6b7148; --air: #2d6f93; --water: #216b63;
  --shadow: 0 1px 2px rgba(28,25,23,.05), 0 8px 24px -12px rgba(28,25,23,.12);
  --radius: 14px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #100e14;
    --panel: #1a1721;
    --panel-2: #211d2a;
    --ink: #ece8e3;
    --ink-soft: #c9c3bb;
    --muted: #8b8389;
    --line: #2b2634;
    --line-soft: #231f2c;
    --accent: #d2a05c;
    --accent-soft: #2a2231;
    --deep: #ded7ef;
    --retro: #e07a62;
    --station: #d6b65e;
    --fire: #d9734a; --earth: #9aa36a; --air: #6aa8cc; --water: #58a89c;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px -16px rgba(0,0,0,.6);
  }
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.6 ui-sans-serif, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  -webkit-font-smoothing: antialiased;
  padding: 0 16px 80px;
}




/* --- cards --- */
.formcard, .panel, .card, .strip, .recap {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow);
}
.formcard, .panel { padding: 20px 22px; margin-bottom: 18px; }
/* The search form is not a card, but what follows it still needs the
   same air as everywhere else: a submit button should not touch the
   results it produced. */
form { margin-bottom: 18px; }

/* --- fields --- */
.grid { display: grid; gap: 15px; grid-template-columns: repeat(12, 1fr); }
.f-2 { grid-column: span 2; } .f-3 { grid-column: span 3; }
.f-4 { grid-column: span 4; }
.f-6 { grid-column: span 6; } .f-12 { grid-column: span 12; }
@media (max-width: 860px) { .f-2 { grid-column: span 3; } }
@media (max-width: 680px) {
  .f-2, .f-3, .f-4, .f-6 { grid-column: span 6; }
}
@media (max-width: 420px) { .f-2, .f-3, .f-4, .f-6 { grid-column: span 12; } }

label {
  display: block; font-size: 11.5px; font-weight: 600; color: var(--muted);
  margin-bottom: 6px; letter-spacing: .03em; text-transform: uppercase;
}
.req { color: var(--accent); margin-left: 3px; font-weight: 700; }
/* Coordinates are the exception, not the rule: a reader wants a place name
   and only reaches for figures when the name is ambiguous. Folding them away
   keeps the form the length of the question it is really asking. */
/* Hidden from the eye but not from the keyboard, and taking no room:
   an absolutely positioned checkbox at full width lies across whatever
   is beneath it. */
/* A time zone you type at and pick from. The list hangs under the field,
   so it must sit above whatever follows it on the form. */
.combo { position: relative; }
.combo-list {
  position: absolute; z-index: 60; left: 0; right: 0; top: 100%;
  margin: 4px 0 0; padding: 4px; list-style: none; max-height: 272px;
  overflow-y: auto; background: var(--panel); border: 1px solid var(--line);
  border-radius: 9px; box-shadow: 0 10px 30px rgba(0,0,0,.16);
}
.combo-list li {
  padding: 7px 10px; border-radius: 6px; font-size: 14px; cursor: pointer;
  color: var(--ink); white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;
}
.combo-list li[aria-selected="true"], .combo-list li:hover {
  background: var(--accent-soft); color: var(--accent);
}
.combo-list .none { color: var(--muted); cursor: default; }
.combo-list .none:hover { background: transparent; color: var(--muted); }
.fold { position: absolute; width: 1px; height: 1px; margin: -1px;
  padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.fold:focus-visible + .fold-open { outline: 2px solid var(--accent);
  outline-offset: 3px; border-radius: 3px; }
.fold-open {
  /* Block-level, or the submit button comes up alongside it. */
  display: flex; align-items: center; gap: 7px; cursor: pointer;
  margin: 16px 0 0; font-size: 13px; color: var(--accent);
  /* It sits where a label would, so it inherits a label's shouting. */
  text-transform: none; letter-spacing: 0; font-weight: 500;
  border-bottom: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  padding-bottom: 2px; width: max-content;
  transition: border-color .14s;
}
.fold-open:hover { border-bottom-color: var(--accent); }
.fold-open::before { content: "+"; font-weight: 700; line-height: 1; }
.fold:checked ~ .fold-open::before { content: "−"; }
/* A date in the results is a door to that moment's chart. It should read as
   part of the table, not as the browser's idea of a hyperlink. */
td a {
  color: var(--accent); text-decoration: none;
  border-bottom: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
  padding-bottom: 1px; transition: border-color .14s, color .14s;
}
td a:hover { border-bottom-color: var(--accent); }
td a:visited { color: var(--accent); }
td a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px;
  border-radius: 3px; }
.fold ~ .folded { display: none; }
.fold:checked ~ .folded { display: grid; margin-top: 14px; }
/* The birth fields are required by the formula, not by the form: the star
   belongs there only once an apostrophe has asked for a natal chart. */
.req-natal { display: none; }
.wants-natal .req-natal { display: inline; }

.legend-req { text-transform: none; letter-spacing: 0; font-weight: 500; }
input, select {
  width: 100%; padding: 10px 12px; border: 1px solid var(--line);
  border-radius: 9px; background: var(--panel-2); color: var(--ink);
  font: inherit; transition: border-color .14s, box-shadow .14s;
}
input:focus, select:focus {
  outline: 0; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
input::placeholder { color: var(--muted); opacity: .7; }
select { appearance: none; cursor: pointer;
  background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%),
                    linear-gradient(135deg, var(--muted) 50%, transparent 50%);
  background-position: calc(100% - 17px) 50%, calc(100% - 12px) 50%;
  background-size: 5px 5px, 5px 5px; background-repeat: no-repeat;
  padding-right: 34px; }

button {
  margin-top: 20px; padding: 11px 28px; border: 0; border-radius: 9px;
  background: var(--accent); color: #fff; font: inherit; font-weight: 600;
  cursor: pointer; transition: filter .14s, transform .06s;
}
button:hover { filter: brightness(1.07); }
button:active { transform: translateY(1px); }

.legend {
  font: 600 11.5px/1 ui-sans-serif, sans-serif; letter-spacing: .07em;
  text-transform: uppercase; color: var(--muted);
  margin: 26px 0 14px; padding-top: 18px; border-top: 1px solid var(--line-soft);
}

/* --- results --- */
.result-head { margin-bottom: 18px; }
.formula {
  font: 600 20px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--ink); margin: 0 0 4px; word-break: break-all;
}
.reading { color: var(--accent); font-size: 14.5px; margin: 0 0 12px; }
.facts { display: flex; flex-wrap: wrap; gap: 8px; }
.fact {
  font-size: 12px; color: var(--muted); background: var(--panel-2);
  border: 1px solid var(--line-soft); border-radius: 20px; padding: 3px 11px;
}
.fact strong { color: var(--ink); font-weight: 600; }

table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th {
  text-align: left; font-size: 10.5px; text-transform: uppercase;
  letter-spacing: .07em; color: var(--muted); font-weight: 600;
  padding: 0 10px 10px; border-bottom: 1px solid var(--line);
}
td { padding: 9px 10px; border-bottom: 1px solid var(--line-soft); }
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background .12s; }
tbody tr:hover { background: var(--panel-2); }
.glyph { width: 26px; color: var(--accent); line-height: 0; }
.glyph .code { font: 600 10.5px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
               letter-spacing: .06em; color: var(--muted); }
.body-name { font-weight: 550; }
.pos { color: var(--ink-soft); }
.sign-mark { color: var(--accent); }
.num { text-align: right; color: var(--muted); font-size: 13px; }
.tag { font-size: 10px; font-weight: 700; letter-spacing: .06em;
       padding: 2px 7px; border-radius: 5px; }
.R { color: var(--retro); background: color-mix(in srgb, var(--retro) 12%, transparent); }
.tag.good { color: var(--accent); background: var(--accent-soft); }
.tag.bad { color: var(--retro); background: color-mix(in srgb, var(--retro) 12%, transparent); }
.legend-note { font-size: 12px; color: var(--muted); margin: 12px 0 0; line-height: 1.5; }
.profection { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.S { color: var(--station); background: color-mix(in srgb, var(--station) 14%, transparent); }
.idx { color: var(--muted); font-size: 12px; width: 34px; }

.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 0 32px; }
@media (max-width: 560px) { .cols { grid-template-columns: 1fr; } }

/* A phone has no room for the desktop's padding: without this the widest
   table pushes the whole page sideways. */
@media (max-width: 560px) {
  body { padding: 0 12px 60px; }
  form, .panel { padding: 16px; }
  table { font-size: 13px; }
  td, .chart-side td { padding: 7px 5px; }
  th, .chart-side th { padding: 0 5px 9px; }
  .glyph { width: 22px; font-size: 16px; }
  .num, .chart-side .num { font-size: 11.5px; }
  header { padding: 32px 0 20px; }
  h1 { font-size: 25px; }
}

.note {
  background: var(--accent-soft); border-left: 3px solid var(--accent);
  padding: 12px 16px; border-radius: 0 9px 9px 0; font-size: 13.5px;
  color: var(--ink-soft); margin-bottom: 18px;
}
.note.err {
  border-left-color: var(--retro);
  background: color-mix(in srgb, var(--retro) 9%, transparent);
}
.empty { color: var(--muted); font-size: 14px; text-align: center; padding: 28px 10px; }
/* The wheel is drawn light whatever the page does, the way a chart is
   printed, so its card is light too. */

/* --- masthead, for a page that is still only a form --------------------- */
header { padding: 40px 0 24px; text-align: center; }
header .mark { width: 42px; height: 42px; margin: 0 auto 14px; border-radius: 50%;
  border: 1.5px solid var(--accent); display: grid; place-items: center;
  color: var(--accent); }
h1 { font: 600 29px/1.2 ui-serif, Georgia, "Times New Roman", serif;
     letter-spacing: -0.015em; margin: 0 0 7px; }
.tagline { color: var(--muted); margin: 0; font-size: 14.5px; }
nav.tabs { display: flex; gap: 4px; justify-content: center; margin: 0 auto 26px;
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 4px; width: fit-content; box-shadow: var(--shadow); }
nav.tabs a { padding: 7px 20px; border-radius: 7px; text-decoration: none;
  color: var(--muted); font-size: 14px; font-weight: 550; transition: .14s; }
nav.tabs a:hover { color: var(--ink); }
nav.tabs a.on { background: var(--accent-soft); color: var(--accent); }

/* --- the shell ---------------------------------------------------------- */
.page { max-width: 1280px; margin: 0 auto; }
.nav { display: flex; align-items: center; justify-content: space-between;
       padding: 14px 0; gap: 14px; }
.brand { display: flex; align-items: center; gap: 9px; min-width: 0; }
.brand .mark { width: 26px; height: 26px; margin: 0; border-radius: 50%;
               border: 1.5px solid var(--accent); display: grid;
               place-items: center; color: var(--accent); flex: 0 0 auto; }
.brand b { font: 600 14.5px/1.2 ui-serif, Georgia, serif; }
.seg { display: flex; gap: 3px; background: var(--panel); flex: 0 0 auto;
       border: 1px solid var(--line); border-radius: 9px; padding: 3px; }
.seg a { padding: 6px 15px; border-radius: 7px; text-decoration: none;
         color: var(--muted); font-size: 12.5px; font-weight: 600; }
.seg a.on { background: var(--accent-soft); color: var(--accent); }

/* --- form --------------------------------------------------------------- */
.formcard input, .formcard select { height: 42px; padding: 0 12px; }
.recap { display: none; align-items: center; gap: 10px; padding: 13px 16px;
         margin-bottom: 18px; font-size: 13.5px; }
.recap .sep { color: var(--muted); }
.recap label { margin: 0 0 0 auto; text-transform: none; letter-spacing: 0;
               font-size: 12.5px; color: var(--accent); cursor: pointer;
               border: 1px solid var(--line); border-radius: 7px;
               padding: 5px 12px; white-space: nowrap; }
#edit, .page > input[type="radio"] {
  position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none;
}

/* --- title and the six facts -------------------------------------------- */
.title { display: flex; align-items: baseline; justify-content: space-between;
         gap: 20px; flex-wrap: wrap; margin: 18px 0 14px; }
.title h1 { font: 600 24px/1.2 ui-serif, Georgia, serif; margin: 0;
            letter-spacing: -.015em; }
.title .meta { color: var(--muted); font-size: 12.5px; }
.cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
         gap: 10px; }
.sum { background: var(--panel); border: 1px solid var(--line);
       border-radius: 12px; padding: 11px 13px; display: flex;
       flex-direction: column; gap: 3px; min-width: 0; }
.sum .k { font-size: 9.5px; font-weight: 650; letter-spacing: .08em;
          text-transform: uppercase; color: var(--muted); }
.sum .v { display: flex; align-items: center; gap: 7px; font-size: 14.5px;
          font-weight: 600; }
.sum .v i { font-style: normal; color: var(--accent); line-height: 0; }
.sum .s { font-size: 11px; color: var(--muted);
          font-variant-numeric: tabular-nums; }

/* --- the sticky bar: chart identity on the left, sections on the right --- */
.strip { position: sticky; top: 0; z-index: 30; padding: 12px 16px;
         margin-top: 16px; }
.row1 { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.row1 .asc { font: 600 19px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
             white-space: nowrap; }
.badge { font-size: 9.5px; font-weight: 700; letter-spacing: .09em;
         color: var(--accent); background: var(--accent-soft);
         border-radius: 5px; padding: 3px 7px; }
.row1 .mh { color: var(--accent); font-size: 12.5px; }
.pills { display: flex; gap: 4px; flex-wrap: wrap; margin-left: auto; }
.pills label { display: inline-flex; align-items: center; padding: 6px 12px;
               margin: 0; border: 1px solid transparent; border-radius: 9px;
               cursor: pointer; font-size: 12.5px; font-weight: 600;
               color: var(--muted); text-transform: none; letter-spacing: 0;
               transition: .14s; }
.pills label em { font-style: normal; font-size: 10.5px; opacity: .6;
                  margin-left: 6px; font-variant-numeric: tabular-nums; }
.pills label:hover { color: var(--ink); }
.strip .facts { margin-top: 9px; }

/* --- wheel beside the tables, and it stays put while they scroll -------- */
.work { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
        gap: 18px; align-items: start; padding-top: 16px; }
.card { padding: 16px 18px 18px; }
.card .cap { display: flex; align-items: center; justify-content: space-between;
             margin-bottom: 8px; }
.card .cap { padding-bottom: 10px; border-bottom: 1px solid var(--line-soft);
             margin-bottom: 14px; }
.card .cap h3 { font: 600 11.5px/1 ui-sans-serif, sans-serif; margin: 0;
                letter-spacing: .07em; text-transform: uppercase;
                color: var(--muted); }
.chartcard { position: sticky; top: 120px; }
/* The transit page has no sticky bar over it, so its wheel starts where the
   viewport does rather than below one that is not there. */
.chartcard.nobar { top: 16px; }
.wheel-wrap { box-shadow: none; background: transparent; border: 0; padding: 0; }
.work > .card > section > .legend:first-child { margin-top: 0; padding-top: 0;
                                                border-top: 0; }

/* Which section is showing. "All" leaves every one of them visible. */
#sec-pos:checked ~ .work [data-sec], #sec-asp:checked ~ .work [data-sec],
#sec-hou:checked ~ .work [data-sec], #sec-dig:checked ~ .work [data-sec],
#sec-lot:checked ~ .work [data-sec] { display: none; }
#sec-pos:checked ~ .work [data-sec="pos"],
#sec-asp:checked ~ .work [data-sec="asp"],
#sec-hou:checked ~ .work [data-sec="hou"],
#sec-dig:checked ~ .work [data-sec="dig"],
#sec-lot:checked ~ .work [data-sec="lot"] { display: block; }
#sec-all:checked ~ .strip [for="sec-all"], #sec-pos:checked ~ .strip [for="sec-pos"],
#sec-asp:checked ~ .strip [for="sec-asp"], #sec-hou:checked ~ .strip [for="sec-hou"],
#sec-dig:checked ~ .strip [for="sec-dig"], #sec-lot:checked ~ .strip [for="sec-lot"] {
  background: var(--accent-soft); color: var(--accent); border-color: var(--line);
}

@media (max-width: 940px) { .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) {
  .work { grid-template-columns: 1fr; }
  .chartcard, .strip { position: static; }
  .pills { margin-left: 0; margin-top: 10px; }
}
@media (max-width: 760px) {
  .recap { display: flex; }
  .formcard { display: none; }
  #edit:checked ~ .page .formcard { display: block; }
  #edit:checked ~ .page .recap { display: none; }
  .brand b { font-size: 13px; }
}
@media (max-width: 620px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }


/* Everything on one page, or one table at a time. The radios carry the state,
   so this costs no JavaScript and survives being pasted into WordPress. */
.asp { text-align: center; width: 26px; line-height: 0; }
td.asp-hard { color: var(--retro); }
td.asp-soft { color: var(--water); }
td.asp-conj { color: var(--muted); }
.reading-pair { color: var(--ink-soft); }
"""


# The client's own formulas. A demo that offers his working list explains the
# product far better than an empty box does.
PRESETS = [
    ("Mer.S", "Mercury stationary"),
    ("Sun.120.Moon", "Sun trine Moon"),
    ("Sun.120A.Moon", "Sun applying trine to Moon"),
    ("MoonVoid", "Moon void of course"),
    ("Mar.H7", "Mars in the 7th house"),
    ("mo.pln_hour", "Moon's planetary hour"),
    ("ME'.R", "Transiting Mercury retrograde"),
    ("MA'.90.SA", "Transiting Mars square natal Saturn"),
    ("JU'.0.SO", "Transiting Jupiter conjunct natal Sun"),
    ("PL'.[119.9-120.1].MO", "Transiting Pluto exact trine natal Moon"),
    ("MO'.[0-0.1].MO", "Lunar Return"),
    ("SA'.TAU[0-1]", "Transiting Saturn at 0-1 Taurus"),
    ("SO'.[0-0.1].H1", "Transiting Sun crossing the Ascendant"),
    ("UR'.RS", "Transiting Uranus stationary retrograde"),
    ("VE'.[0-0.1].H5", "Transiting Venus entering the natal 5th"),
]

# Typing a place name and getting its coordinates and timezone is the job of
# the /cities endpoint, so the field asks it as you type rather than making
# anyone remember a country code.
CITY_SCRIPT = """
<script>
const ZONES = __ZONES__;

function wireZones() {
  for (const field of document.querySelectorAll('input[data-zones]')) {
    const list = field.parentElement.querySelector('.combo-list');
    if (!list) continue;
    let at = -1;

    // The city, then the region. Typing "madrid" should not have to wade
    // through Europe/, and typing "eu" should not offer Australia/Eucla.
    const rank = (zone, q) => {
      const low = zone.toLowerCase();
      const city = low.slice(low.lastIndexOf('/') + 1).replace(/_/g, ' ');
      // The region first: someone typing "eu" is starting to write Europe,
      // and a single Australian township should not stand in front of a
      // continent. Then the city, which is what "madrid" means.
      if (low.startsWith(q)) return 0;
      if (city.startsWith(q)) return 1;
      if (city.includes(q)) return 2;
      if (low.includes(q)) return 3;
      return -1;
    };

    const close = () => {
      list.hidden = true;
      field.setAttribute('aria-expanded', 'false');
      at = -1;
    };

    const show = () => {
      const q = field.value.trim().toLowerCase().replace(/_/g, ' ');
      const found = (q ? ZONES
          .map(z => [rank(z, q), z])
          .filter(pair => pair[0] >= 0)
          .sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]))
          .map(pair => pair[1])
        : ZONES).slice(0, 60);

      list.innerHTML = '';
      if (!found.length) {
        const empty = document.createElement('li');
        empty.className = 'none';
        empty.textContent = 'No time zone matches that';
        list.appendChild(empty);
      }
      for (const zone of found) {
        const row = document.createElement('li');
        row.setAttribute('role', 'option');
        row.textContent = zone.startsWith('+') || zone.startsWith('-')
          ? (zone === '+0' ? 'UTC' : 'UTC' + zone) : zone;
        row.dataset.value = zone;
        row.addEventListener('mousedown', event => {
          event.preventDefault();
          field.value = zone;
          close();
        });
        list.appendChild(row);
      }
      list.scrollTop = 0;
      list.hidden = false;
      field.setAttribute('aria-expanded', 'true');
      at = -1;
    };

    const move = step => {
      const rows = [...list.querySelectorAll('li[role="option"]')];
      if (!rows.length) return;
      if (at >= 0) rows[at].removeAttribute('aria-selected');
      at = (at + step + rows.length) % rows.length;
      rows[at].setAttribute('aria-selected', 'true');
      rows[at].scrollIntoView({ block: 'nearest' });
    };

    field.addEventListener('focus', show);
    field.addEventListener('input', show);
    field.addEventListener('blur', () => setTimeout(close, 120));
    field.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') { event.preventDefault(); list.hidden ? show() : move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
      else if (event.key === 'Enter') {
        const rows = list.querySelectorAll('li[role="option"]');
        if (!list.hidden && at >= 0 && rows[at]) {
          event.preventDefault();
          field.value = rows[at].dataset.value;
          close();
        }
      } else if (event.key === 'Escape') { close(); }
    });
  }
}

function wireCity(input, list, hidden) {
  const field = document.getElementById(input);
  const datalist = document.getElementById(list);
  const code = document.getElementById(hidden);
  if (!field) return;
  let timer = null, matches = {};

  field.addEventListener('input', () => {
    const q = field.value.trim();
    if (matches[field.value]) { code.value = matches[field.value]; return; }
    clearTimeout(timer);
    if (q.length < 2) return;
    timer = setTimeout(async () => {
      try {
        const res = await fetch('/cities?q=' + encodeURIComponent(q) + '&limit=8');
        if (!res.ok) return;
        const data = await res.json();
        datalist.innerHTML = '';
        matches = {};
        for (const r of data.results) {
          const label = r.name + ', ' + r.country;
          matches[label] = r.country_code;
          const option = document.createElement('option');
          option.value = label;
          option.label = r.timezone;
          datalist.appendChild(option);
        }
      } catch (e) { /* the field still works as plain text */ }
    }, 250);
  });

  field.form.addEventListener('submit', () => {
    // Send just the place name; the country travels in its own field.
    const chosen = matches[field.value];
    if (chosen) { code.value = chosen; field.value = field.value.split(',')[0]; }
  });
}
</script>
"""


def _page_script():
    """The page's script, with the zone list folded into it.

    The list is built once and shared by every zone field on the page, rather
    than repeated per field the way a select would have to be.
    """
    return CITY_SCRIPT.replace("__ZONES__", _zone_names())



def page(title, body, tab="chart"):
    """The shell: the masthead, the two tabs, then whatever the caller built.

    The same header on every page, so moving between the form and a chart does
    not feel like moving between two different sites.
    """
    def tab_link(key, label):
        current = ' aria-current="page"' if key == tab else ""
        on = ' class="on"' if key == tab else ""
        return f'<a href="/view?tab={key}"{on}{current}>{escape(label)}</a>'

    mark = glyphs.inline(glyphs.BODIES["SO"], 21, "gl")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{STYLE}</style>
{_page_script()}
</head><body>
<input type="checkbox" id="edit">
<div class="page">
<header>
  <div class="mark gl">{mark}</div>
  <h1>Astrological Formula Search</h1>
  <p class="tagline">Search time for the moments a formula holds</p>
</header>
<nav class="tabs">{tab_link("chart", "Chart")}{tab_link("search", "Search")}</nav>
{body}
</div></body></html>"""


def _motion_tag(body):
    if body.get("stationary"):
        return '<span class="tag S">STATIONARY</span>'
    if body.get("retrograde"):
        return '<span class="tag R">R</span>'
    return ""


def chart_table(chart):
    rows = []
    for body in chart["bodies"]:
        if "error" in body:
            continue
        position = body["position"]
        rows.append(
            "<tr>"
            f'<td class="glyph">{body_glyph(body["code"])}</td>'
            f'<td class="body-name">{escape(body["name"])}</td>'
            f'<td class="pos">{position["degree_to_minute"]}&deg;'
            f'{position["minute_to_minute"]:02d}&prime; '
            f'<span class="sign-mark">{sign_glyph(position["sign_to_minute"])}</span> '
            f'{escape(position["sign_to_minute"])}</td>'
            f'<td class="num">{body["speed_deg_per_day"]:+.4f}&deg;</td>'
            f"<td>{_motion_tag(body)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th></th><th>Body</th><th>Position</th>"
        '<th class="num">Speed</th><th></th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def aspect_table(chart):
    """The aspects the wheel draws, written out.

    The same list feeds both, so a chord in the middle of the wheel and a row
    in this table can never disagree.
    """
    drawn = [
        body
        for body in chart["bodies"]
        if body.get("code") in wheel.DRAWN and "error" not in body
    ]
    aspects = wheel.aspects_between(drawn)
    if not aspects:
        return '<p class="empty">No aspects within orb.</p>'

    rows = []
    for aspect in aspects:
        first, second = aspect["first"], aspect["second"]
        rows.append(
            "<tr>"
            f'<td class="glyph">{body_glyph(first["code"], 17)}</td>'
            f'<td class="asp {aspect["class"]}">'
            f'{aspect_glyph(aspect["name"])}</td>'
            f'<td class="glyph">{body_glyph(second["code"], 17)}</td>'
            f'<td class="reading-pair">{escape(first["name"])} '
            f'{escape(aspect["name"])} {escape(second["name"])}</td>'
            f'<td class="num">{aspect["orb"]:.1f}&deg;</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th colspan=\"3\"></th><th>Aspect</th>"
        '<th class="num">Orb</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


DIGNITY_LABELS = {
    "domicile": "Domicile", "exaltation": "Exaltation", "triplicity": "Triplicity",
    "term": "Term", "face": "Face", "detriment": "Detriment", "fall": "Fall",
}


def dignity_table(chart):
    """Which planets are at home in the degrees they hold.

    The score is Lilly's, so one number says whether a planet can act for
    itself in a question or is a stranger borrowing another's house.
    """
    rows = []
    for body in chart["bodies"]:
        d = body.get("dignity")
        if not d:
            continue
        if d["dignities"]:
            marks = " ".join(
                f'<span class="tag {"bad" if n in ("detriment", "fall") else "good"}">'
                f"{DIGNITY_LABELS[n]}</span>"
                for n in d["dignities"]
            )
        else:
            marks = '<span class="tag">Peregrine</span>'
        rows.append(
            "<tr>"
            f'<td class="glyph">{body_glyph(body["code"])}</td>'
            f'<td class="body-name">{escape(body["name"])}</td>'
            f'<td class="pos">{body["position"]["degree_to_minute"]}&deg;'
            f'{body["position"]["minute_to_minute"]:02d}&prime; '
            f'<span class="sign-mark">{sign_glyph(body["position"]["sign_to_minute"])}</span></td>'
            f"<td>{marks}</td>"
            f'<td class="num">{d["score"]:+d}</td>'
            "</tr>"
        )
    return (
        '<table><thead><tr><th colspan="2">Body</th><th>Position</th>'
        '<th>Essential dignity</th><th class="num">Score</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        f'<p class="legend-note">{escape(chart.get("term_system", "egyptian").title())} '
        "terms, triplicity by sect. Scores are Lilly's: domicile +5, exaltation "
        "+4, triplicity +3, term +2, face +1, detriment &minus;5, fall &minus;4.</p>"
    )


def lots_table(chart):
    block = chart.get("lots")
    if not block:
        return '<p class="empty">No lots for this chart.</p>'
    rows = "".join(
        "<tr>"
        f'<td class="body-name">{escape(l["name"])}</td>'
        f'<td class="pos">{l["position"]["degree_to_minute"]}&deg;'
        f'{l["position"]["minute_to_minute"]:02d}&prime; '
        f'<span class="sign-mark">{sign_glyph(l["position"]["sign_to_minute"])}</span> '
        f'{escape(l["position"]["sign_to_minute"])}</td>'
        f'<td class="num">{escape(l["formula"])}</td>'
        "</tr>"
        for l in block["lots"]
    )
    return (
        '<table><thead><tr><th>Lot</th><th>Position</th>'
        '<th class="num">Taken from</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'<p class="legend-note">A {escape(block["sect"])} birth, so the arcs run '
        "that way round. Every lot reverses between day and night.</p>"
    )


def profection_block(chart):
    p = chart.get("profection")
    if not p:
        return ""
    return (
        '<div class="profection">'
        f'<span class="fact"><strong>Age {p["age"]}</strong></span>'
        f'<span class="fact">{_ordinal(p["house"])} house '
        f'&mdash; {escape(p["house_meaning"])}</span>'
        f'<span class="fact">{escape(p["sign"])}</span>'
        f'<span class="fact">Lord of the Year '
        f'<strong>{body_glyph(p["lord_of_the_year"], 15)}</strong></span>'
        f'<span class="fact">{escape(p["begins"])} &rarr; {escape(p["ends"])}</span>'
        "</div>"
    )


def houses_table(houses):
    left, right = [], []
    for cusp in houses["cusps"]:
        position = cusp["position"]
        cell = (
            f'<tr><td class="idx">{cusp["house"]}</td><td class="pos">'
            f'{position["degree_to_minute"]}&deg;{position["minute_to_minute"]:02d}&prime; '
            f'<span class="sign-mark">{sign_glyph(position["sign_to_minute"])}</span> '
            f'{escape(position["sign_to_minute"])}</td></tr>'
        )
        (left if cusp["house"] <= 6 else right).append(cell)
    return (
        '<div class="cols">'
        f'<table><tbody>{"".join(left)}</tbody></table>'
        f'<table><tbody>{"".join(right)}</tbody></table>'
        "</div>"
    )


ORDINALS = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else ORDINALS.get(n % 10, 'th')}"


def _card(label, glyph, value, detail):
    return (
        '<div class="sum">'
        f'<span class="k">{escape(label)}</span>'
        f'<span class="v"><i class="gl">{glyph}</i>{escape(value)}</span>'
        f'<span class="s">{detail}</span>'
        "</div>"
    )


def summary_cards(chart):
    """The six facts a traditional astrologer reads first.

    Sect and the Lord of the Year earn their place up here because they decide
    how everything below is judged: which planets are in favour, and which
    house the year is being read from.
    """
    houses, cards = chart["houses"], []
    for label, angle in (("Ascendant", "ascendant"), ("Midheaven", "midheaven")):
        place = houses[angle]["position"]
        cards.append(
            _card(label, sign_glyph(place["sign_to_minute"], 17),
                  place["sign_to_minute"],
                  f'{place["degree_to_minute"]}&deg;'
                  f'{place["minute_to_minute"]:02d}&prime;')
        )

    for label, code in (("Sun", "SO"), ("Moon", "MO")):
        body = next((b for b in chart["bodies"] if b.get("code") == code), None)
        # A body the ephemeris could not reach carries an error in place of a
        # position. The card is dropped rather than the page, and the note
        # below the form says which bodies are missing and why.
        if body is None or "error" in body:
            continue
        place = body["position"]
        cards.append(
            _card(label, sign_glyph(place["sign_to_minute"], 17),
                  place["sign_to_minute"],
                  f'{place["degree_to_minute"]}&deg;'
                  f'{place["minute_to_minute"]:02d}&prime;')
        )

    lots = chart.get("lots")
    if lots:
        day = lots["sect"] == "day"
        cards.append(
            _card("Sect", body_glyph("SO" if day else "MO", 17),
                  "Day" if day else "Night",
                  "Sun leads" if day else "Moon leads")
        )

    year = chart.get("profection")
    if year:
        lord = year["lord_of_the_year"]
        name = next(
            (b["name"] for b in chart["bodies"] if b.get("code") == lord), lord
        )
        cards.append(
            _card("Year lord", body_glyph(lord, 17), name,
                  f'Age {year["age"]} &middot; {_ordinal(year["house"])}')
        )

    return f'<div class="cards">{"".join(cards)}</div>'


def _coordinates(chart):
    """The place in degrees and minutes, the way a gazetteer prints it.

    Astro-Seek shows this beside the city, and the client reads the two pages
    side by side. Seconds appear only when there are any: a city resolves on
    the minute, so they would be three characters of nothing, but coordinates
    typed in by hand keep whatever precision they were given.
    """
    location = chart.get("location") or {}
    source = chart.get("input") or {}
    latitude = location.get("latitude", source.get("latitude"))
    longitude = location.get("longitude", source.get("longitude"))
    if latitude is None or longitude is None:
        return None

    def written(value, positive, negative):
        hemisphere = positive if value >= 0 else negative
        total = round(abs(value) * 3600.0)
        degree, rest = divmod(total, 3600)
        minute, second = divmod(rest, 60)
        tail = f"{second:02d}\u2033" if second else ""
        return f"{degree}\u00b0{minute:02d}\u2032{tail}{hemisphere}"

    return f'{written(latitude, "N", "S")}, {written(longitude, "E", "W")}'


def _when(chart):
    """The moment, written the way a person says it."""
    moment = chart.get("time") or {}
    try:
        when = datetime.strptime(
            f'{chart["input"]["date"]} {chart["input"]["time"][:5]}', "%Y-%m-%d %H:%M"
        )
        said = f"{when:%A}, {when.day} {when:%B %Y} &middot; {when:%H:%M} local"
    except (ValueError, KeyError):
        said = escape(f'{chart["input"]["date"]} {chart["input"]["time"][:5]}')

    parts = [said, f'({escape(chart["utc"][11:16])} UTC)']
    lots = chart.get("lots")
    if lots:
        parts.append(f'{lots["sect"].title()} birth')
    if moment.get("timezone"):
        parts.insert(1, escape(moment["timezone"]))
    return " &middot; ".join(parts)


def _missing_bodies(chart):
    """Say so when the ephemeris could not place something.

    A wheel with planets quietly absent is worse than no wheel: the shapes an
    astrologer reads are made as much by what is missing as by what is there,
    and nothing on the page would say Jupiter had been dropped.
    """
    absent = [b for b in chart["bodies"] if "error" in b]
    if not absent:
        return ""

    from .ephemeris import COMPLETE_FROM, COMPLETE_TO

    names = ", ".join(escape(b["name"]) for b in absent)
    reasons = sorted({b["error"] for b in absent})
    why = escape(reasons[0] if len(reasons) == 1 else "; ".join(reasons))
    plural = "is" if len(absent) == 1 else "are"
    return (
        f'<div class="note err">{names} {plural} not on this chart, because '
        f"{why} Every body is available for dates between "
        f"{COMPLETE_FROM} and {COMPLETE_TO}.</div>"
    )


def chart_page(chart, form_values):
    location = chart.get("location") or {}
    moment = chart.get("time") or {}
    houses = chart["houses"]
    # A chart cast from coordinates has no place name to head the page with,
    # so the coordinates themselves become the name. They then appear once,
    # not twice, which is why the strip below skips its own copy.
    placed = _coordinates(chart)
    named = location.get("name")
    where = named or placed or "Chart"

    facts = [
        f'<span class="fact"><strong>{escape(str(where))}</strong></span>',
    ]
    if placed and named:
        facts.append(f'<span class="fact">{escape(placed)}</span>')
    facts.append(
        f'<span class="fact">{escape(chart["input"]["date"])} '
        f'{escape(chart["input"]["time"][:5])}</span>'
    )
    if moment.get("timezone"):
        facts.append(
            f'<span class="fact">{escape(moment["timezone"])} '
            f'UTC{moment["utc_offset"]:+g}</span>'
        )
    facts.append(f'<span class="fact">{escape(chart["utc"])}</span>')

    recap = (
        f'<strong>{escape(chart["input"]["date"])} '
        f'{escape(chart["input"]["time"][:5])}</strong>'
        f'<span class="sep">&middot;</span>{escape(str(where))}'
    )
    note = f'<div class="note">{escape(moment["note"])}</div>' if moment.get("note") else ""
    note += _missing_bodies(chart)
    chooser, panels = _sections(chart)

    return (
        chart_form(form_values, recap=recap)
        + '<div class="title">'
        + f'<h1>{escape(str(where))}</h1>'
        + f'<div class="meta">{_when(chart)}</div>'
        + "</div>"
        + summary_cards(chart)
        + note
        + chooser
        + '<div class="strip">'
        + '<div class="row1">'
        + f'<span class="asc">{escape(houses["ascendant"]["position"]["formatted_to_minute"])}</span>'
        + '<span class="badge">ASC</span>'
        + f'<span class="mh">Midheaven '
        + f'{escape(houses["midheaven"]["position"]["formatted_to_minute"])} &middot; '
        + f'{escape(houses["system_name"])} houses</span>'
        + f'<div class="pills">{_pills(_counts(chart))}</div>'
        + "</div>"
        + f'<div class="facts">{"".join(facts)}</div>'
        + "</div>"
        + '<div class="work">'
        + '<div class="card chartcard">'
        + '<div class="cap"><h3>Chart wheel</h3></div>'
        + f'<div class="wheel-wrap">{wheel.render(chart)}</div>'
        + "</div>"
        + f'<div class="card">{panels}</div>'
        + "</div>"
    )


# Everything at once is the default, because a chart is usually read whole and
# because that is what prints. Anyone who would rather take one table at a time
# can, and the choice costs no page reload.
SECTIONS = (
    ("all", "All"),
    ("pos", "Positions"),
    ("asp", "Aspects"),
    ("hou", "Houses"),
    ("dig", "Dignities"),
    ("lot", "Lots"),
)


def _pills(counts=None):
    """The section switcher, each one carrying how much is behind it.

    The count is the point: it says whether a tab is worth opening before you
    open it, and "Aspects 12" reads very differently from "Aspects 0".
    """
    counts = counts or {}
    out = []
    for key, label in SECTIONS:
        n = counts.get(key)
        tally = "" if n is None else f"<em>{n}</em>"
        out.append(f'<label for="sec-{key}">{escape(label)}{tally}</label>')
    return "".join(out)


def _counts(chart):
    return {
        "pos": sum(1 for b in chart["bodies"] if "error" not in b),
        "asp": len(wheel.aspects_between([
            b for b in chart["bodies"]
            if b.get("code") in wheel.DRAWN and "error" not in b
        ])),
        "hou": len(chart["houses"]["cusps"]),
        "dig": sum(1 for b in chart["bodies"] if "dignity" in b),
        "lot": len((chart.get("lots") or {}).get("lots", [])),
    }


def _sections(chart):
    """The radios travel with the page, the panels sit in the right column.

    They are returned apart because the tabs belong in the sticky bar while
    what they switch is further down the page, and a CSS-only switch needs the
    radios to be siblings of both.
    """
    chooser = "".join(
        f'<input type="radio" name="section" id="sec-{key}"'
        f'{" checked" if key == "all" else ""}>'
        for key, _ in SECTIONS
    )
    panels = (
        f'<section data-sec="pos"><p class="legend">Positions</p>'
        f"{chart_table(chart)}</section>"
        f'<section data-sec="asp"><p class="legend">Aspects</p>'
        f"{aspect_table(chart)}</section>"
        f'<section data-sec="hou"><p class="legend">House cusps</p>'
        f'{houses_table(chart["houses"])}</section>'
        f'<section data-sec="dig"><p class="legend">Essential dignities</p>'
        f"{dignity_table(chart)}</section>"
        f'<section data-sec="lot"><p class="legend">Profected year</p>'
        f"{profection_block(chart)}"
        f'<p class="legend">The seven Hermetic Lots</p>'
        f"{lots_table(chart)}</section>"
    )
    return chooser, panels


def _options(selected):
    return "".join(
        f'<option value="{key}"{" selected" if key == selected else ""}>{escape(name)}</option>'
        for key, name in HOUSE_SYSTEMS.items()
    )


def _label(text, required=False):
    """A field label, marked when the form will not submit without it."""
    if required == "natal":
        star = '<span class="req req-natal" aria-hidden="true">*</span>'
    elif required:
        star = '<span class="req" aria-hidden="true">*</span>'
    else:
        star = ""
    return f'<label>{escape(text)}{star}</label>'


@lru_cache(maxsize=1)
def _zone_names():
    """Canonical IANA zones, as a JSON array for the browser to filter.

    Deprecated aliases such as US/Eastern are left out, so one place does not
    appear under three spellings. Sent once and shared by every zone field.
    """
    regions = (
        "Africa/", "America/", "Antarctica/", "Arctic/", "Asia/", "Atlantic/",
        "Australia/", "Europe/", "Indian/", "Pacific/",
    )
    names = sorted(z for z in available_timezones() if z.startswith(regions))
    offsets = [f"{q / 4:+g}" for q in range(-48, 57)]
    return json.dumps(offsets + names)


def _zone_field(label, name, value, span="f-4"):
    """A time zone you type at and pick from.

    Neither a plain select nor a datalist does this job. A select of four
    hundred names is a scroll, and a datalist matches anywhere in the string,
    so "eu" offered Africa/Ceuta and Australia/Eucla before Europe. This
    filters on the city and the region, in that order.

    Without JavaScript it stays a text box, and a text box is all the field
    ever needed: the server reads a zone name or an offset either way.
    """
    return f'''
    <div class="{span} combo"><label>{escape(label)}</label>
      <input name="{name}" value="{escape(str(value or ""))}" autocomplete="off"
             role="combobox" aria-expanded="false" aria-autocomplete="list"
             data-zones="1" placeholder="Type to search, or +2">
      <ul class="combo-list" role="listbox" hidden></ul></div>'''


def _city_field(label, name, value, span="f-4", hint="Start typing\u2026", required=False):
    """A place name that looks itself up as you type."""
    list_id = f"{name}-list"
    return f'''
    <div class="{span}">{_label(label, required)}
      <input id="{name}" name="{name}" value="{escape(str(value or ""))}"
             list="{list_id}" autocomplete="off" placeholder="{escape(hint)}">
      <datalist id="{list_id}"></datalist>
      <input type="hidden" id="{name}-code" name="{name}_country" value="">
    </div>'''


def chart_form(values=None, recap=None):
    """The birth data, on one row.

    Each field gets room in proportion to what it holds, so a place name and a
    house system are not squeezed to the same width as a time. On a phone the
    five fields become five full rows, which is a wall in front of the chart,
    so once there is a chart to show they collapse to the single line in
    `recap` with an Edit control.
    """
    values = values or {}

    def value(name, fallback=""):
        return escape(str(values.get(name) or fallback))

    line = (
        f'<div class="recap">{recap}<label for="edit">Edit</label></div>'
        if recap else ""
    )
    # Folded away unless the reader already reached for it: a form that comes
    # back with coordinates in it should not hide them.
    open_coords = " checked" if any(
        values.get(k) for k in ("latitude", "longitude", "tz")
    ) else ""
    return f"""{line}
<form class="formcard" method="get" action="/view/chart">
  <div class="grid">
    <div class="f-3">{_label("Date", True)}
      <input type="date" name="date" value="{value('date', '2026-07-15')}"></div>
    <div class="f-3">{_label("Time", True)}
      <input type="time" name="time" value="{value('time', '12:00')}"></div>
    {_city_field("Place", "city", values.get("city") or "Barcelona", "f-3", required=True)}
    <div class="f-3"><label>House system</label>
      <select name="house_system">{_options(values.get('house_system', 'R'))}</select></div>
  </div>

  <input type="checkbox" id="chart-coords" class="fold"{open_coords}>
  <label for="chart-coords" class="fold-open">Enter coordinates instead of a place</label>
  <div class="grid folded">
    <div class="f-4"><label>Latitude</label>
      <input name="latitude" value="{value('latitude')}"
             placeholder="41.3833 or 41&deg;23&prime;N" autocomplete="off"></div>
    <div class="f-4"><label>Longitude</label>
      <input name="longitude" value="{value('longitude')}"
             placeholder="2.1667 or 2&deg;10&prime;E" autocomplete="off"></div>
    {_zone_field("Time zone", "tz", values.get("tz"))}
  </div>
  <button type="submit">Calculate chart</button>
</form>
<script>wireCity('city', 'city-list', 'city-code'); wireZones();</script>
"""


def _preset_options(current):
    options = ['<option value="">Choose one, or type your own below</option>']
    for formula, description in PRESETS:
        selected = " selected" if formula == current else ""
        options.append(
            f'<option value="{escape(formula)}"{selected}>'
            f"{escape(formula)} &mdash; {escape(description)}</option>"
        )
    return "".join(options)


def search_form(values=None):
    values = values or {}

    def value(name, fallback=""):
        return escape(str(values.get(name) or fallback))

    wants_natal = "'" in str(values.get("formula") or "")
    # Each pair of coordinate fields stays folded until it has something in
    # it, so the form is the length of the question and not of its options.
    open_here = " checked" if any(
        values.get(k) for k in ("latitude", "longitude", "tz")
    ) else ""
    open_born = " checked" if any(
        values.get(k) for k in ("natal_latitude", "natal_longitude", "natal_tz")
    ) else ""

    return f"""
<form method="get" action="/view/search" id="searchform"
      class="{'wants-natal' if wants_natal else ''}">
  <div class="grid">
    <div class="f-12"><label>Choose a formula</label>
      <select id="preset" onchange="document.getElementById('formula').value=this.value">
        {_preset_options(values.get('formula'))}
      </select></div>
    <div class="f-6">{_label("Or write your own", True)}
      <input id="formula" name="formula" value="{value('formula', 'Mer.S')}"
             placeholder="Sun.120.Moon"></div>
    <div class="f-3">{_label("From", True)}
      <input type="date" name="start" value="{value('start', '2027-01-01')}"></div>
    <div class="f-3">{_label("To", True)}
      <input type="date" name="end" value="{value('end', '2027-12-31')}"></div>
    <div class="f-4"><label>Precision</label>
      <select name="step_seconds">{_step_options(values.get('step_seconds', '900'))}</select></div>
    {_city_field("Place (houses or hours)", "city", values.get("city"), "f-4", "Optional")}
    <div class="f-4"><label>Orbs</label>
      <select name="orb_system">
        <option value="moiety">Moiety &mdash; traditional</option>
        <option value="fixed"{' selected' if values.get('orb_system') == 'fixed' else ''}>Fixed &mdash; from your ZET file</option>
      </select></div>
  </div>

  <input type="checkbox" id="search-coords" class="fold"{open_here}>
  <label for="search-coords" class="fold-open">Enter coordinates instead of a place</label>
  <div class="grid folded">
    <div class="f-4"><label>Latitude</label>
      <input name="latitude" value="{value('latitude')}"
             placeholder="41.3833 or 41&deg;23&prime;N" autocomplete="off"></div>
    <div class="f-4"><label>Longitude</label>
      <input name="longitude" value="{value('longitude')}"
             placeholder="2.1667 or 2&deg;10&prime;E" autocomplete="off"></div>
    {_zone_field("Time zone", "tz", values.get("tz"))}
  </div>

  <p class="legend">Natal chart<span class="legend-req"> &mdash; a date, a time and a
     place, needed for formulas with an apostrophe</span></p>
  <div class="grid">
    <div class="f-4"><label>Birth date<span class="req req-natal" aria-hidden="true">*</span></label>
      <input type="date" name="natal_date" value="{value('natal_date')}"></div>
    <div class="f-4"><label>Birth time<span class="req req-natal" aria-hidden="true">*</span></label>
      <input type="time" name="natal_time" value="{value('natal_time')}"></div>
    {_city_field("Birth place", "natal_city", values.get("natal_city"), "f-4",
                 required="natal")}
  </div>
  <input type="checkbox" id="natal-coords" class="fold"{open_born}>
  <label for="natal-coords" class="fold-open">Enter birth coordinates instead of a place</label>
  <div class="grid folded">
    <div class="f-4"><label>Birth latitude</label>
      <input name="natal_latitude" value="{value('natal_latitude')}"
             placeholder="41.3833 or 41&deg;23&prime;N" autocomplete="off"></div>
    <div class="f-4"><label>Birth longitude</label>
      <input name="natal_longitude" value="{value('natal_longitude')}"
             placeholder="2.1667 or 2&deg;10&prime;E" autocomplete="off"></div>
    {_zone_field("Birth time zone", "natal_tz", values.get("natal_tz"))}
  </div>
  <button type="submit">Search</button>
</form>
<script>
  wireCity('city', 'city-list', 'city-code');
  wireCity('natal_city', 'natal_city-list', 'natal_city-code');
  wireZones();
  (function () {{
    var form = document.getElementById('searchform');
    var written = document.getElementById('formula');
    var chosen = document.getElementById('preset');
    function mark() {{
      form.classList.toggle('wants-natal', written.value.indexOf("'") !== -1);
    }}
    written.addEventListener('input', mark);
    chosen.addEventListener('change', mark);
    mark();
  }})();
</script>
"""


def _step_options(current):
    choices = [
        ("300", "5 minutes \u2014 finest"),
        ("900", "15 minutes \u2014 catches stations"),
        ("3600", "1 hour"),
        ("21600", "6 hours"),
        ("86400", "1 day \u2014 fastest"),
    ]
    return "".join(
        f'<option value="{v}"{" selected" if str(current) == v else ""}>{label}</option>'
        for v, label in choices
    )


def _natal_query(values):
    """The birth details as a query string, for linking a moment to its chart."""
    values = values or {}
    carried = {
        "natal_date": values.get("natal_date"),
        "natal_time": values.get("natal_time"),
        "natal_city": values.get("natal_city"),
        "natal_city_country": values.get("natal_country"),
        "natal_latitude": values.get("natal_latitude"),
        "natal_longitude": values.get("natal_longitude"),
        "natal_tz": values.get("natal_tz"),
    }
    if not (carried["natal_date"] and carried["natal_time"]):
        return None
    return "&amp;".join(
        f"{key}={quote(str(value))}" for key, value in carried.items() if value
    )


def search_page(result, form_values):
    warnings = "".join(
        f'<div class="note">{escape(w)}</div>' for w in result.get("warnings", [])
    )

    # A formula with an apostrophe was measured against a birth chart, so each
    # moment it found can be drawn around that chart. Without one there is
    # nothing to draw a transit against, and the dates stay plain text.
    born = _natal_query(form_values) if result.get("natal_chart") else None

    if result["intervals"]:
        def began(moment):
            shown = escape(moment[:16].replace("T", " "))
            if not born:
                return shown
            return (
                f'<a href="/view/transits?moment={quote(moment)}&amp;{born}">'
                f"{shown}</a>"
            )

        rows = "".join(
            f'<tr><td class="idx">{n}</td>'
            f'<td class="pos">{began(i["begin"])}</td>'
            f'<td class="pos">{escape(i["end"][:16].replace("T", " "))}</td>'
            f'<td class="num">{i["duration_hours"]:g} h</td></tr>'
            for n, i in enumerate(result["intervals"], 1)
        )
        head = (
            '<th>Begins (UTC)</th>' if not born
            else '<th>Begins (UTC) &mdash; open the chart</th>'
        )
        table = (
            f'<table><thead><tr><th class="idx">#</th>{head}'
            '<th>Ends (UTC)</th><th class="num">Length</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
    else:
        table = (
            '<p class="empty">Nothing found in this range.<br>'
            "That is often the right answer: a slow body may simply not form "
            "the aspect during the period you asked about.</p>"
        )

    facts = [
        f'<span class="fact"><strong>{result["found"]}</strong> found</span>',
        f'<span class="fact">{result["steps_evaluated"]:,} steps</span>',
        f'<span class="fact">{escape(result["orb_system"])} orbs</span>',
    ]
    if result.get("natal_chart"):
        facts.append(
            f'<span class="fact">natal {escape(result["natal_chart"][:10])}</span>'
        )

    return (
        search_form(form_values)
        + '<div class="panel">'
        + '<div class="result-head">'
        + f'<p class="formula">{escape(result["formula"])}</p>'
        + f'<p class="reading">{escape(result["reading"])}</p>'
        + f'<div class="facts">{"".join(facts)}</div>'
        + "</div>"
        + warnings
        + table
        + "</div>"
    )


def error_panel(message):
    return f'<div class="note err">{escape(str(message))}</div>'


def transits_page(natal, moving, moment, submitted=None):
    """The bi-wheel for one moment, with the aspects it makes to the birth chart.

    Reached from a row of search results: a formula with an apostrophe names a
    moment, and this is what that moment looks like against the chart it was
    measured from.
    """
    from . import wheel

    crossings = wheel.crossing_aspects(
        wheel._for_wheel(moving), wheel._for_wheel(natal)
    )
    born = natal.get("location") or {}
    placed = _coordinates(natal)
    named = born.get("name")
    where = named or placed or "the birth chart"

    rows = "".join(
        f'<tr><td>{body_glyph(a["moving"]["code"])} '
        f'{escape(a["moving"]["name"])}</td>'
        f'<td class="pos">{aspect_glyph(a["name"])} {escape(a["name"])}</td>'
        f'<td>{body_glyph(a["natal"]["code"])} '
        f'{escape(a["natal"]["name"])}</td>'
        f'<td class="num">{a["orb"]:.2f}&deg;</td></tr>'
        for a in crossings
    )
    table = (
        '<table><thead><tr><th>Transiting</th><th>Aspect</th>'
        '<th>Natal</th><th class="num">Orb</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        if crossings else
        '<p class="empty">Nothing within orb of the birth chart at this moment.</p>'
    )

    facts = [f'<span class="fact"><strong>{escape(str(where))}</strong></span>']
    # Where the chart was cast from, the same way the chart page shows it. A
    # transit is read against the natal houses, and those are the birth place's.
    if placed and named:
        facts.append(f'<span class="fact">{escape(placed)}</span>')
    facts += [
        f'<span class="fact">born {escape(natal["input"]["date"])} '
        f'{escape(natal["input"]["time"][:5])}</span>',
        f'<span class="fact">{escape(moment[:16].replace("T", " "))} UTC</span>',
        f'<span class="fact">{len(crossings)} aspects</span>',
    ]

    # Either chart can be short of a body, and a bi-wheel hides that even
    # better than a single one does: a ring with two planets in it looks
    # deliberate.
    absent = _missing_bodies(natal) + _missing_bodies(moving)

    return (
        '<div class="title">'
        f'<h1>Transits</h1>'
        f'<div class="meta">The sky of {escape(moment[:16].replace("T", " "))} UTC '
        f'around the chart for {escape(str(where))}</div>'
        "</div>"
        + f'<div class="facts">{"".join(facts)}</div>'
        + absent
        + '<div class="work">'
        + '<div class="card chartcard nobar"><div class="cap"><h3>Chart wheel</h3>'
        + '<span class="hint">natal inside, transits outside</span></div>'
        + wheel.render_transits(natal, moving)
        + "</div>"
        + '<div class="card"><div class="cap"><h3>Aspects to the birth chart</h3>'
        + f'<span class="hint">{len(crossings)}</span></div>'
        + table
        + "</div></div>"
    )
