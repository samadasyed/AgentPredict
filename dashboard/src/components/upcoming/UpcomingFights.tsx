/**
 * Upcoming fights — the pre-event surface.
 *
 * Each card shows the matchup, the current implied odds, how the line has moved
 * over the last week (sparkline), and a countdown to the fight. Pairs with the
 * AI prediction feed, which explains *why* the line is moving.
 */

import type { MarketSeries } from '../../lib/marketSeries'
import { parseFighters, formatCountdown, formatSpan } from '../../lib/marketSeries'
import { ProbabilityChart } from '../featured/ProbabilityChart'

function FightCard({ s }: { s: MarketSeries }) {
  const pct = (s.latest.probability * 100).toFixed(0)
  const up = s.latest.delta >= 0
  const fighters = parseFighters(s.outcome)

  return (
    <div className="flex flex-col rounded-xl border border-white/5 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-400">
          {formatCountdown(s.eventStart)}
        </span>
        <span className={`text-xs font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
          {up ? '▲' : '▼'} {up ? '+' : ''}{(s.latest.delta * 100).toFixed(1)}
        </span>
      </div>

      <p className="mt-2 truncate text-sm font-semibold text-slate-100" title={s.outcome}>
        {s.outcome}
      </p>

      {fighters ? (
        <div className="mt-1 flex items-baseline gap-2 text-xs text-slate-400">
          <span className="text-2xl font-bold text-white">{pct}%</span>
          <span className="truncate">{fighters[0]}</span>
        </div>
      ) : (
        <div className="mt-1 text-2xl font-bold text-white">{pct}%</div>
      )}

      <div className="mt-2 h-12">
        <ProbabilityChart points={s.points} up={up} height={48} />
      </div>
      <span className="mt-1 text-[11px] uppercase tracking-widest text-slate-600">
        {s.historyStart > 0 ? `odds · last ${formatSpan(s.historyStart)}` : 'odds trend'}
      </span>
    </div>
  )
}

export function UpcomingFights({ series }: { series: MarketSeries[] }) {
  if (series.length === 0) return null
  return (
    <section>
      <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
        Upcoming Fights
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {series.map((s) => (
          <FightCard key={s.marketId} s={s} />
        ))}
      </div>
    </section>
  )
}
