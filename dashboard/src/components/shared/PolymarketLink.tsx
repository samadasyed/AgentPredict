/**
 * Visible external link to a fight's page on polymarket.com.
 * Renders nothing when the market has no known event slug.
 */

interface PolymarketLinkProps {
  url: string | null
  className?: string
}

export function PolymarketLink({ url, className = '' }: PolymarketLinkProps) {
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      // Cards live inside hover surfaces — don't let the link's click bubble.
      onClick={(e) => e.stopPropagation()}
      className={`inline-flex items-center gap-1 text-[11px] font-medium text-sky-400/90 hover:text-sky-300 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 ${className}`}
    >
      Polymarket
      <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path d="M4 2h6v6M10 2 5 7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}
