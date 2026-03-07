/**
 * Two-column split layout: left = Event Feed, right = Prediction Feed.
 */

interface TwoColumnLayoutProps {
  left:  React.ReactNode
  right: React.ReactNode
}

export function TwoColumnLayout({ left, right }: TwoColumnLayoutProps) {
  return (
    <div className="flex flex-1 gap-4 p-4 min-h-0 overflow-hidden">
      {/* Stream 1 — factual events */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">{left}</div>
      {/* Stream 2 — RAG predictions */}
      <div className="flex-1 overflow-y-auto space-y-2 pl-1">{right}</div>
    </div>
  )
}
