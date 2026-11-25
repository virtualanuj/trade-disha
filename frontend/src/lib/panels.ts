import { useCallback, useEffect, useMemo, useRef } from 'react'

import { usePref } from './usePref'

/** The dashboard panels that can be minimised. */
export const PANEL_IDS = [
  'tiles',
  'bias', // "Market view": the meter with its evidence (one panel since E9)
  'signal',
  'trades',
  'chart',
  'history',
  'chain',
  'news', // "Headlines", under the option chain (E10)
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
  history: false,
  chain: false,
  news: false,
}

/**
 * What moves up and down the left column: every panel on its own (since E9 the signal has
 * its own row and Market view holds the evidence). The option chain and the headlines share
 * the right-hand column and do not move.
 */
export const UNIT_IDS = ['tiles', 'signal', 'bias', 'chart', 'trades', 'history'] as const

export type UnitId = (typeof UNIT_IDS)[number]
export type Order = readonly UnitId[]

export const ORDER_KEY = 'tradedisha.panelOrder'
/** Headlines taken out of the right-hand column (E10); separate from minimised */
export const NEWS_HIDDEN_KEY = 'tradedisha.newsHidden'
export const DEFAULT_ORDER: Order = UNIT_IDS

/** The unit a panel moves with; null for a panel that does not move. */
export function unitOf(id: PanelId): UnitId | null {
  return id === 'chain' || id === 'news' ? null : id
}

/**
 * Before E9 market view and signal were one unit, `view`, and evidence had its own: an
 * order stored then keeps the pair's place as signal then market view, and evidence (now
 * inside market view) is dropped.
 */
function carryOver(stored: unknown[]): unknown[] {
  return stored.flatMap((id) =>
    id === 'view' ? ['signal', 'bias'] : id === 'evidence' ? [] : [id],
  )
}

/**
 * A stored order, if that is what `v` is: unknown and repeated ids are dropped and any
 * unit it does not mention is added at the end. Otherwise the default order.
 */
export function parseOrder(v: unknown): Order {
  if (!Array.isArray(v)) return DEFAULT_ORDER
  const known = new Set<unknown>(UNIT_IDS)
  const out: UnitId[] = []
  for (const id of [...carryOver(v as unknown[]), ...UNIT_IDS]) {
    if (known.has(id) && !out.includes(id as UnitId)) out.push(id as UnitId)
  }
  return out.every((id, i) => id === DEFAULT_ORDER[i]) ? DEFAULT_ORDER : out
}

/** `order` with `unit` one place up (-1) or down (+1); `order` itself at either end. */
export function moveUnit(order: Order, unit: UnitId, dir: -1 | 1): Order {
  const from = order.indexOf(unit)
  const other = order[from + dir]
  if (from < 0 || other === undefined) return order
  const next = [...order]
  next[from] = other
  next[from + dir] = unit
  return next.every((id, i) => id === DEFAULT_ORDER[i]) ? DEFAULT_ORDER : next
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
  /** the left column's units, top to bottom */
  order: Order
  /**
   * true when a panel other than the headlines is minimised, or the order is not the
   * default: what "Restore panels" undoes. The headlines have their own button.
   */
  changed: boolean
  /** headlines taken out of the right-hand column (E10) */
  newsHidden: boolean
  setNewsHidden: (hidden: boolean) => void
  /** the headlines are on the page and expanded: what the Headlines button shows as on */
  newsShown: boolean
  /** the Headlines button: show them expanded, or take them off the page */
  showNews: (shown: boolean) => void
  toggleMinimise: (id: PanelId) => void
  /** expand a minimised panel; does nothing to one that is already showing */
  open: (id: PanelId) => void
  /** whether a panel can go up (-1) or down (+1); never for one that does not move */
  canMove: (id: PanelId, dir: -1 | 1) => boolean
  /** move a panel's unit one place; market view and signal go together */
  move: (id: PanelId, dir: -1 | 1) => void
  /** every panel but the headlines expanded again, in the default order */
  restoreAll: () => void
}

/** What "Restore panels" expands: every panel but the headlines, which have their own button. */
const RESTORED = PANEL_IDS.filter((id) => id !== 'news')

/** Which panels are minimised and what order they are in, remembered in this browser. */
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

  const [order, storeOrder] = usePref(ORDER_KEY, parseOrder)
  const latestOrder = useRef(order)
  const writeOrder = useCallback(
    (next: Order) => {
      if (next === latestOrder.current) return
      latestOrder.current = next
      storeOrder(next)
    },
    [storeOrder],
  )
  const move = useCallback(
    (id: PanelId, dir: -1 | 1) => {
      const unit = unitOf(id)
      if (unit) writeOrder(moveUnit(latestOrder.current, unit, dir))
    },
    [writeOrder],
  )
  const canMove = useCallback(
    (id: PanelId, dir: -1 | 1) => {
      const unit = unitOf(id)
      return unit !== null && moveUnit(order, unit, dir) !== order
    },
    [order],
  )

  const [newsHidden, storeNewsHidden] = usePref(NEWS_HIDDEN_KEY, (v) => v === true)
  const setNewsHidden = useCallback(
    (hidden: boolean) => {
      storeNewsHidden(hidden)
    },
    [storeNewsHidden],
  )

  const showNews = useCallback(
    (shown: boolean) => {
      storeNewsHidden(!shown)
      if (shown) open('news')
    },
    [storeNewsHidden, open],
  )

  const restoreAll = useCallback(() => {
    write((m) => (RESTORED.some((id) => m[id]) ? { ...NONE_MINIMISED, news: m.news } : m))
    writeOrder(DEFAULT_ORDER)
  }, [write, writeOrder])

  return useMemo(
    () => ({
      minimised,
      order,
      changed: RESTORED.some((id) => minimised[id]) || order !== DEFAULT_ORDER,
      newsHidden,
      setNewsHidden,
      newsShown: !newsHidden && !minimised.news,
      showNews,
      toggleMinimise,
      open,
      canMove,
      move,
      restoreAll,
    }),
    [
      minimised,
      order,
      newsHidden,
      setNewsHidden,
      showNews,
      toggleMinimise,
      open,
      canMove,
      move,
      restoreAll,
    ],
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
