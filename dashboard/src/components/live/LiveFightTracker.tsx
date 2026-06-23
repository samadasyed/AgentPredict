/**
 * Live fight tracker — appears only while a fight is in progress.
 *
 * Top: a head-to-head scoreboard of the two fighters' cumulative stats.
 * Below: a real-time play-by-play of stat changes ("Sean O'Malley landed 6
 * significant strikes — 42 total"), derived from the MMA FightStatEvent stream.
 */

import type { LiveFight, FightStatUpdate } from '../../lib/marketSeries'
import { STAT_LABELS, STAT_VERBS, formatStatValue } from './statLabels'

const SCOREBOARD_STATS = ['significant_strikes', 'takedowns', 'knockdowns', 'control_time_seconds']
const MAX_PLAYS = 18

function relTime(ms: number): string {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000))
  if (s < 60) return `${s}s ago`
  return `${Math.floor(s / 60)}m ago`
}

function Scoreboard({ fight }: { fight: LiveFight }) {
  const [f1, f2] = fight.fighters
  if (!f1) return null
  return (
    <div className="rounded-xl border border-white/5 bg-slate-900/60 p-4">
      <div className="mb-3 grid grid-cols-3 items-center text-sm font-semibold text-white">
        <span className="truncate">{f1.fighter}</span>
        <span className="text-center text-xs uppercase tracking-widest text-rose-400">vs</span>
        <span className="truncate text-right">{f2?.fighter ?? '—'}</span>
      </div>
      <div className="space-y-1.5">
        {SCOREBOARD_STATS.map((k) => (
          <div key={k} className="grid grid-cols-3 items-center text-sm">
            <span className="font-mono font-bold text-orange-300">{formatStatValue(k, f1.stats[k] ?? 0)}</span>
            <span className="text-center text-[11px] uppercase tracking-wide text-slate-500">{STAT_LABELS[k] ?? k}</span>
            <span className="text-right font-mono font-bold text-sky-300">{formatStatValue(k, f2?.stats[k] ?? 0)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function playText(u: FightStatUpdate): string {
  const verb = STAT_VERBS[u.statType] ?? 'recorded'
  const label = STAT_LABELS[u.statType] ?? u.statType
  if (u.statType === 'control_time_seconds') {
    return `${u.fighter} ${verb} +${Math.round(u.delta)}s — ${formatStatValue(u.statType, u.value)} total`
  }
  return `${u.fighter} ${verb} ${Math.round(u.delta)} ${label} — ${Math.round(u.value)} total`
}

export function LiveFightTracker({
  fights,
  updates,
}: {
  fights: LiveFight[]
  updates: FightStatUpdate[]
}) {
  if (fights.length === 0) return null
  const liveIds = new Set(fights.map((f) => f.fightId))
  const plays = updates.filter((u) => liveIds.has(u.fightId) && u.delta > 0).slice(0, MAX_PLAYS)

  return (
    <section className="rounded-2xl border border-rose-500/20 bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-rose-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
          Live Fight Tracker
        </h2>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs font-mono text-slate-400">
          {fights.length} live
        </span>
      </div>

      <div className="space-y-4 p-4">
        {fights.slice(0, 2).map((f) => (
          <Scoreboard key={f.fightId} fight={f} />
        ))}

        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">Play-by-play</span>
          <ul className="mt-2 max-h-64 space-y-1.5 overflow-y-auto">
            {plays.length === 0 ? (
              <li className="py-4 text-center text-sm italic text-slate-600">Awaiting the next exchange…</li>
            ) : (
              plays.map((u) => (
                <li
                  key={u.eventId}
                  className="flex items-center justify-between gap-3 rounded-lg border border-white/5 bg-slate-900/60 px-3 py-2 text-sm"
                >
                  <span className="text-slate-200">{playText(u)}</span>
                  <span className="shrink-0 whitespace-nowrap font-mono text-xs text-slate-600">
                    {u.round > 0 ? `R${u.round} · ` : ''}{relTime(u.timestamp)}
                  </span>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </section>
  )
}
