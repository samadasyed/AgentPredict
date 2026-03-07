/**
 * Tests for useEventStream hook — mocks WebSocket globally.
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useEventStream } from '../../hooks/useEventStream'

// ─── Mock WebSocket ───────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen:    ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror:   ((e: Event) => void) | null = null
  onclose:   ((e: CloseEvent) => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(_data: string) {}
  close() { this.onclose?.(new CloseEvent('close')) }

  // Test helpers
  simulateOpen()    { this.onopen?.(new Event('open')) }
  simulateMessage(data: object) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
  simulateError()   { this.onerror?.(new Event('error')) }
  simulateClose()   { this.onclose?.(new CloseEvent('close')) }
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useEventStream', () => {
  it('starts as disconnected', () => {
    const { result } = renderHook(() => useEventStream())
    expect(result.current.connected).toBe(false)
  })

  it('becomes connected on ws.onopen', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    expect(result.current.connected).toBe(true)
    expect(result.current.error).toBeNull()
  })

  it('routes event messages to events array', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    act(() =>
      MockWebSocket.instances[0].simulateMessage({
        type: 'event',
        data: {
          event_id: 'ev-1',
          source: 'SOURCE_POLYMARKET',
          ingested_at: 1000,
          market_event: { market_id: 'mkt-1', outcome: 'A wins', probability: 0.6, delta: 0.05, timestamp: 1000 },
        },
      })
    )
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0].event_id).toBe('ev-1')
    expect(result.current.predictions).toHaveLength(0)
  })

  it('routes prediction messages to predictions array', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    act(() =>
      MockWebSocket.instances[0].simulateMessage({
        type: 'prediction',
        data: {
          explanation: 'Odds moved.',
          evidence: [],
          confidence: 0.8,
          timestamp: 2000,
          trigger_event_id: 'ev-1',
        },
      })
    )
    expect(result.current.predictions).toHaveLength(1)
    expect(result.current.events).toHaveLength(0)
  })

  it('sets error on malformed JSON', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    act(() =>
      MockWebSocket.instances[0].onmessage?.(
        new MessageEvent('message', { data: 'not-json!!!' })
      )
    )
    expect(result.current.error).toContain('Malformed payload')
  })

  it('sets error on unknown message type', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    act(() =>
      MockWebSocket.instances[0].simulateMessage({ type: 'mystery', data: {} })
    )
    expect(result.current.error).toContain('Unknown message type')
  })

  it('sets disconnected on ws.onclose', () => {
    const { result } = renderHook(() => useEventStream())
    act(() => MockWebSocket.instances[0].simulateOpen())
    act(() => MockWebSocket.instances[0].simulateClose())
    expect(result.current.connected).toBe(false)
  })
})
