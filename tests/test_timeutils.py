import pytest

from app.timeutils import TimeConversionError, convert, convert_with_offset


def test_summer_and_winter_offsets_differ_for_the_same_city():
    """Spain is two hours ahead in summer and one in winter."""
    summer = convert("2026-07-15", "12:00:00", "Europe/Madrid")
    winter = convert("2026-01-15", "12:00:00", "Europe/Madrid")
    assert summer["utc_offset"] == 2.0 and summer["dst_in_effect"] is True
    assert winter["utc_offset"] == 1.0 and winter["dst_in_effect"] is False


def test_ambiguous_hour_is_flagged_with_both_answers():
    """At the autumn change 02:30 happens twice in Madrid."""
    result = convert("2026-10-25", "02:30:00", "Europe/Madrid")
    assert result["ambiguous"] is True
    assert result["nonexistent"] is False
    assert result["alternative_utc"] != result["utc"]
    assert "occurred twice" in result["note"]


def test_nonexistent_hour_is_flagged_and_not_called_ambiguous():
    """At the spring change 02:30 never happens in Madrid.

    A skipped hour is not a repeated one. Python's fold changes the offset
    inside the gap too, so the two must be told apart deliberately.
    """
    result = convert("2026-03-29", "02:30:00", "Europe/Madrid")
    assert result["nonexistent"] is True
    assert result["ambiguous"] is False
    assert "never occurred" in result["note"]


def test_a_normal_time_is_neither_ambiguous_nor_missing():
    result = convert("2026-07-15", "12:00:00", "Europe/Madrid")
    assert result["ambiguous"] is False and result["nonexistent"] is False
    assert "note" not in result


@pytest.mark.parametrize(
    "zone,offset",
    [("Asia/Kolkata", 5.5), ("Asia/Kathmandu", 5.75), ("Asia/Karachi", 5.0)],
)
def test_fractional_hour_offsets(zone, offset):
    """India, Nepal and others are not on whole-hour offsets."""
    assert convert("2026-07-15", "12:00:00", zone)["utc_offset"] == offset


def test_historical_rules_apply_not_current_ones():
    """Britain used double summer time in 1947, two hours ahead of UTC.

    Applying today's rules to a historical date would put this an hour out,
    which is exactly the error that shifts a chart by fifteen degrees of the
    Ascendant.
    """
    assert convert("1947-06-15", "12:00:00", "Europe/London")["utc_offset"] == 2.0


def test_unknown_timezone_is_rejected_clearly():
    with pytest.raises(TimeConversionError, match="Unknown timezone"):
        convert("2026-07-15", "12:00:00", "Europe/Atlantis")


def test_malformed_time_is_rejected_clearly():
    with pytest.raises(TimeConversionError, match="Expected YYYY-MM-DD"):
        convert("15-07-2026", "12:00:00", "Europe/Madrid")


def test_explicit_offset_bypasses_timezone_rules():
    result = convert_with_offset("2026-07-15", "12:00:00", 5.0)
    assert result["utc"] == "2026-07-15T07:00:00Z"
    assert result["timezone"] is None


def test_explicit_offset_can_cross_midnight():
    result = convert_with_offset("2026-07-15", "00:30:00", 2.0)
    assert result["utc"] == "2026-07-14T22:30:00Z"
