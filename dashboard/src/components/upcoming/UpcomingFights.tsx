/**
 * Upcoming fights — the pre-event surface.
 *
 * Each card shows the matchup and a countdown. When a Polymarket market exists
 * for the fight it also shows the current odds and the week-long odds-trend
 * sparkline; otherwise it notes that odds aren't listed yet. Pairs with the AI
 * prediction feed, which explains *why* a listed line is moving.
 */

import type { UpcomingFight } from '../../lib/fights'
import { segmentRank } from '../../lib/fights'
import { parseFighters, formatCountdown, formatSpan, polymarketUrl } from '../../lib/marketSeries'
import { ProbabilityChart } from '../featured/ProbabilityChart'
import { PolymarketLink } from '../shared/PolymarketLink'

function FightCard({ f }: { f: UpcomingFight }) {
  const m = f.market
  const favorite = m?.outcome || parseFighters(f.matchup)?.[0] || null
  const up = (m?.latest.delta ?? 0) >= 0
  const isLive = f.phase === 'live'

  return (
    <div className="flex flex-col rounded-xl border border-white/5 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            isLive ? 'bg-rose-500/10 text-rose-400' : 'bg-amber-500/10 text-amber-400'
          }`}
        >
          {isLive ? '● live' : formatCountdown(f.eventStart)}
        </span>
        {m && (
          <span className={`text-xs font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
            {up ? '▲' : '▼'} {up ? '+' : ''}{(m.latest.delta * 100).toFixed(1)}
          </span>
        )}
      </div>

      <p className="mt-2 truncate text-sm font-semibold text-slate-100" title={f.matchup}>
        {f.matchup}
      </p>
      {m?.fightInfo && (
        <p className="truncate text-[11px] text-slate-500">{m.fightInfo}</p>
      )}

      {m ? (
        <>
          <div className="mt-1 flex items-baseline gap-2 text-xs text-slate-400">
            <span className="text-2xl font-bold text-white">{(m.latest.probability * 100).toFixed(0)}%</span>
            {favorite && <span className="truncate">{favorite}</span>}
          </div>
          <div className="mt-2 h-12">
            <ProbabilityChart points={m.points} up={up} height={48} />
          </div>
          <span className="mt-1 flex items-center justify-between text-[11px] uppercase tracking-widest text-slate-600">
            {m.historyStart > 0 ? `odds · last ${formatSpan(m.historyStart)}` : 'odds trend'}
            <PolymarketLink url={polymarketUrl(m)} className="normal-case tracking-normal" />
          </span>
        </>
      ) : (
        <div className="mt-2 flex h-[68px] items-center justify-center rounded-lg border border-dashed border-white/10 text-center text-xs text-slate-600">
          odds not yet listed
        </div>
      )}
    </div>
  )
}

/** Group fights by card (UFC 329, UFC Fight Night, …), preserving soonest-first
 * card order. Within a card, show the card in billing order — Main Card first,
 * then Prelims, then Early Prelims — and biggest market first within a segment.
 * Fights with no known card land in a trailing "More scheduled" group. */
function groupByCard(fights: UpcomingFight[]): [string, UpcomingFight[]][] {
  const groups = new Map<string, UpcomingFight[]>()
  for (const f of fights) {
    const key = f.cardTitle || ''
    const arr = groups.get(key)
    if (arr) arr.push(f)
    else groups.set(key, [f])
  }
  const entries = [...groups.entries()]
  // Known cards in first-seen (soonest) order; the untitled bucket last.
  entries.sort((a, b) => (a[0] === '' ? 1 : 0) - (b[0] === '' ? 1 : 0))
  for (const entry of entries) {
    entry[1] = [...entry[1]].sort(
      (a, b) =>
        segmentRank(a.market?.fightInfo) - segmentRank(b.market?.fightInfo) ||
        (b.market?.volume ?? 0) - (a.market?.volume ?? 0),
    )
  }
  return entries
}

export function UpcomingFights({ fights }: { fights: UpcomingFight[] }) {
  if (fights.length === 0) return null
  const groups = groupByCard(fights)
  return (
    <section className="space-y-4">
      {groups.map(([card, cardFights]) => (
        <div key={card || '(uncarded)'}>
          <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
            {card ? `${card} · Fight Card` : 'More Scheduled Fights'}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cardFights.map((f) => (
              <FightCard key={f.id} f={f} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
