/**
 * Unified "upcoming fight" view-model.
 *
 * Two sources feed it:
 *   - BallDontLie schedule events (FIGHT_UPCOMING) → matchup + start + phase, but
 *     no odds (and available even when /fights is plan-gated).
 *   - Polymarket markets → odds + history, when a UFC market is actually trading.
 *
 * A card may come from either or both; when both exist for the same matchup they
 * merge (the fight card gains its market's odds/sparkline).
 */

import type { CanonicalEvent } from '../types/events'
import type { MarketSeries, Phase } from './marketSeries'
import { matchupFor, parseFighters } from './marketSeries'

const UPCOMING = 'FIGHT_UPCOMING'
const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v ?? 0)) || 0

export interface UpcomingFight {
  id: string
  matchup: string
  cardTitle: string           // "UFC 329" etc.; '' unknown
  eventStart: number          // ms; 0 = unknown
  phase: Phase
  market: MarketSeries | null // odds/history when a market exists
}

/** Surnames (>3 chars) shared between two matchup/outcome strings → same fight. */
function sameMatchup(a: string, b: string): boolean {
  const tokens = (s: string) =>
    new Set(s.toLowerCase().replace(/[.]/g, '').split(/\s+/).filter((t) => t.length > 3))
  const ta = tokens(a)
  const hay = b.toLowerCase()
  let shared = 0
  for (const t of ta) if (hay.includes(t)) shared++
  return shared >= 1
}

const asPhase = (p: string | undefined, fallback: Phase = 'upcoming'): Phase =>
  p === 'live' || p === 'upcoming' || p === 'final' ? p : fallback

/**
 * Merge schedule events and market series into a sorted list of upcoming fights.
 * `series` should be the full MarketSeries list; we pull upcoming/live ones in.
 */
export function buildUpcomingFights(events: CanonicalEvent[], series: MarketSeries[]): UpcomingFight[] {
  // 1. Newest FIGHT_UPCOMING per fight_id.
  const byId = new Map<string, CanonicalEvent['fight_event']>()
  const seen = new Map<string, number>()
  for (const e of events) {
    const f = e.fight_event
    if (!f || f.stat_type !== UPCOMING) continue
    const ts = num(f.timestamp)
    if (ts >= (seen.get(f.fight_id) ?? -1)) {
      seen.set(f.fight_id, ts)
      byId.set(f.fight_id, f)
    }
  }

  const marketUpcoming = series.filter(
    (s) => (s.phase === 'upcoming' || s.phase === 'live') && parseFighters(matchupFor(s)),
  )
  const usedMarkets = new Set<string>()

  const cards: UpcomingFight[] = []
  for (const f of byId.values()) {
    if (!f) continue
    const market =
      marketUpcoming.find((s) => !usedMarkets.has(s.marketId) && sameMatchup(f.fighter_name, matchupFor(s))) ?? null
    if (market) usedMarkets.add(market.marketId)
    cards.push({
      id: f.fight_id,
      // Prefer the market's title — it names both fighters cleanly.
      matchup: market ? matchupFor(market) : f.fighter_name,
      cardTitle: market?.cardTitle ?? '',
      eventStart: num(f.event_start) || (market?.eventStart ?? 0),
      phase: asPhase(f.phase),
      market,
    })
  }

  // 2. Market-sourced fights with no schedule event of their own.
  for (const s of marketUpcoming) {
    if (usedMarkets.has(s.marketId)) continue
    cards.push({
      id: `mkt:${s.marketId}`,
      matchup: matchupFor(s),
      cardTitle: s.cardTitle,
      eventStart: s.eventStart,
      phase: s.phase,
      market: s,
    })
  }

  // Soonest first; unknown start times (0) sink to the bottom.
  return cards.sort((a, b) => (a.eventStart || Infinity) - (b.eventStart || Infinity))
}
