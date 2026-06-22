"""
Unit tests for MMA agent — mocks HTTP client and gRPC emitter.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.mma.agent import MMAAgent, _event_matchup, _event_phase
from agents.mma.models import Event, Fight, Fighter, FightStat


def _fighter(fid: int, name: str) -> Fighter:
    return Fighter(id=fid, name=name)


def _make_fight(fight_id: int, status: str = "in_progress") -> Fight:
    return Fight(
        id=fight_id,
        status=status,
        fighter1=_fighter(10, "Alice Smith"),
        fighter2=_fighter(11, "Bob Jones"),
    )


def _make_event(event_id: int) -> Event:
    return Event(id=event_id, name=f"UFC {event_id}", date=date.today())


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_live_events.return_value = []
    client.get_fights.return_value = []
    client.get_fight_stats.return_value = []
    return client


@pytest.fixture
def mock_emitter():
    emitter = MagicMock()
    emitter.emit.return_value = True
    return emitter


@pytest.fixture
def agent(mock_client, mock_emitter):
    return MMAAgent(client=mock_client, emitter=mock_emitter)


@pytest.mark.asyncio
async def test_no_live_events_emits_nothing(agent, mock_emitter):
    await agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_no_fights_emits_nothing(agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = []
    await agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_new_fight_emits_fight_discovered(agent, mock_client, mock_emitter):
    """First time a fight is seen, FIGHT_DISCOVERED event is emitted."""
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101)]
    await agent._poll_once()
    mock_emitter.emit.assert_called_once()


@pytest.mark.asyncio
async def test_known_fight_not_re_emitted(agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101)]

    await agent._poll_once()
    mock_emitter.emit.reset_mock()

    await agent._poll_once()  # same fight again
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_fight_discovered_event_fields(agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(202)]
    await agent._poll_once()

    ev = mock_emitter.emit.call_args[0][0]
    from agents.generated import events_pb2  # type: ignore[import]
    assert ev.source == events_pb2.SOURCE_MMA
    assert ev.fight_event.fight_id == "202"
    assert ev.fight_event.stat_type == "FIGHT_DISCOVERED"
    assert ev.fight_event.fighter_name == "Alice Smith vs Bob Jones"


@pytest.mark.asyncio
async def test_multiple_fights_each_emitted_once(agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(301), _make_fight(302)]
    await agent._poll_once()
    assert mock_emitter.emit.call_count == 2


# ─── upcoming-card discovery (works without GOAT tier / /fights access) ────────


def _upcoming_event(eid: int, name: str, days_ahead: float) -> Event:
    start = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return Event(id=eid, name=name, date=start.date(), main_card_start_time=start)


def test_event_matchup_helper():
    assert _event_matchup("UFC 329: McGregor vs. Holloway 2") == "McGregor vs. Holloway 2"
    assert _event_matchup("UFC Fight Night") == "UFC Fight Night"


def test_event_phase_helper():
    now = 1_000_000_000_000
    assert _event_phase(now + 86_400_000, "scheduled", now) == "upcoming"
    assert _event_phase(now - 60_000, "scheduled", now) == "live"
    assert _event_phase(now - 60_000, "completed", now) == "final"


@pytest.mark.asyncio
async def test_poll_upcoming_emits_only_ufc_in_window(agent, mock_client, mock_emitter):
    mock_client.get_events.return_value = [
        _upcoming_event(10, "UFC 329: McGregor vs. Holloway 2", 5),
        _upcoming_event(11, "PFL Austin: Eblen vs. Kasanganay 2", 5),   # not UFC → filtered
        _upcoming_event(12, "UFC Fight Night: Far vs. Future", 999),    # beyond window → filtered
    ]
    await agent._poll_upcoming()

    upcoming = [
        c[0][0].fight_event for c in mock_emitter.emit.call_args_list
        if c[0][0].fight_event.stat_type == "FIGHT_UPCOMING"
    ]
    assert len(upcoming) == 1
    fe = upcoming[0]
    assert fe.fight_id == "10"
    assert fe.fighter_name == "McGregor vs. Holloway 2"
    assert fe.phase == "upcoming"
    assert fe.event_start > 0


@pytest.mark.asyncio
async def test_poll_upcoming_marks_started_card_live(agent, mock_client, mock_emitter):
    mock_client.get_events.return_value = [_upcoming_event(20, "UFC Live: A vs. B", -0.01)]
    await agent._poll_upcoming()
    fe = mock_emitter.emit.call_args[0][0].fight_event
    assert fe.stat_type == "FIGHT_UPCOMING"
    assert fe.phase == "live"


# ─── fight-stat polling (BALLDONTLIE_GOAT_TIER=1) ──────────────────────────────


def _make_fight_stat(fight_id: int, fighter_name: str, **kwargs) -> FightStat:
    return FightStat(fight_id=fight_id, fighter=_fighter(1, fighter_name), **kwargs)


@pytest.fixture
def goat_agent(mock_client, mock_emitter, monkeypatch):
    monkeypatch.setattr("agents.mma.agent._GOAT_TIER_ENABLED", True)
    return MMAAgent(client=mock_client, emitter=mock_emitter)


@pytest.mark.asyncio
async def test_goat_stat_change_emits_event(goat_agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101)]
    mock_client.get_fight_stats.return_value = [
        _make_fight_stat(101, "Alice Smith", significant_strikes_landed=5, takedowns_landed=1, knockdowns=0),
    ]

    await goat_agent._poll_once()

    stat_events = [
        call[0][0] for call in mock_emitter.emit.call_args_list
        if call[0][0].fight_event.stat_type != "FIGHT_DISCOVERED"
    ]
    assert len(stat_events) == 2
    assert {e.fight_event.stat_type for e in stat_events} == {"significant_strikes", "takedowns"}


@pytest.mark.asyncio
async def test_goat_no_change_no_emit(goat_agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101)]
    mock_client.get_fight_stats.return_value = [
        _make_fight_stat(101, "Alice Smith", significant_strikes_landed=5),
    ]

    await goat_agent._poll_once()
    mock_emitter.emit.reset_mock()

    await goat_agent._poll_once()  # identical stats
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_goat_finished_fight_stops_polling(goat_agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101, status="completed")]

    await goat_agent._poll_once()

    mock_client.get_fight_stats.assert_not_called()


@pytest.mark.asyncio
async def test_goat_empty_stats_emits_only_discovery(goat_agent, mock_client, mock_emitter):
    """A fight with no stats yet (e.g. not started) emits FIGHT_DISCOVERED only."""
    mock_client.get_live_events.return_value = [_make_event(1)]
    mock_client.get_fights.return_value = [_make_fight(101, status="scheduled")]
    mock_client.get_fight_stats.return_value = []

    await goat_agent._poll_once()

    assert mock_emitter.emit.call_count == 1
    assert mock_emitter.emit.call_args[0][0].fight_event.stat_type == "FIGHT_DISCOVERED"
