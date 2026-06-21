/**
 * Dependency-free SVG area+line chart of a probability series.
 * Auto-scales the y-axis to the data range (with padding) so small moves read clearly.
 */

import { useId } from 'react'

interface ProbabilityChartProps {
  points: number[]        // probabilities [0,1], chronological
  up?: boolean            // color: emerald when trending up, red when down
  height?: number
  showAxis?: boolean
}

const WIDTH = 600

export function ProbabilityChart({ points, up = true, height = 200, showAxis = false }: ProbabilityChartProps) {
  const gid = useId()
  const color = up ? '#34d399' : '#f87171'

  if (points.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-slate-600">
        gathering data…
      </div>
    )
  }

  const min = Math.min(...points)
  const max = Math.max(...points)
  const pad = (max - min) * 0.2 || 0.02
  const lo = Math.max(0, min - pad)
  const hi = Math.min(1, max + pad)
  const range = hi - lo || 1
  const n = points.length

  const x = (i: number) => (i / (n - 1)) * WIDTH
  const y = (p: number) => height - ((p - lo) / range) * height

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(' ')
  const area = `${line} L ${WIDTH} ${height} L 0 ${height} Z`

  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="h-full w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.30" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {showAxis && (
        <>
          <line x1="0" y1={y(hi)} x2={WIDTH} y2={y(hi)} stroke="#ffffff" strokeOpacity="0.06" strokeWidth="1" />
          <line x1="0" y1={y(lo)} x2={WIDTH} y2={y(lo)} stroke="#ffffff" strokeOpacity="0.06" strokeWidth="1" />
        </>
      )}
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2.5"
            vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
