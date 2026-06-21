import { useMemo } from 'react'
import { useEventStream } from './hooks/useEventStream'
import { Header } from './components/layout/Header'
import { FeaturedFight } from './components/featured/FeaturedFight'
import { MarketStrip } from './components/featured/MarketStrip'
import { EventFeed } from './components/events/EventFeed'
import { PredictionFeed } from './components/predictions/PredictionFeed'
import { StreamWarning } from './components/shared/StreamWarning'
import { buildMarketSeries, pickFeatured, sortByRecent } from './lib/marketSeries'

export default function App() {
  const { events, predictions, connected, error } = useEventStream()

  const series = useMemo(() => buildMarketSeries(events), [events])
  const featured = useMemo(() => pickFeatured(series), [series])
  const movers = useMemo(() => sortByRecent(series), [series])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 antialiased">
      <Header connected={connected} />

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {!connected && (
          <StreamWarning message="WebSocket disconnected — attempting to reconnect…" />
        )}
        {error && <StreamWarning message={error} />}

        {featured ? (
          <FeaturedFight series={featured} />
        ) : (
          <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-10 text-center text-slate-500">
            Waiting for live market data…
          </div>
        )}

        <MarketStrip series={movers} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <EventFeed events={events} />
          <PredictionFeed predictions={predictions} />
        </div>
      </main>
    </div>
  )
}
