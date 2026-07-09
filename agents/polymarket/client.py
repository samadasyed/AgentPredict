"""
Async Polymarket client (Gamma API — https://gamma-api.polymarket.com).

Primary discovery is EVENTS BY TAG: `/events?tag_slug=ufc&closed=false` returns
every UFC event Polymarket lists — one event per fight (e.g. "UFC 329: Max
Holloway vs. Conor McGregor (Welterweight, Main Card)") with all of its markets
embedded, prices inline, and a real scheduled start time. From each fight event
we keep the single MONEYLINE (fight winner) market, enriched with the matchup,
card title, weight class / card segment, and volume.

If the tag yields nothing (e.g. a different POLYMARKET_TAG with no listings),
we fall back to the generic top-volume live-market list so the agent's
QUERY / FALLBACK_ALL filtering still has something to work with.

A browser User-Agent is required (the edge 403s default UAs).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from agents.polymarket.models import Market, PriceSnapshot, TokenPrice
from agents.shared.retry import retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://gamma-api.polymarket.com"
# CLOB serves per-token price history (the Gamma list has only the current price).
_CLOB_URL = "https://clob.polymarket.com"
_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_LIMIT = int(os.getenv("POLYMARKET_LIMIT", "80"))   # top-volume fallback list size
# Gamma tag that scopes discovery (UFC product → "ufc").
_TAG_SLUG = os.getenv("POLYMARKET_TAG", "ufc")
# A fight whose scheduled start is this many hours in the past but whose market
# is still open is a leftover (card change, late resolution) — drop it. UFC
# cards run ~7 hours end to end.
_STALE_HOURS = float(os.getenv("POLYMARKET_STALE_HOURS", "12"))
# Window of price history to request for the pre-event odds-trend chart.
_HISTORY_INTERVAL = os.getenv("POLYMARKET_HISTORY_INTERVAL", "1w")
# CLOB requires a resolution ("fidelity", minutes per point) with ranged
# intervals — 1w rejects anything under 5. 180 (3h) ≈ 56 points per week.
_HISTORY_FIDELITY_MIN = os.getenv("POLYMARKET_HISTORY_FIDELITY_MIN", "180")
MARKET_CACHE_TTL_S: int = 300  # 5 minutes
_DEBUG_DUMP = os.getenv("DEBUG_DUMP", "0") == "1"
_DEBUG_DIR = Path("/tmp/polymarket_debug")


def _iso_to_ms(value: Any) -> int:
    """Parse an ISO-8601-ish timestamp to unix millis. Handles both Gamma forms:
    '2026-07-11T22:00:00Z' and '2026-07-11 22:00:00+00' (gameStartTime uses a
    space separator and a short offset). Returns 0 on anything unparseable."""
    if not value or not isinstance(value, str):
        return 0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


# Gamma returns currently-tradeable markets ordered by 24h volume (fallback path).
_LIST_PARAMS = {
    "active": "true",
    "closed": "false",
    "order": "volume24hr",
    "ascending": "false",
    "limit": str(_LIMIT),
}

_EVENTS_PARAMS = {
    "tag_slug": _TAG_SLUG,
    "closed": "false",
    "limit": "100",
}

# "UFC 329: Max Holloway vs. Conor McGregor (Welterweight, Main Card)"
#   card="UFC 329"  matchup="Max Holloway vs. Conor McGregor"
#   info="Welterweight, Main Card"
_FIGHT_TITLE_RE = re.compile(
    r"^(?P<card>[^:]+):\s*(?P<matchup>[^(]+?)\s*(?:\((?P<info>[^)]*)\))?\s*$"
)
_VS_RE = re.compile(r"\bvs\.?\s", re.IGNORECASE)


def _parse_tokens(obj: dict) -> list[TokenPrice]:
    """Outcome tokens from a Gamma market object (outcomes/prices are JSON strings)."""
    try:
        outcomes = json.loads(obj.get("outcomes") or "[]")
        prices = json.loads(obj.get("outcomePrices") or "[]")
        token_ids = json.loads(obj.get("clobTokenIds") or "[]")
    except (TypeError, ValueError):
        return []
    if not outcomes or len(prices) != len(outcomes):
        return []
    cid = obj.get("conditionId") or obj.get("id") or ""
    tokens: list[TokenPrice] = []
    for i, name in enumerate(outcomes):
        try:
            price = float(prices[i])
        except (TypeError, ValueError):
            continue
        tid = str(token_ids[i]) if i < len(token_ids) else f"{cid}-{i}"
        tokens.append(TokenPrice(token_id=tid, outcome=str(name), price=min(1.0, max(0.0, price))))
    return tokens


def _phase_for(closed: bool, event_start_ms: int, now_ms: int) -> str:
    if closed:
        return "final"
    if not event_start_ms:
        return ""
    return "live" if event_start_ms <= now_ms else "upcoming"


def _parse_market(obj: dict) -> Market | None:
    """Build a Market from a generic Gamma market object (fallback path)."""
    tokens = _parse_tokens(obj)
    cid = obj.get("conditionId") or obj.get("condition_id") or obj.get("id")
    if not tokens or not cid:
        return None

    closed = bool(obj.get("closed", False))

    # Scheduled start of the underlying event. Gamma uses several field names
    # depending on the market type; take the first that parses.
    event_start_ms = 0
    for key in ("gameStartTime", "startDate", "startTime", "eventStartTime"):
        event_start_ms = _iso_to_ms(obj.get(key))
        if event_start_ms:
            break

    return Market(
        condition_id=str(cid),
        question=obj.get("question", ""),
        tokens=tokens,
        active=bool(obj.get("active", True)),
        closed=closed,
        accepting_orders=not closed,
        event_start_ms=event_start_ms,
        phase=_phase_for(closed, event_start_ms, int(time.time() * 1000)),
    )


def _parse_fight_event(ev: dict, now_ms: int) -> Market | None:
    """Build one Market (the fight-winner moneyline) from a Gamma EVENT object,
    or None if the event isn't an individual fight (futures, "who fights next",
    props-only) or is a stale leftover from a card change."""
    title_raw = (ev.get("title") or "").strip()
    m = _FIGHT_TITLE_RE.match(title_raw)
    if not m or not _VS_RE.search(m.group("matchup")):
        return None  # not "<card>: <A> vs. <B> (...)" — futures/speculative event

    markets = ev.get("markets") or []
    moneyline = next(
        (mk for mk in markets if mk.get("sportsMarketType") == "moneyline"),
        None,
    ) or next((mk for mk in markets if (mk.get("question") or "").strip() == title_raw), None)
    if moneyline is None or bool(moneyline.get("closed", False)):
        return None

    tokens = _parse_tokens(moneyline)
    cid = moneyline.get("conditionId") or moneyline.get("id")
    if not tokens or not cid:
        return None

    event_start_ms = (
        _iso_to_ms(ev.get("startTime"))
        or _iso_to_ms(moneyline.get("gameStartTime"))
        or _iso_to_ms(ev.get("eventDate"))
    )
    # Started long ago but still open → dead listing (opponent swap etc.). Drop.
    if event_start_ms and (now_ms - event_start_ms) > _STALE_HOURS * 3_600_000:
        return None

    info = (m.group("info") or "").strip()
    try:
        volume = float(ev.get("volume") or 0.0)
    except (TypeError, ValueError):
        volume = 0.0

    return Market(
        condition_id=str(cid),
        question=title_raw,
        tokens=tokens,
        active=bool(ev.get("active", True)),
        closed=False,
        # Viewer semantics: a fight market is "on" until it resolves — Polymarket
        # may pause order-taking mid-fight, which must not hide the fight.
        accepting_orders=True,
        event_start_ms=event_start_ms,
        phase=_phase_for(False, event_start_ms, now_ms),
        title=" ".join(m.group("matchup").split()),
        card_title=m.group("card").strip(),
        event_slug=str(ev.get("slug") or ""),
        fight_info=" · ".join(part.strip() for part in info.split(",") if part.strip()),
        volume=volume,
    )


class PolymarketClient:
    """Async wrapper around the Polymarket Gamma API."""

    def __init__(self, base_url: str = _BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._market_cache: list[Market] = []
        self._cache_loaded_at: float = 0.0
        # condition_id → recent (timestamp_ms, probability) trajectory, cached so
        # we hit the CLOB history endpoint at most once per market per TTL.
        self._history_cache: dict[str, list[tuple[int, float]]] = {}
        self._history_loaded_at: float = 0.0

    async def _session_(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    @retry(max_attempts=4, base_delay=1.0, retryable=(aiohttp.ClientError, TimeoutError))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._session_()
        async with session.get(f"{self._base_url}{path}", params=params) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("[polymarket] rate limited — backing off %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise aiohttp.ClientError("rate limited")
            resp.raise_for_status()
            data = await resp.json()
            if _DEBUG_DUMP:
                _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                (_DEBUG_DIR / f"{path.strip('/').replace('/', '_')}_{int(time.time())}.json").write_text(
                    json.dumps(data, indent=2)[:200_000])
            return data

    async def _fetch_fight_markets(self) -> list[Market]:
        """One Market per listed fight, via tagged events. Soonest card first,
        then by volume so the main event leads its card.

        Uses /events/pagination — the bare /events is deprecated (its Sunset
        header already passed); both return the same event objects."""
        raw = await self._get("/events/pagination", params=_EVENTS_PARAMS)
        events = raw if isinstance(raw, list) else raw.get("data", [])
        now_ms = int(time.time() * 1000)
        fights = [f for f in (_parse_fight_event(ev, now_ms) for ev in events) if f]
        fights.sort(key=lambda f: (f.event_start_ms or float("inf"), -f.volume))
        return fights

    async def _fetch_live(self) -> list[Market]:
        """Generic fallback: top live markets by 24h volume. (/markets is
        marked deprecated by Gamma but still serves; the pagination variant
        rejects these params. Rarely used — only when the tag has no fights.)"""
        raw = await self._get("/markets", params=_LIST_PARAMS)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        return [m for m in (_parse_market(o) for o in items) if m]

    async def _fetch_current(self) -> list[Market]:
        fights = await self._fetch_fight_markets()
        if fights:
            return fights
        logger.info("[polymarket] no fight events under tag '%s' — falling back to top-volume list",
                    _TAG_SLUG)
        return await self._fetch_live()

    async def _fetch_history(self, token_id: str) -> list[tuple[int, float]]:
        """Recent price history for one CLOB token, oldest first. Best-effort —
        returns [] on any failure so a missing history never breaks the poll."""
        try:
            session = await self._session_()
            params = {"market": token_id, "interval": _HISTORY_INTERVAL,
                      "fidelity": _HISTORY_FIDELITY_MIN}
            async with session.get(f"{_CLOB_URL}/prices-history", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.debug("[polymarket] history fetch failed for %s: %s", token_id, exc)
            return []
        rows = data.get("history", []) if isinstance(data, dict) else []
        out: list[tuple[int, float]] = []
        for row in rows:
            t, p = row.get("t"), row.get("p")
            if t is None or p is None:
                continue
            try:
                out.append((int(t) * 1000, min(1.0, max(0.0, float(p)))))  # CLOB `t` is epoch seconds
            except (TypeError, ValueError):
                continue
        return out

    async def get_markets(self, active_only: bool = True, max_pages: int | None = None) -> list[Market]:
        """Currently-listed fight markets (or the generic top-volume fallback),
        cached for MARKET_CACHE_TTL_S."""
        now = time.monotonic()
        if self._market_cache and (now - self._cache_loaded_at) < MARKET_CACHE_TTL_S:
            return self._market_cache
        markets = await self._fetch_current()
        self._market_cache = markets
        self._cache_loaded_at = now
        logger.info("[polymarket] fetched %d markets (cache refreshed)", len(markets))
        return markets

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        """Fresh price for the PRIMARY outcome of each wanted market (one
        snapshot per market — for a fight moneyline that is fighter A's win
        probability; fighter B's is its complement). Each snapshot also carries
        the scheduled start, phase, fight metadata, and recent price history."""
        wanted = set(market_ids)
        now_ms = int(time.time() * 1000)

        if time.monotonic() - self._history_loaded_at >= MARKET_CACHE_TTL_S:
            self._history_cache.clear()  # expire stale histories

        snapshots: list[PriceSnapshot] = []
        for m in await self._fetch_current():
            if m.condition_id not in wanted:
                continue
            token = m.tokens[0]
            # Fetch history once per market per TTL, for the primary outcome only.
            if m.condition_id not in self._history_cache:
                self._history_cache[m.condition_id] = await self._fetch_history(token.token_id)
                self._history_loaded_at = time.monotonic()
            snapshots.append(PriceSnapshot(
                market_id=m.condition_id,
                token_id=token.token_id,
                outcome=token.outcome,
                probability=token.price,
                timestamp_ms=now_ms,
                history=self._history_cache[m.condition_id],
                event_start_ms=m.event_start_ms,
                phase=m.phase,
                title=m.title,
                card_title=m.card_title,
                fight_info=m.fight_info,
                volume=m.volume,
                event_slug=m.event_slug,
            ))
        return snapshots

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "PolymarketClient":
        return self

    async def __aexit__(self, *_) -> None:
        return await self.close()
