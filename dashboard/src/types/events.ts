/**
 * TypeScript mirrors of proto/events.proto message shapes.
 * These match the JSON produced by google.protobuf.json_format.MessageToDict.
 */

export type EventSource = 'SOURCE_UNKNOWN' | 'SOURCE_POLYMARKET' | 'SOURCE_MMA'

export interface MarketEvent {
  market_id: string
  outcome: string
  probability: number  // [0, 1]
  delta: number        // signed change
  timestamp: number    // unix millis
}

export interface FightStatEvent {
  fight_id: string
  fighter_name: string
  stat_type: string
  value: number
  round: number
  timestamp: number    // unix millis
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
