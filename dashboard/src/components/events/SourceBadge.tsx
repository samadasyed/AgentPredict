/**
 * Color-coded source pill — blue for Polymarket, orange for MMA.
 */

import type { EventSource } from '../../types/events'

interface SourceBadgeProps {
  source: EventSource
}

const BADGE_STYLES: Record<EventSource, { label: string; className: string }> = {
  SOURCE_POLYMARKET: {
    label: 'PM',
    className: 'bg-pm/20 text-pm border border-pm/40',
  },
  SOURCE_MMA: {
    label: 'MMA',
    className: 'bg-mma/20 text-mma border border-mma/40',
  },
  SOURCE_UNKNOWN: {
    label: '?',
    className: 'bg-gray-700 text-gray-400 border border-gray-600',
  },
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const { label, className } = BADGE_STYLES[source] ?? BADGE_STYLES.SOURCE_UNKNOWN
  return (
    <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded-full ${className}`}>
      {label}
    </span>
  )
}
