# Component: `agents/` — Python pollers

Two independent processes translate the outside world into `CanonicalEvent`s
and push them to the engine over gRPC (`agents/shared/event_emitter.py`,
single channel, `emit()` with retry via `agents/shared/retry.py`).

## Polymarket agent (`agents/polymarket/`)

- **Discovery** (`client.py`): `GET /events/pagination?tag_slug=<POLYMARKET_TAG>`
  → one `Market` per fight = the moneyline market, enriched with matchup
  `title`, `card_title`, `fight_info` ("Welterweight · Main Card"), `volume`,
  `event_slug`, scheduled start, and lifecycle `phase`. Futures rejected by
  title shape; stale open leftovers (start >`POLYMARKET_STALE_HOURS` ago)
  dropped. Falls back to the generic top-volume list only if the tag is empty.
- **Prices**: one snapshot per market for the PRIMARY outcome (fighter A);
  fighter B's probability is the complement. Week-long history fetched from
  CLOB once per market per 5-min TTL and shipped as a snapshot on the event.
- **Emit policy** (`agent.py`):
  - per-tick move ≥ `POLYMARKET_DELTA_THRESHOLD` (0.01) → delta event;
  - else first sighting OR every `POLYMARKET_REBASELINE_S` (120s) → baseline
    event (delta 0) so late-joining clients always receive the full slate.
- **Filter**: keeps markets whose question contains `POLYMARKET_QUERY`
  ("UFC"); `POLYMARKET_FALLBACK_ALL=1` opts into off-theme markets.

## MMA agent (`agents/mma/`)

- **Upcoming cards** (free tier): `/events` filtered to `MMA_PROMOTION` within
  [now−24h, now+`MMA_UPCOMING_DAYS`], capped at `MMA_UPCOMING_MAX`; each card
  re-emits a `FIGHT_UPCOMING` sentinel every poll (dashboard dedups) with the
  matchup in `fighter_name` and the card start in `event_start`.
- **Live stats** (GOAT tier, `BALLDONTLIE_GOAT_TIER=1`): detects in-progress
  events, polls `/fight_stats` per live fight, emits one `FightStatEvent` per
  fighter per stat with cumulative values.

## Mocks

`mock_client.py` in each package mirrors the real client's interface AND
output shape exactly (fighter-name outcomes, matching names across both mocks
so odds fuse with stats). `MOCK_MODE=1` selects them.

## Tests

`agents/tests/unit/` — parsing against real-shaped Gamma fixtures, emit-policy
contracts (baseline/re-baseline/delta), upcoming-card filtering, mock-shape
guarantees. Run per `handoff/RUNBOOK.md`.
