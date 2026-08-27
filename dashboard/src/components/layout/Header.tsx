/** Sticky top bar with the AgentPredict MMA brand. */
export function Header() {
  return (
    <header className="sticky top-0 z-10 border-b border-white/5 bg-slate-950/80 px-6 py-4 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center">
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-sky-400 text-sm font-black text-slate-950">
            A
          </span>
          <div className="leading-tight">
            <div className="text-base font-semibold tracking-tight text-white">
              AgentPredict <span className="text-rose-400">MMA</span>
            </div>
            <div className="text-xs text-slate-500">Live odds · fight stats · AI analysis</div>
          </div>
        </div>
      </div>
    </header>
  )
}
