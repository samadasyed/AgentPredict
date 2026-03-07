import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { PredictionCard } from '../../components/predictions/PredictionCard'
import type { RagPrediction } from '../../types/rag'

const highConfPred: RagPrediction = {
  explanation: 'Odds shifted because Fighter A landed a massive combo in round 2.',
  evidence: [
    { text: 'Fighter A has 85% striking accuracy this round.', source_ref: 'market_events/x', score: 0.92 },
  ],
  confidence: 0.85,
  timestamp: Date.now(),
  trigger_event_id: 'ev-1',
}

const lowConfPred: RagPrediction = {
  explanation: 'Insufficient confidence to provide a reliable explanation.',
  evidence: [],
  confidence: 0.3,
  timestamp: Date.now(),
  trigger_event_id: 'ev-2',
}

describe('PredictionCard', () => {
  it('renders explanation text', () => {
    render(<PredictionCard prediction={highConfPred} />)
    expect(screen.getByText(/Odds shifted/)).toBeInTheDocument()
  })

  it('shows AI Analysis label', () => {
    render(<PredictionCard prediction={highConfPred} />)
    expect(screen.getByText('AI Analysis')).toBeInTheDocument()
  })

  it('shows confidence percentage', () => {
    render(<PredictionCard prediction={highConfPred} />)
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  it('shows evidence text', () => {
    render(<PredictionCard prediction={highConfPred} />)
    expect(screen.getByText(/Fighter A has 85%/)).toBeInTheDocument()
  })

  it('shows Evidence section header', () => {
    render(<PredictionCard prediction={highConfPred} />)
    expect(screen.getByText('Evidence')).toBeInTheDocument()
  })

  it('shows "No evidence retrieved" when evidence is empty', () => {
    render(<PredictionCard prediction={lowConfPred} />)
    expect(screen.getByText('No evidence retrieved.')).toBeInTheDocument()
  })

  it('renders low confidence percentage correctly', () => {
    render(<PredictionCard prediction={lowConfPred} />)
    expect(screen.getByText('30%')).toBeInTheDocument()
  })
})
