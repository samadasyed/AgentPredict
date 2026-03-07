/**
 * Stream 1 — factual event feed (left column).
 * No predictive language; only factual state changes.
 */

import type { CanonicalEvent } from '../../types/events'
import { EventCard } from './EventCard'

interface EventFeedProps {
  events: CanonicalEvent[]
}

export function EventFeed({ events }: EventFeedProps) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 px-1">
        Live Events
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-gray-600 italic px-1">Waiting for events…</p>
      ) : (
        events.map((ev) => <EventCard key={ev.event_id} event={ev} />)
      )}
    </section>
  )
}
