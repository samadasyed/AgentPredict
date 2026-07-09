/**
 * Stream 2 — RAG prediction feed. Always shows prediction + confidence + evidence.
 */

import type { RagPrediction } from '../../types/rag'
import { PredictionCard } from './PredictionCard'
import { InfoHint } from '../shared/InfoHint'

interface PredictionFeedProps {
  predictions: RagPrediction[]
}

export function PredictionFeed({ predictions }: PredictionFeedProps) {
  return (
    <section className="flex flex-col rounded-2xl border border-white/5 bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400">AI Predictions</h2>
          <InfoHint label="How do AI Predictions work?">
            <p className="font-semibold text-slate-100">Under the hood</p>
            <ol className="mt-2 list-decimal space-y-1.5 pl-4">
              <li>
                <span className="text-slate-100">Trigger.</span> The system watches every
                odds tick. When a fight's win probability has moved ≥2 points since its
                last analysis — one sharp jump or a slow drift — one analysis runs.
                Each fight is analyzed at most once per 90 seconds.
              </li>
              <li>
                <span className="text-slate-100">Context.</span> It gathers the most
                recent market moves and live fight stats (the Live Events feed).
              </li>
              <li>
                <span className="text-slate-100">Evidence.</span> Past events are stored
                as vectors in a search index (Pinecone); the most similar ones to this
                move are retrieved and attached as the evidence you see on each card.
              </li>
              <li>
                <span className="text-slate-100">Explanation.</span> A language model
                (Google Gemini) writes a 2–3 sentence explanation grounded only in that
                data, and scores its own confidence. It's instructed to never invent
                injuries, news, or fight action — if the data doesn't support a cause,
                it says the move looks like normal market repricing.
              </li>
              <li>
                <span className="text-slate-100">Verification.</span> A checker rejects
                the result unless confidence is at least 50% and the text actually
                references the fighters involved. Only passing analyses appear here.
              </li>
            </ol>
            <p className="mt-2 text-slate-400">
              These are explanations of market moves, not betting advice.
            </p>
          </InfoHint>
        </div>
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
