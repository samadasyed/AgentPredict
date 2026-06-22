/**
 * TypeScript mirrors of proto/events.proto message shapes.
 * These match the JSON produced by google.protobuf.json_format.MessageToDict.
 */

export type EventSource = 'SOURCE_UNKNOWN' | 'SOURCE_POLYMARKET' | 'SOURCE_MMA'

/** One point on a market's probability trajectory (shipped as a snapshot). */
export interface ProbabilityPoint {
  timestamp: number    // unix millis (arrives as a string on the wire — coerce)
  probability: number  // [0, 1]
}

export interface MarketEvent {
  market_id: string
  outcome: string
  probability: number  // [0, 1]
  delta: number        // signed change
  timestamp: number    // unix millis
  history?: ProbabilityPoint[]  // recent trajectory (pre-event odds trend)
  event_start?: number          // scheduled start of the fight, unix millis (0 = unknown)
  phase?: string                // "upcoming" | "live" | "final" | "" (unknown)
}

export interface FightStatEvent {
  fight_id: string
  fighter_name: string  // a fighter, or the headline matchup for schedule events
  stat_type: string     // stat name; sentinels: "FIGHT_DISCOVERED", "FIGHT_UPCOMING"
  value: number
  round: number
  timestamp: number    // unix millis
  event_start?: number  // scheduled card start, unix millis (0 = unknown)
  phase?: string        // "upcoming" | "live" | "final" | "" (unknown)
}

export interface CanonicalEvent {
  event_id: string
  source: EventSource
  ingested_at: number  // unix millis
  market_event?: MarketEvent
  fight_event?: FightStatEvent
}

/** Wrapper envelope from the gateway WebSocket. */
export interface EventMessage {
  type: 'event'
  data: CanonicalEvent
}
