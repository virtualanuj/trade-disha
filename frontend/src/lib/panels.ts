import { useCallback, useEffect, useMemo, useRef } from 'react'

import { usePref } from './usePref'

/** The dashboard panels that can be minimised. */
export const PANEL_IDS = [
  'tiles',
  'bias',
  'signal',
  'trades',
  'chart',
  'evidence',
  'history',
  'chain',
] as const

export type PanelId = (typeof PANEL_IDS)[number]
export type Minimised = Record<PanelId, boolean>

export const PANELS_KEY = 'tradedisha.panels'
/** E1's "option chain shown" choice, read once so a hidden chain stays hidden */
const LEGACY_CHAIN_OPEN_KEY = 'tradedisha.chainOpen'

export const NONE_MINIMISED: Minimised = {
  tiles: false,
  bias: false,
  signal: false,
  trades: false,
  chart: false,
  evidence: false,
  history: false,
  chain: false,
}

/**
 * Stored minimised flags, if that is what `v` is; otherwise nothing minimised, except
 * that the option chain stays hidden when E1 had it hidden (`legacyChainOpen === false`).
 */
export function parsePanels(v: unknown, legacyChainOpen?: unknown): Minimised {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) {
    return { ...NONE_MINIMISED, chain: legacyChainOpen === false }
  }
  const stored = v as Record<string, unknown>
  const out = { ...NONE_MINIMISED }
  for (const id of PANEL_IDS) out[id] = stored[id] === true
  return out
}

function parseStored(v: unknown): Minimised {
  let legacy: unknown
  try {
    const raw = localStorage.getItem(LEGACY_CHAIN_OPEN_KEY)
    legacy = raw == null ? undefined : (JSON.parse(raw) as unknown)
  } catch {
    legacy = undefined
  }
  return parsePanels(v, legacy)
}

export interface Panels {
  minimised: Minimised
  /** true when any panel is minimised */
  changed: boolean
  toggleMinimise: (id: PanelId) => void
  /** expand a minimised panel; does nothing to one that is already showing */
  open: (id: PanelId) => void
  /** every panel expanded again */
  restoreAll: () => void
}

/** Which panels are minimised, remembered in this browser. */
export function usePanels(): Panels {
  const [minimised, store] = usePref(PANELS_KEY, parseStored)
  /** the flags as last written, so two changes in the same moment both land */
  const latest = useRef(minimised)

  const write = useCallback(
    (change: (now: Minimised) => Minimised) => {
      const next = change(latest.current)
      if (next === latest.current) return
      latest.current = next
      store(next)
    },
    [store],
  )
  const toggleMinimise = useCallback(
    (id: PanelId) => {
      write((m) => ({ ...m, [id]: !m[id] }))
    },
    [write],
  )
  const open = useCallback(
    (id: PanelId) => {
      write((m) => (m[id] ? { ...m, [id]: false } : m))
    },
    [write],
  )
  const restoreAll = useCallback(() => {
    write((m) => (PANEL_IDS.some((id) => m[id]) ? NONE_MINIMISED : m))
  }, [write])

  return useMemo(
    () => ({
      minimised,
      changed: PANEL_IDS.some((id) => minimised[id]),
      toggleMinimise,
      open,
      restoreAll,
    }),
    [minimised, toggleMinimise, open, restoreAll],
  )
}

/**
 * Calls `open` when `ids` contains one not seen before in this page load: a new signal or
 * a newly opened trade brings its panel back, but only once, so minimising it again
 * sticks until the next new one.
 */
export function useOpenOnNew(ids: string[], open: () => void): void {
  const seen = useRef(new Set<string>())
  const key = ids.join('|')
  useEffect(() => {
    let fresh = false
    for (const id of key ? key.split('|') : []) {
      if (!seen.current.has(id)) {
        seen.current.add(id)
        fresh = true
      }
    }
    if (fresh) open()
  }, [key, open])
}
