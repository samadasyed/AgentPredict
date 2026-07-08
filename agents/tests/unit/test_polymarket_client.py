"""
Unit tests for PolymarketClient parsing — no network.

The fight-event fixture mirrors the REAL Gamma /events?tag_slug=ufc shape
observed 2026-07 (UFC 329): event title "<card>: <A> vs. <B> (<info>)",
embedded markets with sportsMarketType, JSON-string outcomes/prices, and
gameStartTime in the "YYYY-MM-DD HH:MM:SS+00" space-separated form.
"""

from __future__ import annotations

import json
import time

from agents.polymarket.client import (
    _iso_to_ms,
    _parse_fight_event,
    _parse_market,
)

_NOW_MS = int(time.time() * 1000)
_HOUR_MS = 3_600_000


def _moneyline(cid: str = "0xc851", outcomes=("Max Holloway", "Conor McGregor"),
               prices=("0.665", "0.335"), closed: bool = False, **extra) -> dict:
    return {
        "conditionId": cid,
        "question": "UFC 329: Max Holloway vs. Conor McGregor (Welterweight, Main Card)",
        "sportsMarketType": "moneyline",
        "outcomes": json.dumps(list(outcomes)),
        "outcomePrices": json.dumps(list(prices)),
        "clobTokenIds": json.dumps([f"{cid}-t0", f"{cid}-t1"]),
        "closed": closed,
        "active": True,
        "gameStartTime": "2026-07-11 22:00:00+00",
        **extra,
    }


def _prop(question: str) -> dict:
    return {
        "conditionId": "0xprop",
        "question": question,
        "sportsMarketType": "ufc_method_of_victory",
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.54", "0.46"]),
        "clobTokenIds": json.dumps(["p0", "p1"]),
        "closed": False,
    }


def _fight_event(start_offset_ms: int = 72 * _HOUR_MS, **overrides) -> dict:
    start_iso = None  # use explicit startTime below
    ev = {
        "title": "UFC 329: Max Holloway vs. Conor McGregor (Welterweight, Main Card)",
        "slug": "ufc-max1-con-2026-07-11",
        "active": True,
        "closed": False,
        "volume": 1_464_663.0,
        "startTime": start_iso,
        "markets": [_prop("Will Max Holloway win by KO or TKO?"), _moneyline()],
    }
    ev.update(overrides)
    if ev.get("startTime") is None:
        # ISO with Z, like the real payload
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp((_NOW_MS + start_offset_ms) / 1000, tz=timezone.utc)
        ev["startTime"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ev


# ─── _iso_to_ms ───────────────────────────────────────────────────────────────

def test_iso_to_ms_handles_both_gamma_forms():
    from datetime import datetime, timezone
    expected = int(datetime(2026, 7, 11, 22, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert _iso_to_ms("2026-07-11T22:00:00Z") == expected
    # gameStartTime uses a space separator and short offset
    assert _iso_to_ms("2026-07-11 22:00:00+00") == expected

def test_iso_to_ms_garbage_is_zero():
    assert _iso_to_ms(None) == 0
    assert _iso_to_ms("") == 0
    assert _iso_to_ms("soon") == 0
    assert _iso_to_ms(12345) == 0


# ─── _parse_fight_event ───────────────────────────────────────────────────────

def test_fight_event_builds_moneyline_market_with_metadata():
    m = _parse_fight_event(_fight_event(), _NOW_MS)
    assert m is not None
    assert m.condition_id == "0xc851"
    assert m.title == "Max Holloway vs. Conor McGregor"
    assert m.card_title == "UFC 329"
    assert m.fight_info == "Welterweight · Main Card"
    assert m.volume == 1_464_663.0
    assert m.phase == "upcoming"
    assert m.event_start_ms > _NOW_MS
    # Primary outcome is fighter A with P(A); complement is fighter B.
    assert m.tokens[0].outcome == "Max Holloway"
    assert abs(m.tokens[0].price - 0.665) < 1e-9

def test_fight_event_started_is_live():
    m = _parse_fight_event(_fight_event(start_offset_ms=-30 * 60 * 1000), _NOW_MS)
    assert m is not None and m.phase == "live"

def test_fight_event_stale_leftover_dropped():
    # Started 3 days ago but market never closed (card change) → drop.
    assert _parse_fight_event(_fight_event(start_offset_ms=-72 * _HOUR_MS), _NOW_MS) is None

def test_fight_event_closed_moneyline_dropped():
    ev = _fight_event(markets=[_moneyline(closed=True)])
    assert _parse_fight_event(ev, _NOW_MS) is None

def test_futures_event_rejected():
    ev = _fight_event(title="Who will be UFC Heavyweight champion at the end of 2026?")
    assert _parse_fight_event(ev, _NOW_MS) is None

def test_who_fights_next_event_rejected():
    ev = _fight_event(title="UFC: Who will Charles Oliveira fight next?")
    assert _parse_fight_event(ev, _NOW_MS) is None

def test_fight_event_without_moneyline_rejected():
    ev = _fight_event(markets=[_prop("Fight to Go the Distance?")])
    assert _parse_fight_event(ev, _NOW_MS) is None


# ─── _parse_market (generic fallback path) ────────────────────────────────────

def test_parse_market_fallback_still_works():
    m = _parse_market(_moneyline())
    assert m is not None
    assert m.condition_id == "0xc851"
    assert m.tokens[0].outcome == "Max Holloway"
    assert m.phase in ("upcoming", "live")  # depends on now vs 2026-07-11
