/**
 * Single event card for Stream 1 (factual only — no predictive language).
 */

import type { CanonicalEvent } from '../../types/events'
import { SourceBadge } from './SourceBadge'

interface EventCardProps {
  event: CanonicalEvent
}

function formatTs(ms: number): string {
  return new Date(ms).toLocaleTimeString()
}

function EventBody({ event }: { event: CanonicalEvent }) {
  if (event.market_event) {
    const m = event.market_event
    const pct = (m.probability * 100).toFixed(1)
    const deltaSign = m.delta >= 0 ? '+' : ''
    const deltaPct = (m.delta * 100).toFixed(2)
    return (
      <div className="text-sm text-gray-200">
        <span className="font-medium">{m.outcome}</span>
        <span className="ml-2 text-gray-400">→</span>
        <span className="ml-2 font-mono font-bold">{pct}%</span>
        <span
          className={`ml-2 font-mono text-xs ${
            m.delta >= 0 ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {deltaSign}{deltaPct}%
        </span>
        <span className="block text-xs text-gray-500 mt-0.5 font-mono truncate">
          {m.market_id}
        </span>
      </div>
    )
  }

  if (event.fight_event) {
    const f = event.fight_event
    return (
      <div className="text-sm text-gray-200">
        <span className="font-medium">{f.fighter_name}</span>
        <span className="mx-2 text-gray-500">·</span>
        <span className="text-gray-300">{f.stat_type}</span>
        {f.value > 0 && (
          <span className="ml-2 font-mono font-bold text-orange-300">{f.value}</span>
        )}
        {f.round > 0 && (
          <span className="ml-2 text-xs text-gray-500">R{f.round}</span>
        )}
      </div>
    )
  }

  return <div className="text-xs text-gray-500 italic">Unknown event payload</div>
}

export function EventCard({ event }: EventCardProps) {
  const ts = event.market_event?.timestamp ?? event.fight_event?.timestamp ?? event.ingested_at

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 flex gap-3 items-start">
      <SourceBadge source={event.source} />
      <div className="flex-1 min-w-0">
        <EventBody event={event} />
      </div>
      <span className="text-xs text-gray-600 font-mono whitespace-nowrap">
        {formatTs(ts)}
      </span>
    </div>
  )
}
