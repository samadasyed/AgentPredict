import { describe, it, expect } from 'vitest'
import type { CanonicalEvent, MarketEvent, FightStatEvent } from '../../types/events'
import { buildMarketSeries } from '../../lib/marketSeries'
import { buildUpcomingFights } from '../../lib/fights'

let seq = 0
const now = Date.now()

function upcomingEvent(
  fightId: string, matchup: string, startMs: number, phase = 'upcoming', ts = seq++,
): CanonicalEvent {
  return {
    event_id: `e${seq++}`, source: 'SOURCE_MMA', ingested_at: 0,
    fight_event: {
      fight_id: fightId, fighter_name: matchup, stat_type: 'FIGHT_UPCOMING',
      value: 0, round: 0, timestamp: ts, event_start: startMs, phase,
    } as FightStatEvent,
  }
}
function marketEvent(marketId: string, outcome: string, startMs: number): CanonicalEvent {
  return {
    event_id: `m${seq++}`, source: 'SOURCE_POLYMARKET', ingested_at: 0,
    market_event: {
      market_id: marketId, outcome, probability: 0.6, delta: 0.02, timestamp: seq,
      event_start: startMs, phase: 'upcoming',
    } as MarketEvent,
  }
}

describe('buildUpcomingFights', () => {
  it('builds schedule-only cards sorted soonest-first', () => {
    const events = [
      upcomingEvent('329', 'McGregor vs. Holloway 2', now + 7 * 86_400_000),
      upcomingEvent('311', 'Fiziev vs. Torres', now + 2 * 86_400_000),
    ]
    const cards = buildUpcomingFights(events, [])
    expect(cards.map((c) => c.id)).toEqual(['311', '329'])  // soonest first
    expect(cards[0].matchup).toBe('Fiziev vs. Torres')
    expect(cards[0].market).toBeNull()
    expect(cards[0].phase).toBe('upcoming')
    expect(cards[0].eventStart).toBeGreaterThan(now)
  })

  it('merges a market onto a matching schedule card by fighter name', () => {
    const events = [
      upcomingEvent('500', 'Jones vs. Aspinall', now + 3 * 86_400_000),
      marketEvent('mkt-jones', 'Jon Jones def. Tom Aspinall', now + 3 * 86_400_000),
    ]
    const series = buildMarketSeries(events)
    const cards = buildUpcomingFights(events, series)
    expect(cards).toHaveLength(1)               // merged, not duplicated
    expect(cards[0].id).toBe('500')
    expect(cards[0].market?.marketId).toBe('mkt-jones')
  })

  it('includes market-only fights (no schedule event) and ignores off-theme markets', () => {
    const events = [
      marketEvent('mkt-ufc', 'Alex Pereira def. Magomed Ankalaev', now + 4 * 86_400_000),
      marketEvent('mkt-wc', 'Will Brazil win the World Cup?', now + 4 * 86_400_000),  // no fighters → excluded
    ]
    const series = buildMarketSeries(events)
    const cards = buildUpcomingFights(events, series)
    expect(cards).toHaveLength(1)
    expect(cards[0].id).toBe('mkt:mkt-ufc')
    expect(cards[0].market?.marketId).toBe('mkt-ufc')
  })

  it('keeps the newest schedule reading per fight_id', () => {
    const events = [
      upcomingEvent('700', 'A vs. B', now + 5 * 86_400_000, 'upcoming', 1),
      upcomingEvent('700', 'A vs. B', now - 60_000, 'live', 2),  // newer, now live
    ]
    const cards = buildUpcomingFights(events, [])
    expect(cards).toHaveLength(1)
    expect(cards[0].phase).toBe('live')
  })
})
