"""
Unit tests for MMA agent — mocks HTTP client and gRPC emitter.
"""

from __future__ import annotations

from datetime import date

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.mma.agent import MMAAgent
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
