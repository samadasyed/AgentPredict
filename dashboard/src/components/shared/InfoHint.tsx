/**
 * A small "?" that toggles an explanatory popover. Built on <details> so
 * open/close, keyboard toggling, and light-dismiss (via the backdrop) come
 * free — no state management, works without JS hydration quirks.
 */

import type { ReactNode } from 'react'

interface InfoHintProps {
  label: string        // accessible name, e.g. "What are Live Events?"
  children: ReactNode  // popover body
}

export function InfoHint({ label, children }: InfoHintProps) {
  return (
    <details className="group relative inline-block align-middle">
      <summary
        aria-label={label}
        title={label}
        className="flex h-[18px] w-[18px] cursor-pointer list-none items-center justify-center rounded-full border border-slate-600 text-[10px] font-bold text-slate-400 transition-colors hover:border-slate-400 hover:text-slate-200 group-open:border-sky-400 group-open:text-sky-300 [&::-webkit-details-marker]:hidden"
      >
        ?
      </summary>
      {/* click-away backdrop: any click outside closes the popover */}
      <div
        className="fixed inset-0 z-20 cursor-default"
        onClick={(e) => {
          e.preventDefault()
          ;(e.currentTarget.parentElement as HTMLDetailsElement).open = false
        }}
      />
      <div className="absolute right-0 z-30 mt-2 w-80 max-w-[85vw] rounded-xl border border-white/10 bg-slate-900 p-4 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-slate-300 shadow-2xl">
        {children}
      </div>
    </details>
  )
}
