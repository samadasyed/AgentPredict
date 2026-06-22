/**
 * Headline hero for a fight that has no market yet (the real pre-event case:
 * BallDontLie has the card + date, Polymarket hasn't listed odds). Shows the
 * matchup, a large countdown, and the scheduled date — odds/stats slot in
 * automatically once they're available.
 */

import type { UpcomingFight } from '../../lib/fights'
import { parseFighters, formatCountdown } from '../../lib/marketSeries'

function eventDate(ms: number): string {
  if (!ms) return 'Date TBA'
  return new Date(ms).toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

export function UpcomingFightHero({ fight }: { fight: UpcomingFight }) {
  const fighters = parseFighters(fight.matchup)
  const isLive = fight.phase === 'live'

  return (
    <section className="rounded-2xl border border-amber-500/20 bg-gradient-to-br from-amber-950/30 to-slate-900/40 p-6 shadow-xl">
      <div className="flex flex-col items-center text-center">
        <span
          className={`text-xs font-semibold uppercase tracking-[0.2em] ${
            isLive ? 'text-rose-400' : 'text-amber-400'
          }`}
        >
          {isLive ? '● Live now' : 'Next up'} · {eventDate(fight.eventStart)}
        </span>

        {fighters ? (
          <h2 className="mt-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-3xl font-bold text-white">
            <span>{fighters[0]}</span>
            <span className="text-lg font-medium text-slate-500">vs</span>
            <span>{fighters[1]}</span>
          </h2>
        ) : (
          <h2 className="mt-3 text-3xl font-bold text-white">{fight.matchup}</h2>
        )}

        <div className="mt-5 text-5xl font-bold tracking-tight text-amber-300">
          {isLive ? 'In progress' : formatCountdown(fight.eventStart)}
        </div>

        <p className="mt-5 max-w-md text-sm text-slate-400">
          {isLive
            ? 'Round-by-round stats appear here when available on the data plan.'
            : 'Live odds and the probability trend appear here once this fight is listed on Polymarket.'}
        </p>
      </div>
    </section>
  )
}
