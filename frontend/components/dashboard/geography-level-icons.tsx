import * as React from 'react'
import { cn } from '@/lib/utils'

export type GeographyLevelIconKey = 'city' | 'country' | 'regional' | 'continent' | 'global'

const STROKE = 2.2

/** Circular tab icons (city / country / regional / continent / global) — compact for pills or MyHigh5. */
export function GeographyLevelIcon({
  level,
  size = 32,
  className,
}: {
  level: GeographyLevelIconKey
  size?: number
  className?: string
}) {
  const colors: Record<GeographyLevelIconKey, string> = {
    city: '#2563eb',
    country: '#16a34a',
    regional: '#9333ea',
    continent: '#ea580c',
    global: '#1e3a8a',
  }
  const c = colors[level]
  const vb = 48

  const inner = (() => {
    switch (level) {
      case 'city':
        return (
          <g fill={c} stroke="none">
            <rect x="14" y="22" width="7" height="16" rx="1" />
            <rect x="22.5" y="14" width="8" height="24" rx="1" />
            <rect x="32" y="18" width="7" height="20" rx="1" />
          </g>
        )
      case 'country':
        return (
          <g fill="none" stroke={c} strokeWidth={STROKE} strokeLinecap="round">
            <line x1="18" y1="34" x2="18" y2="14" />
            <path d="M18 14 L30 18 L30 32 L18 28 Z" fill={c} fillOpacity={0.15} stroke={c} />
          </g>
        )
      case 'regional':
        return (
          <g fill={c} stroke="none">
            <circle cx="18" cy="20" r="5" />
            <circle cx="30" cy="18" r="5" />
            <circle cx="24" cy="30" r="6" />
          </g>
        )
      case 'continent':
        return (
          <g fill="none" stroke={c} strokeWidth={STROKE}>
            <circle cx="24" cy="24" r="14" />
            <ellipse cx="24" cy="24" rx="14" ry="5" />
            <line x1="10" y1="24" x2="38" y2="24" />
            <path d="M24 10 Q32 24 24 38 Q16 24 24 10" />
          </g>
        )
      case 'global':
        return (
          <g fill="none" stroke={c} strokeWidth={STROKE}>
            <circle cx="24" cy="24" r="14" />
            <path
              d="M10 24h28M24 10c-4 6-4 22 0 28M24 10c4 6 4 22 0 28"
              strokeLinecap="round"
            />
            <path
              d="M14 17c4 2 10 2 20 0M14 31c4-2 10-2 20 0"
              strokeLinecap="round"
              opacity={0.85}
            />
          </g>
        )
      default:
        return null
    }
  })()

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${vb} ${vb}`}
      className={cn('flex-shrink-0', className)}
      aria-hidden
    >
      <circle cx="24" cy="24" r="22" fill="#ffffff" stroke={c} strokeWidth={STROKE} />
      {inner}
    </svg>
  )
}
