import { useCallback, useSyncExternalStore } from 'react'

interface Ticker {
  now: number
  listeners: Set<() => void>
  timer: ReturnType<typeof setInterval> | null
}

/** One clock per interval, shared by every reader of it. */
const tickers = new Map<number, Ticker>()

function ticker(everyMs: number): Ticker {
  let t = tickers.get(everyMs)
  if (!t) {
    t = { now: Date.now(), listeners: new Set(), timer: null }
    tickers.set(everyMs, t)
  }
  return t
}

function subscribe(everyMs: number, onChange: () => void): () => void {
  const t = ticker(everyMs)
  t.listeners.add(onChange)
  if (t.timer === null) {
    t.now = Date.now()
    t.timer = setInterval(() => {
      t.now = Date.now()
      for (const fn of t.listeners) fn()
    }, everyMs)
  }
  return () => {
    t.listeners.delete(onChange)
    if (t.listeners.size === 0 && t.timer !== null) {
      clearInterval(t.timer)
      t.timer = null
    }
  }
}

function snapshot(everyMs: number): number {
  const t = ticker(everyMs)
  // an idle clock (no reader since a while) would hand the next reader a stale first value
  if (t.timer === null && Date.now() - t.now >= everyMs) t.now = Date.now()
  return t.now
}

/**
 * Wall-clock ms, moving every `everyMs`. For clocks and tick-age displays.
 *
 * Every reader of the same interval shares one timer and sees the same moment, so the
 * clocks on the page tick together, and only the components that show time re-render.
 */
export function useNow(everyMs = 500): number {
  const sub = useCallback((onChange: () => void) => subscribe(everyMs, onChange), [everyMs])
  const get = useCallback(() => snapshot(everyMs), [everyMs])
  return useSyncExternalStore(sub, get)
}
