import { create } from 'zustand'

import type {
  BullionCandlesOut,
  BullionOut,
  FlowOut,
  BiasOut,
  CandleOut,
  CandlesResponse,
  ChainOut,
  GateOut,
  HealthResponse,
  IndexPrices,
  IndexStatsOut,
  NewsOut,
  BankOut,
  OverlayOut,
  PaperTradeOut,
  ParametersOut,
  ResolvedIndexOut,
  SignalOut,
} from '../api/types'

const MAX_CANDLES = 400
/** MCX trades 09:00 to 23:30 */
const MAX_BULLION_CANDLES = 900
/** the tab beside the indices; not an index, so not in `instruments` */
export const BULLION_TAB = 'BULLION'

function gatesByIndex(gates: GateOut[]): Record<string, GateOut> {
  const out: Record<string, GateOut> = {}
  for (const g of gates) out[g.index] = g
  return out
}

function pushCapped<T extends { t: number }>(list: T[], item: T, max = MAX_CANDLES): T[] {
  const last = list[list.length - 1]
  const next = last && last.t === item.t ? [...list.slice(0, -1), item] : [...list, item]
  return next.length > max ? next.slice(next.length - max) : next
}

export type WsState = 'connecting' | 'open' | 'closed'

interface MarketStore {
  ws: WsState
  health: HealthResponse | null
  instruments: ResolvedIndexOut[]
  prices: Record<string, IndexPrices>
  /** wall-clock ms when the latest tick frame for each index arrived */
  lastFrameAt: Record<string, number>
  chains: Record<string, ChainOut>
  candles: Record<string, CandleOut[]>
  /** the near-month future's candles per index: their buy/sell split is the net volume */
  futCandles: Record<string, CandleOut[]>
  overlays: Record<string, OverlayOut[]>
  bias: Record<string, BiasOut>
  parameters: ParametersOut | null
  parametersEffectiveFrom: number | null
  /** active signal per index */
  signals: Record<string, SignalOut>
  /** today's signals, newest first */
  signalHistory: SignalOut[]
  gates: Record<string, GateOut>
  /** latest order-flow reading per index */
  flow: Record<string, FlowOut>
  /** open trades plus today's, newest first */
  trades: PaperTradeOut[]
  /** day statistics per index, for the details view */
  stats: Record<string, IndexStatsOut>
  /** gold and silver for the BULLION tab; null until the first hello */
  bullion: BullionOut | null
  bullionCandles: Record<string, CandleOut[]>
  bullionOverlays: Record<string, OverlayOut[]>
  /** headlines (spec §6.7); null until the first hello */
  news: NewsOut | null
  /** the paper bank (spec §10.5); null until the first hello */
  bank: BankOut | null
  /** an index, or BULLION_TAB */
  selectedIndex: string

  setWs: (s: WsState) => void
  applyHello: (
    h: HealthResponse,
    i: ResolvedIndexOut[],
    p: IndexPrices[],
    c: ChainOut[],
    candles: CandlesResponse[],
    bias: BiasOut[],
    parameters: ParametersOut,
    signalsActive: SignalOut[],
    signalsToday: SignalOut[],
    gates: GateOut[],
    trades: PaperTradeOut[],
    stats: IndexStatsOut[],
    flow: FlowOut[],
  ) => void
  applyFlow: (f: FlowOut) => void
  applyStats: (s: IndexStatsOut) => void
  /** the snapshot; with candles (from hello) the chart series are replaced too */
  applyBullion: (b: BullionOut, candles?: BullionCandlesOut[]) => void
  applyBullionCandle: (metal: string, c: CandleOut, o: OverlayOut) => void
  applyNews: (news: NewsOut) => void
  applyBank: (bank: BankOut) => void
  applyTrades: (t: PaperTradeOut[]) => void
  applyTick: (p: IndexPrices, recvAt: number) => void
  applyHealth: (h: HealthResponse) => void
  applyChain: (c: ChainOut) => void
  applyCandle: (index: string, role: 'spot' | 'fut', c: CandleOut) => void
  applyBias: (b: BiasOut, o: OverlayOut, gates?: GateOut[]) => void
  applySignal: (s: SignalOut, gates: GateOut[]) => void
  /** the per-second live levels of waiting signals; never revives one that has ended */
  applySignalLive: (signals: SignalOut[]) => void
  applyParameters: (p: ParametersOut, effectiveFrom: number | null) => void
  selectIndex: (index: string) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  ws: 'connecting',
  health: null,
  instruments: [],
  prices: {},
  lastFrameAt: {},
  chains: {},
  candles: {},
  futCandles: {},
  overlays: {},
  bias: {},
  parameters: null,
  parametersEffectiveFrom: null,
  signals: {},
  signalHistory: [],
  gates: {},
  flow: {},
  trades: [],
  stats: {},
  bullion: null,
  bullionCandles: {},
  bullionOverlays: {},
  news: null,
  bank: null,
  selectedIndex: 'NIFTY',

  setWs: (ws) => {
    set({ ws })
  },
  applyNews: (news) => {
    set({ news })
  },
  applyBank: (bank) => {
    set({ bank })
  },
  applyHello: (
    health,
    instruments,
    prices,
    chains,
    candles,
    bias,
    parameters,
    signalsActive,
    signalsToday,
    gates,
    trades,
    stats,
    flow,
  ) => {
    const byIndex: Record<string, IndexPrices> = {}
    for (const p of prices) {
      byIndex[p.index] = p
    }
    const chainsByIndex: Record<string, ChainOut> = {}
    for (const c of chains) {
      chainsByIndex[c.index] = c
    }
    const candlesByIndex: Record<string, CandleOut[]> = {}
    const futCandlesByIndex: Record<string, CandleOut[]> = {}
    const overlaysByIndex: Record<string, OverlayOut[]> = {}
    for (const c of candles) {
      candlesByIndex[c.index] = c.candles
      futCandlesByIndex[c.index] = c.fut_candles
      overlaysByIndex[c.index] = c.overlays
    }
    const biasByIndex: Record<string, BiasOut> = {}
    for (const b of bias) {
      biasByIndex[b.index] = b
    }
    const signalsByIndex: Record<string, SignalOut> = {}
    for (const s of signalsActive) {
      signalsByIndex[s.index] = s
    }
    set((s) => ({
      health,
      instruments,
      prices: byIndex,
      chains: chainsByIndex,
      candles: candlesByIndex,
      futCandles: futCandlesByIndex,
      overlays: overlaysByIndex,
      bias: biasByIndex,
      parameters,
      signals: signalsByIndex,
      signalHistory: signalsToday,
      gates: gatesByIndex(gates),
      flow: Object.fromEntries(flow.map((x) => [x.index, x])),
      trades,
      stats: Object.fromEntries(stats.map((x) => [x.index, x])),
      selectedIndex:
        s.selectedIndex === BULLION_TAB || instruments.some((i) => i.index === s.selectedIndex)
          ? s.selectedIndex
          : (instruments[0]?.index ?? s.selectedIndex),
    }))
  },
  applyBullion: (bullion, candles) => {
    set((s) => ({
      bullion,
      ...(candles
        ? {
            bullionCandles: Object.fromEntries(candles.map((c) => [c.metal, c.candles])),
            bullionOverlays: Object.fromEntries(candles.map((c) => [c.metal, c.overlays])),
          }
        : {}),
      // no bullion (synthetic, replay, or the MCX file failed): leave the tab
      selectedIndex:
        s.selectedIndex === BULLION_TAB && bullion.metals.length === 0
          ? (s.instruments[0]?.index ?? 'NIFTY')
          : s.selectedIndex,
    }))
  },
  applyBullionCandle: (metal, c, o) => {
    set((s) => ({
      bullionCandles: {
        ...s.bullionCandles,
        [metal]: pushCapped(s.bullionCandles[metal] ?? [], c, MAX_BULLION_CANDLES),
      },
      bullionOverlays: {
        ...s.bullionOverlays,
        [metal]: pushCapped(s.bullionOverlays[metal] ?? [], o, MAX_BULLION_CANDLES),
      },
    }))
  },
  applyStats: (x) => {
    set((s) => ({ stats: { ...s.stats, [x.index]: x } }))
  },
  applyTrades: (incoming) => {
    set((s) => {
      const byId = new Map(s.trades.map((t) => [t.id, t]))
      for (const t of incoming) byId.set(t.id, t)
      return { trades: [...byId.values()].sort((a, b) => b.entry_ts - a.entry_ts) }
    })
  },
  applyTick: (p, recvAt) => {
    set((s) => ({
      prices: { ...s.prices, [p.index]: p },
      lastFrameAt: { ...s.lastFrameAt, [p.index]: recvAt },
    }))
  },
  applyHealth: (health) => {
    set({ health })
  },
  applyChain: (c) => {
    set((s) => ({ chains: { ...s.chains, [c.index]: c } }))
  },
  applyCandle: (index, role, c) => {
    if (role === 'fut') {
      set((s) => ({
        futCandles: { ...s.futCandles, [index]: pushCapped(s.futCandles[index] ?? [], c) },
      }))
      return
    }
    set((s) => ({ candles: { ...s.candles, [index]: pushCapped(s.candles[index] ?? [], c) } }))
  },
  applyBias: (b, o, gates) => {
    set((s) => ({
      bias: { ...s.bias, [b.index]: b },
      overlays: { ...s.overlays, [b.index]: pushCapped(s.overlays[b.index] ?? [], o) },
      gates: gates ? { ...s.gates, ...gatesByIndex(gates) } : s.gates,
    }))
  },
  applySignal: (sig, gates) => {
    set((s) => {
      let signals = s.signals
      // a shadow signal is history only: it is never the one on offer
      if (sig.shadow) {
        /* leave the active signal alone */
      } else if (sig.status === 'active') signals = { ...signals, [sig.index]: sig }
      else if (signals[sig.index]?.id === sig.id) {
        signals = Object.fromEntries(Object.entries(signals).filter(([k]) => k !== sig.index))
      }
      const rest = s.signalHistory.filter((x) => x.id !== sig.id)
      return {
        signals,
        signalHistory: [sig, ...rest].sort((a, b) => b.ts_fired - a.ts_fired),
        gates: { ...s.gates, ...gatesByIndex(gates) },
      }
    })
  },
  applySignalLive: (incoming) => {
    set((s) => {
      let signals = s.signals
      for (const sig of incoming) {
        if (signals[sig.index]?.id === sig.id) signals = { ...signals, [sig.index]: sig }
      }
      return signals === s.signals ? {} : { signals }
    })
  },
  applyFlow: (f) => {
    set((s) => ({ flow: { ...s.flow, [f.index]: f } }))
  },
  applyParameters: (parameters, parametersEffectiveFrom) => {
    set({ parameters, parametersEffectiveFrom })
  },
  selectIndex: (selectedIndex) => {
    set({ selectedIndex })
  },
}))
