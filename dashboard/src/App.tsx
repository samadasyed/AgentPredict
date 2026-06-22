import { useMemo } from 'react'
import { useEventStream } from './hooks/useEventStream'
import { Header } from './components/layout/Header'
import { FeaturedFight } from './components/featured/FeaturedFight'
import { MarketStrip } from './components/featured/MarketStrip'
import { UpcomingFights } from './components/upcoming/UpcomingFights'
import { LiveFightTracker } from './components/live/LiveFightTracker'
import { EventFeed } from './components/events/EventFeed'
import { PredictionFeed } from './components/predictions/PredictionFeed'
import { StreamWarning } from './components/shared/StreamWarning'
import {
  buildMarketSeries,
  pickFeatured,
  sortByRecent,
  upcomingFights,
  buildLiveFights,
  buildFightUpdates,
  findFightForOutcome,
} from './lib/marketSeries'

export default function App() {
  const { events, predictions, connected, error } = useEventStream()

  const series = useMemo(() => buildMarketSeries(events), [events])
  const featured = useMemo(() => pickFeatured(series), [series])
  const movers = useMemo(() => sortByRecent(series), [series])
  const upcoming = useMemo(() => upcomingFights(series), [series])

  const liveFights = useMemo(() => buildLiveFights(events), [events])
  const fightUpdates = useMemo(() => buildFightUpdates(events), [events])
  const featuredFight = useMemo(
    () => (featured ? findFightForOutcome(liveFights, featured.outcome) : null),
    [featured, liveFights],
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
        ) : (
          <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-10 text-center text-slate-500">
            Waiting for market data…
          </div>
        )}

        {liveFights.length > 0 && (
          <LiveFightTracker fights={liveFights} updates={fightUpdates} />
        )}

        <UpcomingFights series={upcoming} />

        <MarketStrip series={movers} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <EventFeed events={events} />
          <PredictionFeed predictions={predictions} />
        </div>
      </main>
    </div>
  )
}
