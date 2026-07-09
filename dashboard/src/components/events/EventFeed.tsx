/**
 * Stream 1 — factual event feed. No predictive language; only state changes.
 */

import type { CanonicalEvent } from '../../types/events'
import { EventCard } from './EventCard'
import { InfoHint } from '../shared/InfoHint'

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
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Live Events</h2>
          <InfoHint label="What is the Live Events feed?">
            <p className="font-semibold text-slate-100">The raw, factual feed.</p>
            <p className="mt-2">
              Every event streams in here exactly as it arrives, with no interpretation:
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-4">
              <li>
                <span className="text-slate-100">Odds ticks</span> — a fight's implied win
                probability on Polymarket changed. Each row shows the new probability and
                the size of the move.
              </li>
              <li>
                <span className="text-slate-100">Fight stats</span> — during live fights,
                per-fighter numbers (significant strikes, takedowns, knockdowns, control
                time) as they're recorded.
              </li>
            </ul>
            <p className="mt-2 text-slate-400">
              This is the evidence stream. The AI Predictions panel is where interpretation
              happens — it works from exactly this data.
            </p>
          </InfoHint>
        </div>
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
