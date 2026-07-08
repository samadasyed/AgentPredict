/**
 * useEventStream — manages WebSocket lifecycle and routes messages.
 *
 * Returns:
 *   events      — last MAX_EVENTS CanonicalEvents (Stream 1, factual)
 *   predictions — last MAX_PREDS  RagPredictions  (Stream 2, with evidence)
 *   connected   — current connection state
 *   error       — last parse/connection error message, or null
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { CanonicalEvent } from '../types/events'
import type { RagPrediction } from '../types/rag'

/** WS endpoint: explicit override for dev (gateway on another port), otherwise
 * derive from the page — behind TLS at agentpredictufc.com this yields
 * wss://<host>/ws, which the reverse proxy routes to the gateway. */
function gatewayWsUrl(): string {
  const override = import.meta.env.VITE_GATEWAY_WS_URL
  if (override) return override
  if (typeof window !== 'undefined' && window.location.host) {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${window.location.host}/ws`
  }
  return 'ws://localhost:8000/ws'
}
const GATEWAY_WS_URL = gatewayWsUrl()
const RECONNECT_DELAY_MS = 3_000
// Deep enough that a full fight slate's periodic re-baselines plus live-fight
// stat traffic coexist without evicting quiet markets between cycles.
const MAX_EVENTS = 400
const MAX_PREDS  = 50

export interface UseEventStreamResult {
  events:      CanonicalEvent[]
  predictions: RagPrediction[]
  connected:   boolean
  error:       string | null
}

export function useEventStream(): UseEventStreamResult {
  const [events,      setEvents]      = useState<CanonicalEvent[]>([])
  const [predictions, setPredictions] = useState<RagPrediction[]>([])
  const [connected,   setConnected]   = useState(false)
  const [error,       setError]       = useState<string | null>(null)

  const wsRef      = useRef<WebSocket | null>(null)
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    const ws = new WebSocket(GATEWAY_WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
      setError(null)
    }

    ws.onmessage = (msgEvent) => {
      if (!mountedRef.current) return
      try {
        const envelope = JSON.parse(msgEvent.data as string) as { type: string; data: unknown }

        if (envelope.type === 'event') {
          setEvents((prev) => {
            const incoming = envelope.data as CanonicalEvent
            // The gateway replays its recent buffer on every (re)connect; since we
            // reconnect on any close, dedup by event_id so replayed rows don't pile up.
            if (prev.some((e) => e.event_id === incoming.event_id)) return prev
            const next = [incoming, ...prev]
            return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next
          })
        } else if (envelope.type === 'prediction') {
          setPredictions((prev) => {
            const incoming = envelope.data as RagPrediction
            // RagPrediction has no id; a replay is identical in (trigger, timestamp).
            const key = (p: RagPrediction) => `${p.trigger_event_id}:${p.timestamp}`
            if (prev.some((p) => key(p) === key(incoming))) return prev
            const next = [incoming, ...prev]
            return next.length > MAX_PREDS ? next.slice(0, MAX_PREDS) : next
          })
        } else {
          setError(`Unknown message type: ${envelope.type}`)
        }
      } catch (e) {
        setError(`Malformed payload: ${(e as Error).message}`)
      }
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setError('WebSocket connection error')
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      // Reconnect after delay
      timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { events, predictions, connected, error }
}
