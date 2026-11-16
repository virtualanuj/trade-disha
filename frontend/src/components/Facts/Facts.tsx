import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { fmtIstTime, fmtPrice } from '../../lib/format'

/** The small building blocks of the index and bullion detail views. */

function useFlash(value: number | null): 'up' | 'down' | null {
  const prev = useRef<number | null>(null)
  const [dir, setDir] = useState<'up' | 'down' | null>(null)
  useEffect(() => {
    const p = prev.current
    prev.current = value
    if (value == null || p == null || value === p) return
    setDir(value > p ? 'up' : 'down')
    const id = setTimeout(() => {
      setDir(null)
    }, 150)
    return () => {
      clearTimeout(id)
    }
  }, [value])
  return dir
}

export function Price({
  label,
  value,
  ts,
}: {
  label: string
  value: number | null
  ts: number | null
}) {
  const flash = useFlash(value)
  const cls = flash === 'up' ? 'text-bull' : flash === 'down' ? 'text-bear' : 'text-fg'
  return (
    <div className="flex min-w-0 flex-col">
      <span className="truncate text-xs uppercase tracking-wide text-fg-muted">{label}</span>
      <span className={`font-mono text-lg transition-colors duration-150 ${cls}`}>
        {fmtPrice(value)}
      </span>
      <span className="font-mono text-xs text-fg-muted">{ts ? fmtIstTime(ts) : '—'}</span>
    </div>
  )
}

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wide text-fg-muted">{title}</div>
      {children}
    </div>
  )
}

export function Fact({
  label,
  value,
  sub = '',
  cls = '',
}: {
  label: string
  value: string
  sub?: string
  cls?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-muted">{label}</span>
      <span className={`font-mono ${cls}`}>
        {value}
        {sub ? <span className="ml-1 text-[10px] text-fg-muted">{sub}</span> : null}
      </span>
    </div>
  )
}

/** A thin bar with a marker: low on the left, high on the right. */
export function RangeBar({ pos, label }: { pos: number | null; label: string }) {
  if (pos == null) return null
  const pct = Math.min(100, Math.max(0, pos * 100))
  return (
    <div
      className="relative mt-1 h-1 rounded bg-border"
      role="img"
      aria-label={`${label}: ${pct.toFixed(0)}%`}
      title={`${label}: ${pct.toFixed(0)}%`}
    >
      <div
        className="absolute -top-1 h-3 w-0.5 rounded bg-accent"
        style={{ left: `${pct.toFixed(1)}%` }}
      />
    </div>
  )
}
