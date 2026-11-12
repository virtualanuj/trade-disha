import { create } from 'zustand'

import type { ChainOut, HealthResponse, IndexPrices, ResolvedIndexOut } from '../api/types'

export type WsState = 'connecting' | 'open' | 'closed'

interface MarketStore {
  ws: WsState
  health: HealthResponse | null
  instruments: ResolvedIndexOut[]
  prices: Record<string, IndexPrices>
  /** wall-clock ms when the latest tick frame for each index arrived */
  lastFrameAt: Record<string, number>
  chains: Record<string, ChainOut>
  selectedIndex: string

  setWs: (s: WsState) => void
  applyHello: (h: HealthResponse, i: ResolvedIndexOut[], p: IndexPrices[], c: ChainOut[]) => void
  applyTick: (p: IndexPrices, recvAt: number) => void
  applyHealth: (h: HealthResponse) => void
  applyChain: (c: ChainOut) => void
  selectIndex: (index: string) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  ws: 'connecting',
  health: null,
  instruments: [],
  prices: {},
  lastFrameAt: {},
  chains: {},
  selectedIndex: 'NIFTY',

  setWs: (ws) => {
    set({ ws })
  },
  applyHello: (health, instruments, prices, chains) => {
    const byIndex: Record<string, IndexPrices> = {}
    for (const p of prices) {
      byIndex[p.index] = p
    }
    const chainsByIndex: Record<string, ChainOut> = {}
    for (const c of chains) {
      chainsByIndex[c.index] = c
    }
    set((s) => ({
      health,
      instruments,
      prices: byIndex,
      chains: chainsByIndex,
      selectedIndex: instruments.some((i) => i.index === s.selectedIndex)
        ? s.selectedIndex
        : (instruments[0]?.index ?? s.selectedIndex),
    }))
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
  selectIndex: (selectedIndex) => {
    set({ selectedIndex })
  },
}))
