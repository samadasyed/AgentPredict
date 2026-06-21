/**
 * Story-first hero: the market that's moving most right now.
 * Shows the matchup (or outcome), the live implied probability, the move, and a
 * full probability chart. When the outcome parses as "A def. B" it renders a
 * head-to-head odds bar.
 */

import type { MarketSeries } from '../../lib/marketSeries'
import { parseFighters } from '../../lib/marketSeries'
import { ProbabilityChart } from './ProbabilityChart'

function DeltaPill({ delta }: { delta: number }) {
  const up = delta >= 0
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-semibold ${
        up ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
      }`}
    >
      {up ? '▲' : '▼'} {up ? '+' : ''}{(delta * 100).toFixed(1)} pts
    </span>
  )
}

function OddsBar({ a, b, pa }: { a: string; b: string; pa: number }) {
  const aPct = Math.round(pa * 100)
  return (
    <div className="mt-5">
      <div className="flex justify-between text-sm font-medium text-slate-300">
        <span className="truncate pr-2">{a}</span>
        <span className="truncate pl-2 text-slate-400">{b}</span>
      </div>
      <div className="mt-1.5 flex h-2.5 overflow-hidden rounded-full bg-slate-700/60">
        <div className="bg-emerald-400/80" style={{ width: `${aPct}%` }} />
        <div className="bg-sky-400/60" style={{ width: `${100 - aPct}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-xs font-mono text-slate-500">
        <span>{aPct}%</span>
        <span>{100 - aPct}%</span>
      </div>
    </div>
  )
}

export function FeaturedFight({ series }: { series: MarketSeries }) {
  const { latest, points, outcome } = series
  const pct = (latest.probability * 100).toFixed(1)
  const up = latest.delta >= 0
  const fighters = parseFighters(outcome)

  return (
    <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900 to-slate-900/40 p-6 shadow-xl">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Story side */}
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-400">
            Featured market · live odds
          </span>
          <h2 className="mt-2 text-2xl font-semibold leading-snug text-white">{outcome}</h2>

          <div className="mt-auto pt-6">
            <div className="flex items-end gap-3">
              <span className="text-6xl font-bold tracking-tight text-white">{pct}%</span>
              <span className="pb-2 text-sm text-slate-400">implied</span>
              <span className="ml-auto pb-2"><DeltaPill delta={latest.delta} /></span>
            </div>
            {fighters && <OddsBar a={fighters[0]} b={fighters[1]} pa={latest.probability} />}
          </div>
        </div>

        {/* Chart side */}
        <div className="flex flex-col">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span className="uppercase tracking-widest">Probability · last {points.length} ticks</span>
            <span className="font-mono">{series.marketId}</span>
          </div>
          <div className="h-48 flex-1">
            <ProbabilityChart points={points} up={up} showAxis />
          </div>
        </div>
      </div>
    </section>
  )
}
