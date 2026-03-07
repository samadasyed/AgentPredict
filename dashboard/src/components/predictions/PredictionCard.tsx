/**
 * Single prediction card for Stream 2.
 * Shows: explanation + confidence bar + evidence (always visible).
 */

import type { RagPrediction } from '../../types/rag'
import { EvidenceList } from './EvidenceList'

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
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-400">{pct}%</span>
    </div>
  )
}

export function PredictionCard({ prediction }: PredictionCardProps) {
  const ts = new Date(prediction.timestamp).toLocaleTimeString()

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
          AI Analysis
        </span>
        <span className="text-xs text-gray-600 font-mono">{ts}</span>
      </div>

      {/* Explanation */}
      <p className="text-sm text-gray-200 leading-relaxed">{prediction.explanation}</p>

      {/* Confidence */}
      <ConfidenceBar confidence={prediction.confidence} />

      {/* Evidence — always shown */}
      <div className="border-t border-gray-700 pt-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Evidence
        </span>
        <EvidenceList evidence={prediction.evidence} />
      </div>
    </div>
  )
}
