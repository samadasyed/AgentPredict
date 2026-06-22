/**
 * Derive view-models from the live event stream.
 *
 *  - MarketSeries: per-market probability trajectory + lifecycle phase. The
 *    trajectory is seeded from the `history` snapshot the agent ships (so the
 *    pre-event odds trend is there immediately) then extended with live ticks.
 *  - LiveFight / FightStatUpdate: per-fighter running stats and a play-by-play,
 *    derived from MMA FightStatEvents during a live fight.
 *
 * The event list is newest-first (the hook prepends); we walk it oldest→newest
 * so each series reads left (older) → right (newer) for charting.
 *
 * NOTE: protobuf int64 fields (timestamp, event_start, history timestamps) arrive
 * as JSON strings, so anything time-related is Number()-coerced at the boundary.
 */

import type { CanonicalEvent, MarketEvent } from '../types/events'

const MAX_POINTS = 160
const DAY_MS = 86_400_000

export type Phase = 'live' | 'upcoming' | 'final' | 'unknown'

export interface MarketSeries {
  marketId: string
  outcome: string
  points: number[]        // probabilities [0,1], chronological
  latest: MarketEvent
  updatedAt: number       // ms
  phase: Phase
  eventStart: number      // ms; 0 = unknown
  historyStart: number    // ms of the first history point; 0 = none
}

const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v ?? 0)) || 0

/** Lifecycle phase: trust the source's label, else derive from the schedule. */
export function classifyPhase(latest: MarketEvent, eventStart: number): Phase {
  const p = latest.phase
  if (p === 'live' || p === 'upcoming' || p === 'final') return p
  if (eventStart > 0) return eventStart <= Date.now() ? 'live' : 'upcoming'
  return 'unknown'
}

export function buildMarketSeries(events: CanonicalEvent[]): MarketSeries[] {
  const byMarket = new Map<string, MarketEvent[]>()
  for (let i = events.length - 1; i >= 0; i--) {
    const m = events[i].market_event
    if (!m) continue
    const arr = byMarket.get(m.market_id)
    if (arr) arr.push(m)
    else byMarket.set(m.market_id, [m])
  }

  const series: MarketSeries[] = []
  for (const [marketId, arr] of byMarket) {
    const latest = arr[arr.length - 1]

    // Seed the line from the richest history snapshot we've received for this
    // market, then append each live reading in chronological order. Schedule and
    // phase are taken from the most recent event that carries them (live ticks
    // all do, but we stay robust to partial events).
    let seed: NonNullable<MarketEvent['history']> = []
    for (const m of arr) {
      if (m.history && m.history.length > seed.length) seed = m.history
    }
    const points = seed.map((h) => h.probability)
    let phaseStr = ''
    let eventStart = 0
    for (const m of arr) {
      points.push(m.probability)
      if (m.phase) phaseStr = m.phase
      const es = num(m.event_start)
      if (es) eventStart = es
    }

    series.push({
      marketId,
      outcome: latest.outcome,
      points: points.slice(-MAX_POINTS),
      latest,
      updatedAt: num(latest.timestamp),
      phase: classifyPhase({ ...latest, phase: phaseStr }, eventStart),
      eventStart,
      historyStart: seed.length ? num(seed[0].timestamp) : 0,
    })
  }
  return series
}

/**
 * The headline fight: a live fight if one exists, otherwise the soonest upcoming
 * fight, otherwise the biggest recent mover (markets with no schedule).
 */
export function pickFeatured(series: MarketSeries[]): MarketSeries | null {
  if (series.length === 0) return null

  const live = series.filter((s) => s.phase === 'live')
  if (live.length) {
    return [...live].sort(
      (a, b) => Math.abs(b.latest.delta) - Math.abs(a.latest.delta) || b.updatedAt - a.updatedAt,
    )[0]
  }

  const upcoming = series.filter((s) => s.phase === 'upcoming' && s.eventStart > 0)
  if (upcoming.length) {
    return [...upcoming].sort((a, b) => a.eventStart - b.eventStart)[0]
  }

  return [...series].sort(
    (a, b) => Math.abs(b.latest.delta) - Math.abs(a.latest.delta) || b.updatedAt - a.updatedAt,
  )[0]
}

/** Markets sorted by most recent activity, for the movers strip. */
export function sortByRecent(series: MarketSeries[]): MarketSeries[] {
  return [...series].sort((a, b) => b.updatedAt - a.updatedAt)
}

/** Upcoming fights, soonest first. */
export function upcomingFights(series: MarketSeries[]): MarketSeries[] {
  return series
    .filter((s) => s.phase === 'upcoming' && s.eventStart > 0)
    .sort((a, b) => a.eventStart - b.eventStart)
}

/** Split "Jon Jones def. Tom Aspinall" → ["Jon Jones", "Tom Aspinall"]. */
export function parseFighters(outcome: string): [string, string] | null {
  const m = outcome.match(/^(.+?)\s+(?:def\.|defeats|beats|vs\.?)\s+(.+)$/i)
  return m ? [m[1].trim(), m[2].trim()] : null
}

// ─── Time helpers ─────────────────────────────────────────────────────────────

/** "in 2d 4h" / "in 3h 12m" / "in 8m" / "starting now". */
export function formatCountdown(targetMs: number, nowMs: number = Date.now()): string {
  const ms = targetMs - nowMs
  if (ms <= 0) return 'starting now'
  const totalMin = Math.floor(ms / 60_000)
  const d = Math.floor(totalMin / 1440)
  const h = Math.floor((totalMin % 1440) / 60)
  const m = totalMin % 60
  if (d > 0) return `in ${d}d ${h}h`
  if (h > 0) return `in ${h}h ${m}m`
  return `in ${m}m`
}

/** Approximate human span since a start time, e.g. "7d" / "26h". */
export function formatSpan(fromMs: number, nowMs: number = Date.now()): string {
  const ms = Math.max(0, nowMs - fromMs)
  const days = ms / DAY_MS
  if (days >= 1) return `${Math.round(days)}d`
  return `${Math.max(1, Math.round(ms / 3_600_000))}h`
}

// ─── Live fight stats (MMA FightStatEvents) ────────────────────────────────────

const DISCOVERED = 'FIGHT_DISCOVERED'

export interface FightStatUpdate {
  eventId: string
  fightId: string
  fighter: string
  statType: string
  value: number
  delta: number       // change vs the previous reading of the same fighter+stat
  round: number
  timestamp: number
}

export interface FighterTotals {
  fighter: string
  stats: Record<string, number>   // statType → latest cumulative value
  lastUpdate: number
}

export interface LiveFight {
  fightId: string
  fighters: FighterTotals[]
  lastUpdate: number
}

const isStat = (e: CanonicalEvent): boolean =>
  !!e.fight_event && e.fight_event.stat_type !== DISCOVERED && !!e.fight_event.fighter_name

/** Per-update play-by-play (newest first) with per-stat deltas. */
export function buildFightUpdates(events: CanonicalEvent[]): FightStatUpdate[] {
  const last = new Map<string, number>()   // `${fightId}|${fighter}|${statType}` → value
  const out: FightStatUpdate[] = []
  for (let i = events.length - 1; i >= 0; i--) {   // oldest → newest
    const e = events[i]
    if (!isStat(e)) continue
    const f = e.fight_event!
    const key = `${f.fight_id}|${f.fighter_name}|${f.stat_type}`
    const prev = last.get(key)
    const value = num(f.value)
    out.push({
      eventId: e.event_id,
      fightId: f.fight_id,
      fighter: f.fighter_name,
      statType: f.stat_type,
      value,
      delta: prev === undefined ? value : value - prev,
      round: num(f.round),
      timestamp: num(f.timestamp),
    })
    last.set(key, value)
  }
  return out.reverse()   // newest first
}

/** Group live fights with each fighter's latest cumulative stats. */
export function buildLiveFights(events: CanonicalEvent[]): LiveFight[] {
  const fights = new Map<string, Map<string, FighterTotals>>()
  const fightLast = new Map<string, number>()
  for (let i = events.length - 1; i >= 0; i--) {   // oldest → newest
    const e = events[i]
    if (!isStat(e)) continue
    const f = e.fight_event!
    const ts = num(f.timestamp)
    let fighters = fights.get(f.fight_id)
    if (!fighters) fights.set(f.fight_id, (fighters = new Map()))
    let totals = fighters.get(f.fighter_name)
    if (!totals) fighters.set(f.fighter_name, (totals = { fighter: f.fighter_name, stats: {}, lastUpdate: 0 }))
    totals.stats[f.stat_type] = num(f.value)
    totals.lastUpdate = Math.max(totals.lastUpdate, ts)
    fightLast.set(f.fight_id, Math.max(fightLast.get(f.fight_id) ?? 0, ts))
  }

  return [...fights.entries()]
    .map(([fightId, fighters]) => ({
      fightId,
      fighters: [...fighters.values()].sort((a, b) => b.lastUpdate - a.lastUpdate),
      lastUpdate: fightLast.get(fightId) ?? 0,
    }))
    .sort((a, b) => b.lastUpdate - a.lastUpdate)
}

/** Best-effort link a live fight to a market outcome by shared fighter surname. */
export function findFightForOutcome(fights: LiveFight[], outcome: string): LiveFight | null {
  const hay = outcome.toLowerCase()
  for (const fight of fights) {
    for (const ft of fight.fighters) {
      const tokens = ft.fighter.toLowerCase().split(/\s+/).filter((t) => t.length > 3)
      if (tokens.some((t) => hay.includes(t))) return fight
    }
  }
  return null
}
