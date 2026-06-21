/**
 * Derive per-market probability time-series from the live event stream.
 * The event list is newest-first (the hook prepends); we walk it oldest→newest
 * so each series reads left (older) → right (newer) for charting.
 */

import type { CanonicalEvent, MarketEvent } from '../types/events'

export interface MarketSeries {
  marketId: string
  outcome: string
  points: number[]        // probabilities [0,1], chronological
  latest: MarketEvent
  updatedAt: number
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
    series.push({
      marketId,
      outcome: latest.outcome,
      points: arr.map((m) => m.probability).slice(-60),
      latest,
      updatedAt: latest.timestamp,
    })
  }
  return series
}

/** The market with the largest recent absolute move (tiebreak: most recent). */
export function pickFeatured(series: MarketSeries[]): MarketSeries | null {
  if (series.length === 0) return null
  return [...series].sort(
    (a, b) => Math.abs(b.latest.delta) - Math.abs(a.latest.delta) || b.updatedAt - a.updatedAt,
  )[0]
}

/** Markets sorted by most recent activity, for the movers strip. */
export function sortByRecent(series: MarketSeries[]): MarketSeries[] {
  return [...series].sort((a, b) => b.updatedAt - a.updatedAt)
}

/** Split "Jon Jones def. Tom Aspinall" → ["Jon Jones", "Tom Aspinall"]. */
export function parseFighters(outcome: string): [string, string] | null {
  const m = outcome.match(/^(.+?)\s+(?:def\.|defeats|beats|vs\.?)\s+(.+)$/i)
  return m ? [m[1].trim(), m[2].trim()] : null
}
