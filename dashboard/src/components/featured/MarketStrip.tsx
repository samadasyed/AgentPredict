/**
 * A responsive grid of market cards, each with a mini probability sparkline.
 * Gives an at-a-glance "what's moving" view above the raw feed.
 */

import type { MarketSeries } from '../../lib/marketSeries'
import { matchupFor } from '../../lib/marketSeries'
import { ProbabilityChart } from './ProbabilityChart'

function MarketCard({ s }: { s: MarketSeries }) {
  const pct = (s.latest.probability * 100).toFixed(0)
  const up = s.latest.delta >= 0
  const matchup = matchupFor(s)
  return (
    <div className="rounded-xl border border-white/5 bg-slate-900/60 p-4">
      <p className="truncate text-sm font-medium text-slate-200" title={matchup}>{matchup}</p>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-white">{pct}%</span>
        {s.title && <span className="truncate text-xs text-slate-500">{s.outcome}</span>}
        <span className={`text-xs font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
          {up ? '▲' : '▼'} {up ? '+' : ''}{(s.latest.delta * 100).toFixed(1)}
        </span>
      </div>
      <div className="mt-2 h-10">
        <ProbabilityChart points={s.points} up={up} height={40} />
      </div>
    </div>
  )
}

export function MarketStrip({ series }: { series: MarketSeries[] }) {
  if (series.length === 0) return null
  return (
    <section>
      <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
        Markets
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        {series.slice(0, 8).map((s) => (
          <MarketCard key={s.marketId} s={s} />
        ))}
      </div>
    </section>
  )
}
