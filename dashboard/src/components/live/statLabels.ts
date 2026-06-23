/** Human labels + formatting for MMA fight-stat types (proto `stat_type`). */

export const STAT_LABELS: Record<string, string> = {
  significant_strikes: 'sig. strikes',
  takedowns: 'takedowns',
  knockdowns: 'knockdowns',
  control_time_seconds: 'control',
}

/** Verb used in the play-by-play, e.g. "landed 6 sig. strikes". */
export const STAT_VERBS: Record<string, string> = {
  significant_strikes: 'landed',
  takedowns: 'landed',
  knockdowns: 'scored',
  control_time_seconds: 'controlled',
}

/** Format a stat value — control time is seconds → m:ss, everything else raw. */
export function formatStatValue(statType: string, value: number): string {
  if (statType === 'control_time_seconds') {
    const s = Math.max(0, Math.round(value))
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }
  return String(Math.round(value))
}
