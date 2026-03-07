import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { EventCard } from '../../components/events/EventCard'
import type { CanonicalEvent } from '../../types/events'

const marketEvent: CanonicalEvent = {
  event_id: 'ev-pm-1',
  source: 'SOURCE_POLYMARKET',
  ingested_at: Date.now(),
  market_event: {
    market_id: 'mkt-abc',
    outcome: 'Fighter A wins',
    probability: 0.72,
    delta: 0.08,
    timestamp: Date.now(),
  },
}

const fightEvent: CanonicalEvent = {
  event_id: 'ev-mma-1',
  source: 'SOURCE_MMA',
  ingested_at: Date.now(),
  fight_event: {
    fight_id: 'fight-1',
    fighter_name: 'Fighter B',
    stat_type: 'significant_strikes',
    value: 42,
    round: 2,
    timestamp: Date.now(),
  },
}

describe('EventCard', () => {
  it('renders market outcome and probability', () => {
    render(<EventCard event={marketEvent} />)
    expect(screen.getByText('Fighter A wins')).toBeInTheDocument()
    expect(screen.getByText('72.0%')).toBeInTheDocument()
  })

  it('renders positive delta in green', () => {
    render(<EventCard event={marketEvent} />)
    const delta = screen.getByText('+8.00%')
    expect(delta).toHaveClass('text-green-400')
  })

  it('shows PM source badge for Polymarket event', () => {
    render(<EventCard event={marketEvent} />)
    expect(screen.getByText('PM')).toBeInTheDocument()
  })

  it('renders fighter name and stat type for fight event', () => {
    render(<EventCard event={fightEvent} />)
    expect(screen.getByText('Fighter B')).toBeInTheDocument()
    expect(screen.getByText('significant_strikes')).toBeInTheDocument()
  })

  it('shows MMA source badge for fight event', () => {
    render(<EventCard event={fightEvent} />)
    expect(screen.getByText('MMA')).toBeInTheDocument()
  })

  it('renders stat value', () => {
    render(<EventCard event={fightEvent} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders round indicator', () => {
    render(<EventCard event={fightEvent} />)
    expect(screen.getByText('R2')).toBeInTheDocument()
  })
})
