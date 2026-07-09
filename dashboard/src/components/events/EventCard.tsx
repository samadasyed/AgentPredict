/**
 * Single event card for Stream 1 (factual only — no predictive language).
 */

import type { CanonicalEvent } from '../../types/events'
import { SourceBadge } from './SourceBadge'
import { formatClockTime } from '../../lib/time'

interface EventCardProps {
  event: CanonicalEvent
}

function EventBody({ event }: { event: CanonicalEvent }) {
  if (event.market_event) {
    const m = event.market_event
    const pct = (m.probability * 100).toFixed(1)
    const deltaSign = m.delta >= 0 ? '+' : ''
    const deltaPct = (m.delta * 100).toFixed(2)
    return (
      <div className="text-sm text-slate-200">
        <span className="font-medium">{m.title || m.outcome}</span>
        <div className="mt-1 flex items-center gap-2">
          <span className="font-mono font-bold text-white">{pct}%</span>
          <span
            className={`font-mono text-xs ${m.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}
          >
            {deltaSign}{deltaPct}%
          </span>
          <span className="truncate font-mono text-xs text-slate-600" title={m.market_id}>
            {m.title ? `${m.outcome}${m.card_title ? ` · ${m.card_title}` : ''}` : m.market_id}
          </span>
        </div>
      </div>
    )
  }

  if (event.fight_event) {
    const f = event.fight_event
    return (
      <div className="text-sm text-slate-200">
        <span className="font-medium">{f.fighter_name}</span>
        <span className="mx-2 text-slate-500">·</span>
        <span className="text-slate-300">{f.stat_type}</span>
        {f.value > 0 && (
          <span className="ml-2 font-mono font-bold text-orange-300">{f.value}</span>
        )}
        {f.round > 0 && <span className="ml-2 text-xs text-slate-500">R{f.round}</span>}
      </div>
    )
  }

  return <div className="text-xs italic text-slate-500">Unknown event payload</div>
}

export function EventCard({ event }: EventCardProps) {
  const ts = event.market_event?.timestamp ?? event.fight_event?.timestamp ?? event.ingested_at

  return (
    <div className="flex items-start gap-3 rounded-xl border border-white/5 bg-slate-900/60 px-3.5 py-2.5 transition-colors hover:border-white/10">
      <SourceBadge source={event.source} />
      <div className="min-w-0 flex-1">
        <EventBody event={event} />
      </div>
      <span className="whitespace-nowrap font-mono text-xs text-slate-600">{formatClockTime(ts)}</span>
    </div>
  )
}
