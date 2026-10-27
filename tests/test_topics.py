import pytest

from rotation_tracker.topics import cut, tag

# Real chapter titles from the videos checked for the s00 plan.
CASES = [
    ("Market week overview", "macro-flows"),
    ("Sector rotation and flows", "macro-flows"),
    ("Institutional vs retail flows", "macro-flows"),
    ("Sector shifts and earnings", "macro-flows"),
    ("Defensive rotation strategy", "macro-flows"),
    ("Bond market and debt risks", "macro-flows"),
    ("Yields, dollar, and small caps", "macro-flows"),
    ("Upcoming earnings schedule", "macro-flows"),
    ("Market conclusion and outlook", "macro-flows"),
    ("Technical chart analysis", "technicals"),
    ("Market index levels", "technicals"),
    ("S&P 500 levels and options", "technicals"),
    ("Trading levels for top stocks", "technicals"),
    ("Tech and semiconductor charts", "technicals"),
    ("Crypto and market technicals", "technicals"),
    ("SP 500", "technicals"),
    ("QQQ", "technicals"),
    ("Tiger Brokers", "promo"),
    ("Pause Screen", "promo"),
    ("Closing and live event", "promo"),
    ("Channel update and request", "promo"),
    ("Intro", "intro-outro"),
    ("Outro", "intro-outro"),
    ("", "untagged"),
    (None, "untagged"),
]


@pytest.mark.parametrize(("title", "topic"), CASES)
def test_tag(title: str | None, topic: str) -> None:
    assert tag(title) == topic


SEGMENTS = [
    {"start_seconds": 0.0, "end_seconds": 5.0, "text": "welcome back"},
    {"start_seconds": 12.0, "end_seconds": 20.0, "text": "money is leaving software"},
    {"start_seconds": 61.0, "end_seconds": 70.0, "text": "support at 6,500"},
]


def test_cut_assigns_segments_to_the_chapter_they_start_in() -> None:
    chapters = [
        {"start_time": 0, "end_time": 10, "title": "Intro"},
        {"start_time": 10, "end_time": 60, "title": "Sector rotation and flows"},
        {"start_time": 60, "end_time": 90, "title": "Technical chart analysis"},
    ]
    secs = cut(SEGMENTS, chapters)
    assert [(s.topic, s.text) for s in secs] == [
        ("intro-outro", "welcome back"),
        ("macro-flows", "money is leaving software"),
        ("technicals", "support at 6,500"),
    ]


def test_cut_without_chapters_is_one_untagged_section() -> None:
    [s] = cut(SEGMENTS, [])
    assert s.topic == "untagged"
    assert s.text == "welcome back money is leaving software support at 6,500"
    assert s.end_s == 70.0
