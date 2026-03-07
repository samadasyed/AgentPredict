/**
 * Renders the evidence items that support a RAG prediction.
 * Always visible — never hidden (per dashboard rules).
 */

import type { EvidenceItem } from '../../types/rag'

interface EvidenceListProps {
  evidence: EvidenceItem[]
}

export function EvidenceList({ evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="text-xs text-gray-600 italic">No evidence retrieved.</p>
    )
  }

  return (
    <ul className="space-y-1 mt-1">
      {evidence.map((item, idx) => (
        <li key={idx} className="flex gap-2 text-xs text-gray-400">
          <span className="font-mono text-gray-600 shrink-0">
            [{(item.score * 100).toFixed(0)}%]
          </span>
          <span className="leading-relaxed">{item.text}</span>
        </li>
      ))}
    </ul>
  )
}
