import { useEventStream } from './hooks/useEventStream'
import { Header } from './components/layout/Header'
import { TwoColumnLayout } from './components/layout/TwoColumnLayout'
import { EventFeed } from './components/events/EventFeed'
import { PredictionFeed } from './components/predictions/PredictionFeed'
import { StreamWarning } from './components/shared/StreamWarning'

export default function App() {
  const { events, predictions, connected, error } = useEventStream()

  return (
    <div className="flex flex-col h-screen bg-gray-950">
      <Header connected={connected} />

      <div className="px-4 pt-3">
        {!connected && (
          <StreamWarning message="WebSocket disconnected — attempting to reconnect…" />
        )}
        {error && <StreamWarning message={error} />}
      </div>

      <TwoColumnLayout
        left={<EventFeed events={events} />}
        right={<PredictionFeed predictions={predictions} />}
      />
    </div>
  )
}
