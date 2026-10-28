from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from rotation_tracker.pick import Pick, Upload, pick_weeks, window

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 27, tzinfo=UTC)


def ny(y: int, m: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=NY)


def one_week(uploads: list[Upload], friday: date) -> list[Pick]:
    return [p for p in pick_weeks(uploads, friday, NOW) if p.week_friday == friday]


FRI = date(2026, 10, 16)


def test_weekend_video_beats_the_weekday_recaps() -> None:
    ups = [
        Upload("tue", ny(2026, 10, 13, 22)),
        Upload("thu", ny(2026, 10, 15, 23)),
        Upload("sat", ny(2026, 10, 17, 23)),
    ]
    [p] = one_week(ups, FRI)
    assert (p.video_id, p.reason) == ("sat", "weekend")


def test_monday_before_the_open_belongs_to_the_week_before() -> None:
    ups = [Upload("thu", ny(2026, 10, 15, 23)), Upload("mon-early", ny(2026, 10, 19, 1, 15))]
    [p] = one_week(ups, FRI)
    assert (p.video_id, p.reason) == ("mon-early", "weekend")


def test_monday_after_the_open_starts_the_next_week() -> None:
    ups = [Upload("thu", ny(2026, 10, 15, 23)), Upload("mon-late", ny(2026, 10, 19, 10))]
    [p] = one_week(ups, FRI)
    assert p.video_id == "thu"


def test_no_weekend_video_falls_back_to_the_last_recap() -> None:
    ups = [Upload("wed", ny(2026, 10, 14, 22)), Upload("fri-noon", ny(2026, 10, 16, 12))]
    [p] = one_week(ups, FRI)
    assert (p.video_id, p.reason) == ("fri-noon", "fallback")


def test_friday_after_the_close_is_a_weekend_pick() -> None:
    [p] = one_week([Upload("fri-night", ny(2026, 10, 16, 21, 30))], FRI)
    assert p.reason == "weekend"


def test_streams_and_short_uploads_are_never_picked() -> None:
    ups = [
        Upload("recap", ny(2026, 10, 15, 23)),
        Upload("live", ny(2026, 10, 17, 20), tab="streams", live_status="was_live"),
        Upload("short", ny(2026, 10, 18, 20), duration_s=45),
    ]
    [p] = one_week(ups, FRI)
    assert p.video_id == "recap"


def test_daylight_saving_week_uses_new_york_wall_clock() -> None:
    # DST began Sun 10 Mar 2024. 03:00 UTC Mon 11 Mar is 23:00 EDT Sunday: still the weekend.
    sun_night = Upload("sun", datetime(2024, 3, 11, 3, 0, tzinfo=UTC))
    [p] = one_week([sun_night], date(2024, 3, 8))
    assert (p.video_id, p.reason) == ("sun", "weekend")
    start, end = window(date(2024, 3, 8))
    assert start.utcoffset() != end.utcoffset()


def test_an_empty_week_gets_no_pick_and_an_open_week_is_not_picked() -> None:
    ups = [Upload("a", ny(2026, 10, 3, 22)), Upload("b", ny(2026, 10, 24, 22))]
    picks = pick_weeks(ups, date(2026, 10, 2), NOW)
    assert [p.week_friday for p in picks] == [date(2026, 10, 2), date(2026, 10, 23)]
    # The week ending 30 Oct closes on Mon 2 Nov, after NOW.
    late = pick_weeks([Upload("c", ny(2026, 10, 26, 22))], date(2026, 10, 30), NOW)
    assert late == []


def test_first_friday_must_be_a_friday() -> None:
    with pytest.raises(ValueError):
        pick_weeks([], date(2026, 10, 15), NOW)


def test_undated_upload_holds_only_the_weeks_it_may_fall_in() -> None:
    from rotation_tracker.pick import undated_spans, undated_weeks

    listing = [
        ("new", ny(2026, 10, 24, 23)),
        ("mystery", None),
        ("old", ny(2026, 10, 10, 23)),
    ]
    held = undated_weeks(undated_spans(listing), date(2026, 10, 9), NOW)
    assert held == {
        date(2026, 10, 9): ["mystery"],
        date(2026, 10, 16): ["mystery"],
        date(2026, 10, 23): ["mystery"],
    }


def test_fully_dated_listing_holds_nothing() -> None:
    from rotation_tracker.pick import undated_spans, undated_weeks

    spans = undated_spans([("a", ny(2026, 10, 15, 23)), ("b", ny(2026, 10, 8, 23))])
    assert undated_weeks(spans, FRI, NOW) == {}
