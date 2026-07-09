/**
 * Stream 2 — RAG prediction feed. Always shows prediction + confidence + evidence.
 */

import type { RagPrediction } from '../../types/rag'
import { PredictionCard } from './PredictionCard'

interface PredictionFeedProps {
  predictions: RagPrediction[]
}

export function PredictionFeed({ predictions }: PredictionFeedProps) {
  return (
    <section className="flex flex-col rounded-2xl border border-white/5 bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400">AI Predictions</h2>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs font-mono text-slate-400">
          {predictions.length}
        </span>
      </div>
      <div className="max-h-[32rem] space-y-3 overflow-y-auto p-3">
        {predictions.length === 0 ? (
          <p className="px-1 py-6 text-center text-sm italic text-slate-600">
            AI analysis appears when a fight's odds make a real move.
          </p>
        ) : (
          predictions.map((pred) => (
            <PredictionCard key={`${pred.trigger_event_id}-${pred.timestamp}`} prediction={pred} />
          ))
        )}
      </div>
    </section>
  )
}
