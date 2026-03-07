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

const GATEWAY_WS_URL = import.meta.env.VITE_GATEWAY_WS_URL ?? 'ws://localhost:8000/ws'
const RECONNECT_DELAY_MS = 3_000
const MAX_EVENTS = 200
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
            const next = [envelope.data as CanonicalEvent, ...prev]
            return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next
          })
        } else if (envelope.type === 'prediction') {
          setPredictions((prev) => {
            const next = [envelope.data as RagPrediction, ...prev]
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
