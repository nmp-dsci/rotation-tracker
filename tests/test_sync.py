from contextlib import contextmanager
from typing import Any

import pytest

from rotation_tracker import pipeline, transcript_lab, youtube


class FakeCursor:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def execute(self, sql: str, params: Any = None) -> None:
        self.log.append(" ".join(sql.split())[:30])


class FakeCon:
    def __init__(self, picks: list[str]) -> None:
        self.picks = picks
        self.log: list[str] = []

    def execute(self, sql: str, params: Any = None) -> Any:
        class R:
            def fetchall(_s) -> list[tuple[str]]:
                return [(p,) for p in self.picks]

        return R()

    @contextmanager
    def cursor(self) -> Any:
        yield FakeCursor(self.log)

    def commit(self) -> None:
        pass


class FakeCorpus:
    def raw(self, vid: str) -> dict[str, Any]:
        return {"segments": [{"start_seconds": 0, "text": "synthetic words"}]}


def test_sync_skips_bot_checked_videos_and_reports_them(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcript_lab, "Corpus", FakeCorpus)

    def meta(vid: str, need_chapters: bool = False) -> dict[str, Any]:
        if vid == "blocked":
            raise youtube.BotCheck("sign in to confirm")
        return {"chapters": []}

    monkeypatch.setattr(youtube, "video_meta", meta)
    lines: list[str] = []
    res = pipeline.sync(FakeCon(["ok1", "blocked", "ok2"]), log=lines.append)  # type: ignore[arg-type]
    assert res["synced"] == 2
    assert res["skipped"] == ["blocked"]
    assert any("WARNING" in line and "blocked" in line for line in lines)
