"""
Unit tests for MMA agent — mocks HTTP client and gRPC emitter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.mma.agent import MMAAgent
from agents.mma.models import Event, Fight, Fighter, FightStat


def _make_fighter(fid: int, name: str = "Fighter") -> Fighter:
    parts = name.split(" ", 1)
    return Fighter(
        id=fid,
        first_name=parts[0],
        last_name=parts[1] if len(parts) > 1 else "X",
    )


def _make_fight(fight_id: int) -> Fight:
    return Fight(
        id=fight_id,
        event_id=1,
        fighter1=_make_fighter(10, "Alice Smith"),
        fighter2=_make_fighter(11, "Bob Jones"),
        status="in_progress",
    )


def _make_event(event_id: int, fights: list[Fight]) -> Event:
    from datetime import date
    return Event(
        id=event_id,
        name=f"UFC {event_id}",
        date=date.today(),
        fights=fights,
    )


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_live_events.return_value = []
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
async def test_new_fight_emits_fight_discovered(agent, mock_client, mock_emitter):
    """First time a fight is seen, FIGHT_DISCOVERED event is emitted."""
    mock_client.get_live_events.return_value = [
        _make_event(1, [_make_fight(101)])
    ]
    await agent._poll_once()
    mock_emitter.emit.assert_called_once()


@pytest.mark.asyncio
async def test_known_fight_not_re_emitted(agent, mock_client, mock_emitter):
    """Subsequent polls for the same fight should not re-emit."""
    event = _make_event(1, [_make_fight(101)])
    mock_client.get_live_events.return_value = [event]

    await agent._poll_once()
    mock_emitter.emit.reset_mock()

    # Second poll — same fight
    await agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_fight_discovered_event_fields(agent, mock_client, mock_emitter):
    """Emitted event has correct source and stat_type."""
    mock_client.get_live_events.return_value = [
        _make_event(1, [_make_fight(202)])
    ]
    await agent._poll_once()

    ev = mock_emitter.emit.call_args[0][0]
    from agents.generated import events_pb2  # type: ignore[import]
    assert ev.source == events_pb2.SOURCE_MMA
    assert ev.fight_event.fight_id == "202"
    assert ev.fight_event.stat_type == "FIGHT_DISCOVERED"


@pytest.mark.asyncio
async def test_multiple_fights_each_emitted_once(agent, mock_client, mock_emitter):
    mock_client.get_live_events.return_value = [
        _make_event(1, [_make_fight(301), _make_fight(302)])
    ]
    await agent._poll_once()
    assert mock_emitter.emit.call_count == 2


# ─── GOAT-tier _poll_fight_stats tests ─────────────────────────────────────


def _make_fight_stat(fight_id: int, fighter_name: str, **kwargs) -> FightStat:
    return FightStat(
        fight_id=fight_id,
        fighter_id=1,
        fighter_name=fighter_name,
        **kwargs,
    )


@pytest.fixture
def goat_agent(mock_client, mock_emitter, monkeypatch):
    """Agent with GOAT tier enabled."""
    monkeypatch.setattr("agents.mma.agent._GOAT_TIER_ENABLED", True)
    return MMAAgent(client=mock_client, emitter=mock_emitter)


@pytest.mark.asyncio
async def test_goat_stat_change_emits_event(goat_agent, mock_client, mock_emitter):
    """When a stat changes between polls, a FightStatEvent is emitted."""
    fight = _make_fight(101)
    events = [_make_event(1, [fight])]
    mock_client.get_live_events.return_value = events
    mock_client.get_fight_stats.return_value = [
        _make_fight_stat(101, "Alice Smith", significant_strikes=5, takedowns=1, knockdowns=0),
    ]

    await goat_agent._poll_once()

    # FIGHT_DISCOVERED + 2 stat changes (significant_strikes=5, takedowns=1; knockdowns=0 unchanged from default 0)
    stat_events = [
        call[0][0] for call in mock_emitter.emit.call_args_list
        if call[0][0].fight_event.stat_type != "FIGHT_DISCOVERED"
    ]
    assert len(stat_events) == 2
    stat_types = {e.fight_event.stat_type for e in stat_events}
    assert stat_types == {"significant_strikes", "takedowns"}


@pytest.mark.asyncio
async def test_goat_no_change_no_emit(goat_agent, mock_client, mock_emitter):
    """Same stats on second poll should not re-emit."""
    fight = _make_fight(101)
    events = [_make_event(1, [fight])]
    mock_client.get_live_events.return_value = events
    mock_client.get_fight_stats.return_value = [
        _make_fight_stat(101, "Alice Smith", significant_strikes=5),
    ]

    await goat_agent._poll_once()
    mock_emitter.emit.reset_mock()

    # Second poll — same stats
    await goat_agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_goat_completed_fight_stops_polling(goat_agent, mock_client, mock_emitter):
    """Completed fights should not have stats polled."""
    fight = _make_fight(101)
    fight.status = "completed"
    events = [_make_event(1, [fight])]
    mock_client.get_live_events.return_value = events

    await goat_agent._poll_once()

    # get_fight_stats should NOT be called for completed fights
    mock_client.get_fight_stats.assert_not_called()


@pytest.mark.asyncio
async def test_goat_stub_not_implemented_handled(goat_agent, mock_client, mock_emitter):
    """If stubs still raise NotImplementedError, agent handles gracefully."""
    fight = _make_fight(101)
    events = [_make_event(1, [fight])]
    mock_client.get_live_events.return_value = events
    mock_client.get_fight_stats.side_effect = NotImplementedError("GOAT tier required")

    # Should not raise
    await goat_agent._poll_once()

    # Only FIGHT_DISCOVERED emitted, no stat events
    assert mock_emitter.emit.call_count == 1
    assert mock_emitter.emit.call_args[0][0].fight_event.stat_type == "FIGHT_DISCOVERED"


@pytest.mark.asyncio
async def test_goat_scheduled_fight_skipped(goat_agent, mock_client, mock_emitter):
    """Fights that are 'scheduled' (not in_progress) should not have stats polled."""
    fight = _make_fight(101)
    fight.status = "scheduled"
    events = [_make_event(1, [fight])]
    mock_client.get_live_events.return_value = events

    await goat_agent._poll_once()

    mock_client.get_fight_stats.assert_not_called()
