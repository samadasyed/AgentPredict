/**
 * Stream 1 — factual event feed. No predictive language; only state changes.
 */

import type { CanonicalEvent } from '../../types/events'
import { EventCard } from './EventCard'

interface EventFeedProps {
  events: CanonicalEvent[]
}

// Schedule/discovery markers aren't factual state changes — keep them out of the feed.
const SENTINELS = new Set(['FIGHT_UPCOMING', 'FIGHT_DISCOVERED'])
const isSentinel = (e: CanonicalEvent) => !!e.fight_event && SENTINELS.has(e.fight_event.stat_type)

export function EventFeed({ events: allEvents }: EventFeedProps) {
  const events = allEvents.filter((e) => !isSentinel(e))
  return (
    <section className="flex flex-col rounded-2xl border border-white/5 bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Live Events</h2>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs font-mono text-slate-400">
          {events.length}
        </span>
      </div>
      <div className="max-h-[32rem] space-y-2 overflow-y-auto p-3">
        {events.length === 0 ? (
          <p className="px-1 py-6 text-center text-sm italic text-slate-600">Waiting for events…</p>
        ) : (
          events.map((ev) => <EventCard key={ev.event_id} event={ev} />)
        )}
      </div>
    </section>
  )
}
