"""
Unit tests for MMA agent — mocks HTTP client and gRPC emitter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.mma.agent import MMAAgent
from agents.mma.models import Event, Fight, Fighter


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
