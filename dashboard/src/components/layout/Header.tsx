/**
 * Top navigation bar with live connection status indicator.
 */

interface HeaderProps {
  connected: boolean
}

export function Header({ connected }: HeaderProps) {
  return (
    <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-lg font-bold tracking-tight text-white">AgentPredict</span>
        <span className="text-xs text-gray-500 font-mono">Live UFC Dashboard</span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            connected ? 'bg-green-400 animate-pulse' : 'bg-red-500'
          }`}
        />
        <span className={`text-xs font-mono ${connected ? 'text-green-400' : 'text-red-400'}`}>
          {connected ? 'connected' : 'disconnected'}
        </span>
      </div>
    </header>
  )
}
