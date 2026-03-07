/**
 * Amber banner shown when the WebSocket is disconnected or a payload error occurs.
 */

interface StreamWarningProps {
  message: string
}

export function StreamWarning({ message }: StreamWarningProps) {
  return (
    <div className="w-full bg-amber-500/20 border border-amber-500 rounded-md px-4 py-2 text-amber-300 text-sm font-medium">
      ⚠ {message}
    </div>
  )
}
