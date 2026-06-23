import { useMemo } from 'react'
import { useEventStream } from './hooks/useEventStream'
import { Header } from './components/layout/Header'
import { FeaturedFight } from './components/featured/FeaturedFight'
import { MarketStrip } from './components/featured/MarketStrip'
import { UpcomingFights } from './components/upcoming/UpcomingFights'
import { UpcomingFightHero } from './components/upcoming/UpcomingFightHero'
import { LiveFightTracker } from './components/live/LiveFightTracker'
import { EventFeed } from './components/events/EventFeed'
import { PredictionFeed } from './components/predictions/PredictionFeed'
import { StreamWarning } from './components/shared/StreamWarning'
import {
  buildMarketSeries,
  pickFeatured,
  sortByRecent,
  buildLiveFights,
  buildFightUpdates,
  findFightForOutcome,
} from './lib/marketSeries'
import { buildUpcomingFights } from './lib/fights'

export default function App() {
  const { events, predictions, connected, error } = useEventStream()

  const series = useMemo(() => buildMarketSeries(events), [events])
  const featured = useMemo(() => pickFeatured(series), [series])
  const movers = useMemo(() => sortByRecent(series), [series])
  const upcoming = useMemo(() => buildUpcomingFights(events, series), [events, series])

  const liveFights = useMemo(() => buildLiveFights(events), [events])
  const fightUpdates = useMemo(() => buildFightUpdates(events), [events])
  const featuredFight = useMemo(
    () => (featured ? findFightForOutcome(liveFights, featured.outcome) : null),
    [featured, liveFights],
  )

  // The market hero takes priority; otherwise headline the soonest upcoming fight.
  const heroFight = !featured && upcoming.length > 0 ? upcoming[0] : null
  const upcomingList = useMemo(
    () =>
      upcoming.filter(
        (f) =>
          f.id !== heroFight?.id &&
          !(featured?.marketId && f.market?.marketId === featured.marketId),
      ),
    [upcoming, heroFight, featured],
  )

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 antialiased">
      <Header connected={connected} />

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {!connected && (
          <StreamWarning message="WebSocket disconnected — attempting to reconnect…" />
        )}
        {error && <StreamWarning message={error} />}

        {featured ? (
          <FeaturedFight series={featured} liveFight={featuredFight} />
        ) : heroFight ? (
          <UpcomingFightHero fight={heroFight} />
        ) : (
          <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-10 text-center text-slate-500">
            Waiting for fights…
          </div>
        )}

        {liveFights.length > 0 && (
          <LiveFightTracker fights={liveFights} updates={fightUpdates} />
        )}

        <UpcomingFights fights={upcomingList} />

        <MarketStrip series={movers} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <EventFeed events={events} />
          <PredictionFeed predictions={predictions} />
        </div>
      </main>
    </div>
  )
}
