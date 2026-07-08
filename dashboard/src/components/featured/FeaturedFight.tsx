/**
 * Story-first hero — phase aware.
 *
 *  - upcoming: countdown to the fight, current implied odds, and the odds trend
 *    over the last week (so you can see how the line moved before the event).
 *  - live: a LIVE treatment with current odds plus a compact live-stat line for
 *    the two fighters, fused from the MMA stat stream.
 *
 * When the outcome parses as "A def. B" it renders a head-to-head odds bar.
 */

import type { MarketSeries } from '../../lib/marketSeries'
import type { LiveFight } from '../../lib/marketSeries'
import { matchupFor, parseFighters, formatCountdown, formatSpan } from '../../lib/marketSeries'
import { ProbabilityChart } from './ProbabilityChart'
import { STAT_LABELS, formatStatValue } from '../live/statLabels'

/** Surname-insensitive check that `name` refers to the same person as `fighter`. */
const sameFighter = (name: string, fighter: string): boolean => {
  const hay = fighter.toLowerCase()
  return name
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 2)
    .some((t) => hay.includes(t))
}

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

function PhaseChip({ series }: { series: MarketSeries }) {
  if (series.phase === 'live') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-rose-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
        Live now
      </span>
    )
  }
  if (series.phase === 'upcoming' && series.eventStart > 0) {
    return (
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-400">
        Upcoming · {formatCountdown(series.eventStart)}
      </span>
    )
  }
  return (
    <span className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-400">
      Featured market · live odds
    </span>
  )
}

/** Compact two-fighter line of headline live stats (sig. strikes, takedowns…). */
function LiveStatLine({ fight }: { fight: LiveFight }) {
  const [f1, f2] = fight.fighters
  const keys = ['significant_strikes', 'takedowns', 'knockdowns', 'control_time_seconds']
    .filter((k) => (f1?.stats[k] ?? 0) || (f2?.stats[k] ?? 0))

  if (!f1 || keys.length === 0) {
    return <p className="mt-4 text-sm text-slate-500">Awaiting live stats…</p>
  }
  return (
    <div className="mt-5 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3">
      <div className="mb-2 flex justify-between text-xs font-semibold text-slate-300">
        <span className="truncate">{f1.fighter}</span>
        <span className="px-2 text-slate-600">stat</span>
        <span className="truncate text-right">{f2?.fighter ?? '—'}</span>
      </div>
      <div className="space-y-1">
        {keys.map((k) => (
          <div key={k} className="grid grid-cols-3 items-center text-sm">
            <span className="font-mono font-bold text-white">{formatStatValue(k, f1.stats[k] ?? 0)}</span>
            <span className="text-center text-xs uppercase tracking-wide text-slate-500">{STAT_LABELS[k] ?? k}</span>
            <span className="text-right font-mono font-bold text-white">{formatStatValue(k, f2?.stats[k] ?? 0)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FeaturedFight({ series, liveFight }: { series: MarketSeries; liveFight?: LiveFight | null }) {
  const { latest, points, outcome, phase } = series
  const pct = (latest.probability * 100).toFixed(1)
  const up = latest.delta >= 0
  const matchup = matchupFor(series)
  let fighters = parseFighters(matchup)
  // `probability` tracks `outcome` (one fighter). Keep the odds bar's left side
  // aligned with that fighter even if the title names them second.
  if (fighters && !sameFighter(outcome, fighters[0]) && sameFighter(outcome, fighters[1])) {
    fighters = [fighters[1], fighters[0]]
  }
  const context = [series.cardTitle, series.fightInfo].filter(Boolean).join(' · ')
  const isLive = phase === 'live'

  const chartLabel = isLive
    ? 'Live odds'
    : series.historyStart > 0
      ? `Odds trend · last ${formatSpan(series.historyStart)}`
      : `Probability · last ${points.length} ticks`

  return (
    <section
      className={`rounded-2xl border bg-gradient-to-br p-6 shadow-xl ${
        isLive ? 'border-rose-500/30 from-rose-950/40 to-slate-900/40' : 'border-white/10 from-slate-900 to-slate-900/40'
      }`}
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Story side */}
        <div className="flex flex-col">
          <PhaseChip series={series} />
          <h2 className="mt-2 text-2xl font-semibold leading-snug text-white">{matchup}</h2>
          {context && <p className="mt-1 text-sm text-slate-400">{context}</p>}

          <div className="mt-auto pt-6">
            <div className="flex items-end gap-3">
              <span className="text-6xl font-bold tracking-tight text-white">{pct}%</span>
              <span className="pb-2 text-sm text-slate-400">
                {series.title ? `${outcome} to win` : 'implied'}
              </span>
              <span className="ml-auto pb-2"><DeltaPill delta={latest.delta} /></span>
            </div>
            {fighters && <OddsBar a={fighters[0]} b={fighters[1]} pa={latest.probability} />}
            {isLive && liveFight && <LiveStatLine fight={liveFight} />}
          </div>
        </div>

        {/* Chart side */}
        <div className="flex flex-col">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span className="uppercase tracking-widest">{chartLabel}</span>
            <span className="truncate pl-2 font-mono" title={series.marketId}>
              {series.cardTitle || series.marketId}
            </span>
          </div>
          <div className="h-48 flex-1">
            <ProbabilityChart points={points} up={up} showAxis />
          </div>
        </div>
      </div>
    </section>
  )
}
