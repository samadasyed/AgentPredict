/**
 * Stream 2 — RAG prediction feed (right column).
 * Always shows evidence; always shows prediction + confidence.
 */

import type { RagPrediction } from '../../types/rag'
import { PredictionCard } from './PredictionCard'

interface PredictionFeedProps {
  predictions: RagPrediction[]
}

export function PredictionFeed({ predictions }: PredictionFeedProps) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 px-1">
        AI Predictions
      </h2>
      {predictions.length === 0 ? (
        <p className="text-sm text-gray-600 italic px-1">Waiting for analysis…</p>
      ) : (
        predictions.map((pred) => (
          <PredictionCard key={`${pred.trigger_event_id}-${pred.timestamp}`} prediction={pred} />
        ))
      )}
    </section>
  )
}
