import json
from types import SimpleNamespace

import pytest

from api.routes import (
    _collect_exam_screenshot_paths,
    _exam_gaps_for_trade,
    _load_exam_analysis_snapshot,
    _normalize_exam_paths,
)


def test_normalize_exam_paths_dedupes_and_skips_empty():
    paths = _normalize_exam_paths(["a.png", "", None, "a.png", "b.png"])
    assert paths == ["a.png", "b.png"]


def test_exam_gaps_accepts_journal_evidence():
    trade = {
        "trade_summary": "Setup explicado en journal",
        "closed_at": "2026-04-27T10:00:00Z",
    }
    assert _exam_gaps_for_trade(trade, ["close.png"]) == []


def test_collect_exam_screenshot_paths_merges_generator_and_journal():
    engine = SimpleNamespace(
        screenshot_generator=SimpleNamespace(
            get_screenshot_path=lambda trade_id: [f"{trade_id}_open.png", f"{trade_id}_close.png"]
        )
    )
    trade = {"screenshots": ["manual_note.png", "abc_open.png"]}
    paths = _collect_exam_screenshot_paths(trade, engine, "abc")
    assert paths == ["abc_open.png", "abc_close.png", "manual_note.png"]


@pytest.mark.asyncio
async def test_load_exam_analysis_snapshot_parses_json():
    row = {
        "id": "trade-1",
        "instrument": "EUR_USD",
        "timestamp": "2026-04-27T10:00:00Z",
        "htf_trend": "bullish",
        "ltf_trend": "bullish",
        "convergence": 1,
        "score": 82.0,
        "strategy_detected": "BLUE_B",
        "explanation_json": json.dumps(
            {
                "analysis": {"htf_condition": "decelerating"},
                "explanation": {"strategy_detected": "BLUE_B"},
            }
        ),
    }

    class FakeCursor:
        async def fetchone(self):
            return row

    class FakeRawDB:
        async def execute(self, *_args, **_kwargs):
            return FakeCursor()

    fake_db = SimpleNamespace(_db=FakeRawDB())
    snapshot = await _load_exam_analysis_snapshot(fake_db, "trade-1")

    assert snapshot is not None
    assert snapshot["htf_trend"] == "bullish"
    assert snapshot["explanation_json"]["analysis"]["htf_condition"] == "decelerating"
