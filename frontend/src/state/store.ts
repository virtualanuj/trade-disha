import { create } from 'zustand'

import type {
  BiasOut,
  CandleOut,
  CandlesResponse,
  ChainOut,
  GateOut,
  HealthResponse,
  IndexPrices,
  OverlayOut,
  PaperTradeOut,
  ParametersOut,
  ResolvedIndexOut,
  SignalOut,
} from '../api/types'

const MAX_CANDLES = 400

function gatesByIndex(gates: GateOut[]): Record<string, GateOut> {
  const out: Record<string, GateOut> = {}
  for (const g of gates) out[g.index] = g
  return out
}

function pushCapped<T extends { t: number }>(list: T[], item: T): T[] {
  const last = list[list.length - 1]
  const next = last && last.t === item.t ? [...list.slice(0, -1), item] : [...list, item]
  return next.length > MAX_CANDLES ? next.slice(next.length - MAX_CANDLES) : next
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
  overlays: Record<string, OverlayOut[]>
  bias: Record<string, BiasOut>
  parameters: ParametersOut | null
  parametersEffectiveFrom: number | null
  /** active signal per index */
  signals: Record<string, SignalOut>
  /** today's signals, newest first */
  signalHistory: SignalOut[]
  gates: Record<string, GateOut>
  /** open trades plus today's, newest first */
  trades: PaperTradeOut[]
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
  ) => void
  applyTrades: (t: PaperTradeOut[]) => void
  applyTick: (p: IndexPrices, recvAt: number) => void
  applyHealth: (h: HealthResponse) => void
  applyChain: (c: ChainOut) => void
  applyCandle: (index: string, role: 'spot' | 'fut', c: CandleOut) => void
  applyBias: (b: BiasOut, o: OverlayOut, gates?: GateOut[]) => void
  applySignal: (s: SignalOut, gates: GateOut[]) => void
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
  overlays: {},
  bias: {},
  parameters: null,
  parametersEffectiveFrom: null,
  signals: {},
  signalHistory: [],
  gates: {},
  trades: [],
  selectedIndex: 'NIFTY',

  setWs: (ws) => {
    set({ ws })
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
    const overlaysByIndex: Record<string, OverlayOut[]> = {}
    for (const c of candles) {
      candlesByIndex[c.index] = c.candles
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
      overlays: overlaysByIndex,
      bias: biasByIndex,
      parameters,
      signals: signalsByIndex,
      signalHistory: signalsToday,
      gates: gatesByIndex(gates),
      trades,
      selectedIndex: instruments.some((i) => i.index === s.selectedIndex)
        ? s.selectedIndex
        : (instruments[0]?.index ?? s.selectedIndex),
    }))
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
    if (role !== 'spot') return
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
      if (sig.status === 'active') signals = { ...signals, [sig.index]: sig }
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
  applyParameters: (parameters, parametersEffectiveFrom) => {
    set({ parameters, parametersEffectiveFrom })
  },
  selectIndex: (selectedIndex) => {
    set({ selectedIndex })
  },
}))
