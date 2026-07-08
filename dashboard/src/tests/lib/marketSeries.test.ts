import { describe, it, expect } from 'vitest'
import type { CanonicalEvent, MarketEvent, FightStatEvent } from '../../types/events'
import {
  buildMarketSeries,
  classifyPhase,
  pickFeatured,
  upcomingFights,
  buildLiveFights,
  buildFightUpdates,
  findFightForOutcome,
  formatCountdown,
  matchupFor,
} from '../../lib/marketSeries'

let seq = 0
function market(m: Partial<MarketEvent> & Pick<MarketEvent, 'market_id' | 'probability'>): CanonicalEvent {
  return {
    event_id: `m${seq++}`,
    source: 'SOURCE_POLYMARKET',
    ingested_at: 0,
    market_event: { outcome: 'A def. B', delta: 0, timestamp: seq, ...m } as MarketEvent,
  }
}
function fight(f: Partial<FightStatEvent> & Pick<FightStatEvent, 'fight_id' | 'fighter_name' | 'stat_type' | 'value'>): CanonicalEvent {
  return {
    event_id: `f${seq++}`,
    source: 'SOURCE_MMA',
    ingested_at: 0,
    fight_event: { round: 0, timestamp: seq, ...f } as FightStatEvent,
  }
}
/** The hook stores newest-first; build chronologically then reverse. */
const newestFirst = (chrono: CanonicalEvent[]) => [...chrono].reverse()

describe('buildMarketSeries', () => {
  it('seeds the line from history then appends live ticks', () => {
    const events = newestFirst([
      market({ market_id: 'm1', probability: 0.5, phase: 'live', event_start: 1,
               history: [{ timestamp: 10, probability: 0.4 }, { timestamp: 20, probability: 0.5 }] }),
      market({ market_id: 'm1', probability: 0.52 }),
      market({ market_id: 'm1', probability: 0.55, delta: 0.03 }),
    ])
    const [s] = buildMarketSeries(events)
    expect(s.points).toEqual([0.4, 0.5, 0.5, 0.52, 0.55])
    expect(s.phase).toBe('live')
    expect(s.historyStart).toBe(10)
    expect(s.latest.probability).toBe(0.55)
  })

  it('coerces wire-string int64 event_start to a number', () => {
    const events = newestFirst([
      market({ market_id: 'm2', probability: 0.6, event_start: '1900000000000' as unknown as number }),
    ])
    const [s] = buildMarketSeries(events)
    expect(s.eventStart).toBe(1_900_000_000_000)
  })

  it('carries fight metadata from the most recent event that has it', () => {
    const events = newestFirst([
      market({ market_id: 'm3', probability: 0.66, outcome: 'Max Holloway',
               title: 'Max Holloway vs. Conor McGregor', card_title: 'UFC 329',
               fight_info: 'Welterweight · Main Card', volume: 1_464_663 }),
      market({ market_id: 'm3', probability: 0.68 }),   // partial tick, no metadata
    ])
    const [s] = buildMarketSeries(events)
    expect(s.title).toBe('Max Holloway vs. Conor McGregor')
    expect(s.cardTitle).toBe('UFC 329')
    expect(s.fightInfo).toBe('Welterweight · Main Card')
    expect(s.volume).toBe(1_464_663)
    expect(matchupFor(s)).toBe('Max Holloway vs. Conor McGregor')
  })
})

describe('classifyPhase', () => {
  const base: MarketEvent = { market_id: 'x', outcome: '', probability: 0.5, delta: 0, timestamp: 0 }
  it('trusts an explicit phase', () => {
    expect(classifyPhase({ ...base, phase: 'final' }, 0)).toBe('final')
  })
  it('derives upcoming/live from the schedule', () => {
    expect(classifyPhase(base, Date.now() + 86_400_000)).toBe('upcoming')
    expect(classifyPhase(base, Date.now() - 86_400_000)).toBe('live')
  })
  it('is unknown with no phase and no schedule', () => {
    expect(classifyPhase(base, 0)).toBe('unknown')
  })
})

describe('pickFeatured / upcomingFights', () => {
  it('prefers a live fight over upcoming ones', () => {
    const series = buildMarketSeries(newestFirst([
      market({ market_id: 'up', probability: 0.5, phase: 'upcoming', event_start: Date.now() + 2 * 86_400_000 }),
      market({ market_id: 'live', probability: 0.5, phase: 'live', event_start: Date.now() - 600_000 }),
    ]))
    expect(pickFeatured(series)?.marketId).toBe('live')
  })
  it('otherwise features the soonest upcoming fight', () => {
    const now = Date.now()
    const series = buildMarketSeries(newestFirst([
      market({ market_id: 'far', probability: 0.5, phase: 'upcoming', event_start: now + 5 * 86_400_000 }),
      market({ market_id: 'soon', probability: 0.5, phase: 'upcoming', event_start: now + 1 * 86_400_000 }),
    ]))
    expect(pickFeatured(series)?.marketId).toBe('soon')
    expect(upcomingFights(series).map((s) => s.marketId)).toEqual(['soon', 'far'])
  })

  it('headlines the main event (biggest volume) among same-card fights', () => {
    const now = Date.now()
    // A real card: prelims start an hour before the main event, but the main
    // event has 100x the volume — it must lead, not the earliest prelim.
    const series = buildMarketSeries(newestFirst([
      market({ market_id: 'prelim', probability: 0.5, phase: 'upcoming',
               event_start: now + 2 * 86_400_000, volume: 12_000 }),
      market({ market_id: 'main', probability: 0.66, phase: 'upcoming',
               event_start: now + 2 * 86_400_000 + 3_600_000, volume: 1_400_000 }),
      market({ market_id: 'next-week', probability: 0.5, phase: 'upcoming',
               event_start: now + 9 * 86_400_000, volume: 9_000_000 }),
    ]))
    expect(pickFeatured(series)?.marketId).toBe('main')
  })
})

describe('live fight aggregation', () => {
  const events = newestFirst([
    fight({ fight_id: 'f1', fighter_name: 'Sean O\'Malley', stat_type: 'FIGHT_DISCOVERED', value: 0 }),
    fight({ fight_id: 'f1', fighter_name: 'Sean O\'Malley', stat_type: 'significant_strikes', value: 10 }),
    fight({ fight_id: 'f1', fighter_name: 'Merab Dvalishvili', stat_type: 'significant_strikes', value: 8 }),
    fight({ fight_id: 'f1', fighter_name: 'Sean O\'Malley', stat_type: 'significant_strikes', value: 16 }),
  ])

  it('aggregates per-fighter cumulative totals (ignoring FIGHT_DISCOVERED)', () => {
    const [lf] = buildLiveFights(events)
    expect(lf.fightId).toBe('f1')
    const omalley = lf.fighters.find((f) => f.fighter.includes('Malley'))!
    expect(omalley.stats.significant_strikes).toBe(16)
    expect(lf.fighters).toHaveLength(2)
  })

  it('computes play-by-play deltas, newest first', () => {
    const updates = buildFightUpdates(events).filter((u) => u.fighter.includes('Malley'))
    expect(updates[0].value).toBe(16)
    expect(updates[0].delta).toBe(6)   // 16 - 10
    expect(updates[updates.length - 1].delta).toBe(10)  // first reading
  })

  it('links a live fight to a market outcome by fighter name', () => {
    const fights = buildLiveFights(events)
    expect(findFightForOutcome(fights, "Sean O'Malley def. Merab Dvalishvili")?.fightId).toBe('f1')
    expect(findFightForOutcome(fights, 'Jon Jones def. Tom Aspinall')).toBeNull()
  })

  it('ignores FIGHT_UPCOMING/FIGHT_DISCOVERED sentinels (not live fights)', () => {
    const sentinels = newestFirst([
      fight({ fight_id: 'sched', fighter_name: 'McGregor vs. Holloway 2', stat_type: 'FIGHT_UPCOMING', value: 0 }),
      fight({ fight_id: 'disc', fighter_name: 'A vs B', stat_type: 'FIGHT_DISCOVERED', value: 0 }),
    ])
    expect(buildLiveFights(sentinels)).toHaveLength(0)
    expect(buildFightUpdates(sentinels)).toHaveLength(0)
  })
})

describe('formatCountdown', () => {
  it('formats days/hours/minutes and handles started events', () => {
    expect(formatCountdown(26 * 3_600_000, 0)).toBe('in 1d 2h')
    expect(formatCountdown(3 * 3_600_000 + 12 * 60_000, 0)).toBe('in 3h 12m')
    expect(formatCountdown(8 * 60_000, 0)).toBe('in 8m')
    expect(formatCountdown(-1, 0)).toBe('starting now')
  })
})
