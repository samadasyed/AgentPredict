/**
 * Single prediction card for Stream 2.
 * Shows: explanation + confidence bar + evidence (always visible).
 */

import type { RagPrediction } from '../../types/rag'
import { EvidenceList } from './EvidenceList'
import { formatClockTime } from '../../lib/time'

interface PredictionCardProps {
  prediction: RagPrediction
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const color =
    confidence > 0.7
      ? 'bg-confidence-high'
      : confidence >= 0.5
        ? 'bg-confidence-medium'
        : 'bg-gray-600'

  return (
    <div className="mt-1 flex items-center gap-2">
      <span className="text-xs text-slate-500">Confidence</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-700">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-300">{pct}%</span>
    </div>
  )
}

export function PredictionCard({ prediction }: PredictionCardProps) {
  const ts = formatClockTime(prediction.timestamp)

  return (
    <div className="space-y-2.5 rounded-xl border border-white/5 bg-slate-900/60 p-4 transition-colors hover:border-white/10">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-indigo-400">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
          AI Analysis
        </span>
        <span className="font-mono text-xs text-slate-600">{ts}</span>
      </div>

      <p className="text-sm leading-relaxed text-slate-100">{prediction.explanation}</p>

      <ConfidenceBar confidence={prediction.confidence} />

      <div className="border-t border-white/5 pt-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Evidence</span>
        <EvidenceList evidence={prediction.evidence} />
      </div>
    </div>
  )
}
