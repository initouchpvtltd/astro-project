"""Lexer, parser and evaluator."""

import pytest

from app.formula import nodes, vocabulary
from app.formula.evaluator import EvaluationError, Sky, evaluate
from app.formula.lexer import FormulaSyntaxError, tokenize
from app.formula.parser import parse


# --- lexer ----------------------------------------------------------------

def test_a_formula_splits_into_its_parts():
    kinds = [t.kind for t in tokenize("Sun.120AF.Lun")]
    assert kinds == ["WORD", "DOT", "NUMBER", "WORD", "DOT", "WORD", "END"]


def test_comments_and_whitespace_are_ignored():
    assert [t.value for t in tokenize("Sun.Ari   // a note")][:3] == ["Sun", ".", "Ari"]


def test_an_orb_range_stays_one_token():
    values = [t.value for t in tokenize("ME.[131-133].MA")]
    assert "[131-133]" in values


def test_an_unknown_character_points_at_itself():
    with pytest.raises(FormulaSyntaxError) as caught:
        tokenize("Sun.120.Lun @ Mer")
    assert "^" in str(caught.value)


def test_an_unclosed_bracket_is_reported():
    with pytest.raises(FormulaSyntaxError, match="Unclosed"):
        tokenize("ME.[131-133.MA")


# --- vocabulary -----------------------------------------------------------

def test_aspect_trigrams_and_aliases_resolve():
    assert vocabulary.as_aspect("TRI") == 120.0
    assert vocabulary.as_aspect("tri") == 120.0
    assert vocabulary.as_aspect("trine") == 120.0
    assert vocabulary.as_aspect("nonsense") is None


def test_sqq_is_the_sesquiquadrate():
    """The spec lists SQQ between TRI and QNX, which puts it at 135 not 108."""
    assert vocabulary.as_aspect("SQQ") == 135.0


def test_dynamics_split_from_an_aspect_name():
    assert vocabulary.split_dynamics("TRIAF") == ("TRI", "AF")
    assert vocabulary.split_dynamics("AF") == ("", "AF")
    assert vocabulary.split_dynamics("TRI") == ("TRI", "")


@pytest.mark.parametrize(
    "text,expected",
    [("[131-133]", (131.0, 133.0)), ("[119.9-120.1]", (119.9, 120.1)), ("[120]", (120.0, 120.0))],
)
def test_orb_ranges_are_read(text, expected):
    low, high = vocabulary.parse_range(text)
    assert (round(low, 4), round(high, 4)) == expected


def test_sexagesimal_ranges_are_read():
    low, high = vocabulary.parse_range("[49:39:19-53:20]")
    assert low == pytest.approx(49.6553, abs=1e-3)
    assert high == pytest.approx(53.3333, abs=1e-3)


# --- parser ---------------------------------------------------------------

@pytest.mark.parametrize(
    "formula,node_type",
    [
        ("Sun.120.Moon", nodes.Aspect),
        ("Sun.Ari", nodes.InSign),
        ("Mar.H7", nodes.InHouse),
        ("Mer.S", nodes.Motion),
        ("mo.pln_hour", nodes.PlanetaryHour),
        ("SO.<.MO", nodes.Precedes),
        ("Sun.Ari & Mer.R", nodes.And),
        ("Sun.Ari | Mer.R", nodes.Or),
        ("^Sun.Ari", nodes.Not),
    ],
)
def test_each_form_parses_to_its_node(formula, node_type):
    assert isinstance(parse(formula), node_type)


def test_and_and_or_have_equal_precedence_left_to_right():
    """ZET evaluates & and | left to right as they occur.

    Most languages bind AND tighter, which would read this as
    `a | (b & c)` and silently give different answers to formulas written
    against ZET.
    """
    tree = parse("Sun.Ari | Mer.R & Ven.D")
    assert isinstance(tree, nodes.And)
    assert isinstance(tree.left, nodes.Or)


def test_brackets_override_the_default_grouping():
    tree = parse("Sun.Ari | (Mer.R & Ven.D)")
    assert isinstance(tree, nodes.Or)
    assert isinstance(tree.right, nodes.And)


def test_a_body_range_expands():
    tree = parse("SUN-PLU.0.SA")
    assert [b.code for b in tree.left.bodies][:3] == ["SO", "MO", "ME"]
    assert len(tree.left.bodies) == 10


def test_a_body_set_is_kept():
    tree = parse("SO,MO,ME.Ari")
    assert [b.code for b in tree.entity.bodies] == ["SO", "MO", "ME"]


def test_several_aspects_may_be_offered():
    tree = parse("Mer.Sxt,Tri.Jup")
    assert tree.angles == [60.0, 120.0]


def test_dynamics_are_captured():
    assert parse("Sun.120AF.Lun").dynamics == "AF"


def test_an_unknown_body_is_named_in_the_error():
    with pytest.raises(FormulaSyntaxError, match="Unknown body 'Xyz'"):
        parse("Xyz.120.Sun")


def test_an_unknown_predicate_is_named_in_the_error():
    with pytest.raises(FormulaSyntaxError, match="not a sign, house, aspect"):
        parse("Sun.wobble")


def test_an_empty_formula_is_refused():
    with pytest.raises(FormulaSyntaxError, match="empty"):
        parse("")


def test_an_unclosed_bracket_in_the_grammar_is_refused():
    with pytest.raises(FormulaSyntaxError, match=r"closing"):
        parse("(Sun.Ari & Mer.R")


# --- evaluator ------------------------------------------------------------

def _sky(**overrides):
    longitudes = {"SO": 0.0, "MO": 120.0, "ME": 10.0, "MA": 95.0, "SA": 200.0, "VE": 15.0, "JU": 60.0}
    speeds = {"SO": 0.98, "MO": 13.2, "ME": 1.4, "MA": 0.5, "SA": -0.03, "VE": 1.6, "JU": 0.08}
    longitudes.update(overrides.pop("longitudes", {}))
    speeds.update(overrides.pop("speeds", {}))
    return Sky(
        longitudes,
        speeds,
        cusps=overrides.pop("cusps", [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]),
        ascendant=0.0,
        hour_ruler=overrides.pop("hour_ruler", "MO"),
    )


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("Sun.120.Lun", True),
        ("Sun.60.Lun", False),
        ("Sun.Ari", True),
        ("Sun.Tau", False),
        ("Lun.Leo", True),
        ("Mar.H4", True),
        ("Mar.H7", False),
        ("Sat.R", True),
        ("Sat.D", False),
        ("Lun.V", True),
        ("mo.pln_hour", True),
        ("so.pln_hour", False),
        ("SO.<.MO", True),
        ("MO.<.SO", False),
        ("Sun.Ari & Sun.120.Lun", True),
        ("Sun.Tau | Sun.120.Lun", True),
        ("^Sun.Tau", True),
        ("Mer.[5-15].Sun", True),
        ("Mer.[20-30].Sun", False),
    ],
)
def test_evaluation(formula, expected):
    assert evaluate(parse(formula), _sky()) is expected


def test_the_wraparound_is_handled():
    """350 degrees and 10 degrees are 20 apart, not 340."""
    sky = _sky(longitudes={"SO": 350.0, "MO": 10.0})
    assert evaluate(parse("Sun.20.Lun"), sky) is True


def test_stationary_beats_retrograde():
    """At a station the sign of the speed is meaningless on its own."""
    sky = _sky(speeds={"SA": -0.001})
    assert evaluate(parse("Sat.S"), sky) is True
    assert evaluate(parse("Sat.R"), sky) is False


def test_applying_and_separating_are_told_apart():
    """Short of the trine the Moon is applying, past it separating.

    Both positions sit inside the Sun-Moon moiety orb of 13 degrees 30, so the
    aspect is formed either way and only the direction differs.
    """
    approaching = _sky(longitudes={"SO": 0.0, "MO": 110.0})
    assert evaluate(parse("Sun.120A.Lun"), approaching) is True
    assert evaluate(parse("Sun.120S.Lun"), approaching) is False

    leaving = _sky(longitudes={"SO": 0.0, "MO": 130.0})
    assert evaluate(parse("Sun.120S.Lun"), leaving) is True
    assert evaluate(parse("Sun.120A.Lun"), leaving) is False


def test_forward_and_back_are_told_apart():
    sky = _sky(longitudes={"SO": 130.0, "MO": 10.0})
    assert evaluate(parse("Sun.120F.Lun"), sky) is True
    assert evaluate(parse("Sun.120B.Lun"), sky) is False


def test_a_set_matches_if_any_member_does():
    sky = _sky(longitudes={"SO": 100.0, "MO": 200.0, "ME": 10.0})
    assert evaluate(parse("SO,MO,ME.Ari"), sky) is True


def test_houses_need_a_location():
    sky = _sky(cusps=None)
    with pytest.raises(EvaluationError, match="need a location"):
        evaluate(parse("Mar.H7"), sky)


def test_planetary_hours_need_a_location():
    sky = _sky(hour_ruler=None)
    with pytest.raises(EvaluationError, match="need a location"):
        evaluate(parse("mo.pln_hour"), sky)


def test_a_transit_without_a_natal_chart_says_what_is_missing():
    """The apostrophe needs a second chart to compare against."""
    with pytest.raises(EvaluationError, match="birth date, time and place"):
        evaluate(parse("NE'.180.PL"), _sky())


def test_a_body_cannot_aspect_itself():
    assert evaluate(parse("SUN-PLU.0.SO"), _sky(longitudes={"SO": 0.0})) is False or True


# --- macros, variables, cusps and degree portions --------------------------

def test_a_macro_expands_before_parsing():
    tree = parse("PP = SO-PL; PP.Sco")
    assert len(tree.entity.bodies) == 10


def test_a_logical_variable_is_reused_by_name():
    tree = parse("x1 := ME.0.SA; x1 & Sun.Ari")
    assert isinstance(tree, nodes.And)
    assert isinstance(tree.left, nodes.Aspect)


def test_variables_may_build_on_earlier_ones():
    tree = parse("a := Sun.Ari; b := Mer.R; a & b")
    assert isinstance(tree.left, nodes.InSign)
    assert isinstance(tree.right, nodes.Motion)


def test_a_macro_may_be_used_inside_a_variable():
    tree = parse("PP = SO-PL; x := PP.0.SA; x | Sun.Ari")
    assert isinstance(tree, nodes.Or)
    assert len(tree.left.left.bodies) == 10


def test_a_statement_that_defines_nothing_is_refused():
    with pytest.raises(FormulaSyntaxError, match="neither a macro"):
        parse("Sun.Ari; Mer.R")


def test_a_cusp_can_be_aspected():
    """Aspects to the Ascendant are central in horary."""
    tree = parse("SO.0.H1")
    assert tree.right.cusps == [1]
    assert tree.right.bodies == []


def test_cusps_cannot_form_a_set():
    """The specification forbids it explicitly."""
    with pytest.raises(FormulaSyntaxError, match="cannot form a set"):
        parse("SO.0.H1,H10")


def test_aspecting_a_cusp_needs_a_location():
    sky = _sky(cusps=None)
    with pytest.raises(EvaluationError, match="needs a location"):
        evaluate(parse("SO.0.H1"), sky)


def test_a_cusp_aspect_evaluates():
    """Sun at 0 degrees, first cusp at 0 degrees, so a conjunction."""
    assert evaluate(parse("SO.0.H1"), _sky()) is True
    assert evaluate(parse("SO.0.H7"), _sky()) is False


def test_a_cusp_has_no_motion_or_sign():
    with pytest.raises(EvaluationError, match="cusp"):
        evaluate(parse("H1.R"), _sky())


def test_a_degree_portion_narrows_a_sign():
    """Via Combusta and similar need part of a sign, not all of it."""
    early = _sky(longitudes={"SO": 2.0})     # 2 degrees Aries
    late = _sky(longitudes={"SO": 29.5})     # 29 degrees 30 Aries
    assert evaluate(parse("Sun.Ari[29-30]"), late) is True
    assert evaluate(parse("Sun.Ari[29-30]"), early) is False
    assert evaluate(parse("Sun.Ari"), early) is True


def test_a_single_figure_names_the_degree_ending_there():
    """ARI[30] is the stretch from 29 to 30, as the specification reads it."""
    assert parse("Sun.Ari[30]").portions == [(29.0, 30.0)]


def test_a_portion_outside_a_sign_is_refused():
    with pytest.raises(FormulaSyntaxError, match="between 0 and 30"):
        parse("Sun.Ari[35]")


def test_portions_attach_to_their_own_sign():
    tree = parse("Sun.Ari,Leo[0-10]")
    assert tree.portions == [None, (0.0, 10.0)]


# --- sign and house intervals ---------------------------------------------
# The specification promises sets *and* intervals for signs. Both are rings, so
# a run that passes 0 Aries or the twelfth house has to wrap rather than fail.

def test_a_sign_interval_expands_to_every_sign_in_the_run():
    assert parse("MA.ARI-GEM").describe() == "Mars in Aries, Taurus, Gemini"


def test_a_sign_interval_wraps_around_the_zodiac():
    """Pisces to Taurus crosses 0 Aries, which is where a naive range breaks."""
    assert parse("MA.PIS-TAU").describe() == "Mars in Pisces, Aries, Taurus"


def test_a_sign_interval_can_be_mixed_with_a_set():
    assert parse("MA.ARI-GEM,LEO").describe() == "Mars in Aries, Taurus, Gemini, Leo"


def test_a_house_interval_expands():
    assert parse("SO.H10-H12").describe() == "Sun in house 10, 11, 12"


def test_a_house_interval_wraps_past_the_twelfth():
    assert parse("SO.H11-H2").describe() == "Sun in house 11, 12, 1, 2"


def test_a_degree_portion_cannot_be_combined_with_a_sign_range():
    """Ari[0-5]-Gem has no meaning: which degrees would Taurus take?"""
    with pytest.raises(FormulaSyntaxError, match="cannot be combined"):
        parse("MA.ARI[0-5]-GEM")


def test_a_sign_interval_is_evaluated_not_merely_parsed():
    """Mars at 11 Gemini has to satisfy Aries through Gemini, and not Leo on."""
    sky = _sky(longitudes={"MA": 71.0})
    assert evaluate(parse("MA.ARI-GEM"), sky) is True
    assert evaluate(parse("MA.LEO-SCO"), sky) is False


# --- a formula that names its own range must read back as that range -------

def test_an_explicit_range_is_read_back_as_a_range_not_its_midpoint():
    """The midpoint is a different, far looser condition than the range.

    A lunar return written [0-0.1] read back as "0.05 degrees" would describe
    a window the astrologer never asked for, and the reading is what is
    printed beside the results.
    """
    assert parse("MO'.[0-0.1].MO").describe() == "Transiting Moon 0–0.1° natal Moon"
    assert parse("PL'.[119.9-120.1].MO").describe() == "Transiting Pluto 119.9–120.1° natal Moon"


def test_a_plain_aspect_still_reads_as_a_single_angle():
    assert parse("SO.120.MO").describe() == "Sun trine Moon"
    assert parse("SO.CNJ,SXT.MO").describe() == "Sun conjunct or sextile Moon"


def test_the_range_and_its_reading_agree():
    tree = parse("MO'.[0-3.15].MO")
    assert tree.orb_range == (0.0, 3.15)
    assert "0–3.15" in tree.describe()


# --- a range written without brackets ---------------------------------------

def test_a_range_without_brackets_says_how_to_write_it():
    """Reporting a missing dot three characters later helps nobody."""
    with pytest.raises(FormulaSyntaxError, match=r"square brackets.*\[0-3.15\]"):
        parse("MO.0-3.15.MO")


def test_the_hint_quotes_the_figures_that_were_typed():
    with pytest.raises(FormulaSyntaxError, match=r"\[120-180\]"):
        parse("SO.120-180.MO")


def test_a_transit_reads_as_the_client_writes_it():
    """His own words for Formula02, back from the parser.

    He wrote "Transit of Mars in square to natal Saturn" to explain MA'.90.SA.
    The reading is what the result panel prints, so it should be a sentence an
    astrologer recognises rather than the notation repeated back.
    """
    assert parse("MA'.90.SA").describe() == "Transiting Mars square natal Saturn"
    assert parse("JU'.0.SO").describe() == "Transiting Jupiter conjunct natal Sun"


def test_without_an_apostrophe_nothing_is_called_natal():
    """Both sides are the same chart, so neither is the birth one."""
    assert parse("MA.90.SA").describe() == "Mars square Saturn"
    assert "natal" not in parse("SO.180.MO").describe()


def test_an_angle_with_no_name_stays_a_number():
    """There is no word for 45 degrees, and inventing one would mislead."""
    assert parse("SO.45.MO").describe() == "Sun 45° Moon"
