import { create } from 'zustand'

import type { HealthResponse, IndexPrices, ResolvedIndexOut } from '../api/types'

export type WsState = 'connecting' | 'open' | 'closed'

interface MarketStore {
  ws: WsState
  health: HealthResponse | null
  instruments: ResolvedIndexOut[]
  prices: Record<string, IndexPrices>
  /** wall-clock ms when the latest tick frame for each index arrived */
  lastFrameAt: Record<string, number>

  setWs: (s: WsState) => void
  applyHello: (h: HealthResponse, i: ResolvedIndexOut[], p: IndexPrices[]) => void
  applyTick: (p: IndexPrices, recvAt: number) => void
  applyHealth: (h: HealthResponse) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  ws: 'connecting',
  health: null,
  instruments: [],
  prices: {},
  lastFrameAt: {},

  setWs: (ws) => {
    set({ ws })
  },
  applyHello: (health, instruments, prices) => {
    const byIndex: Record<string, IndexPrices> = {}
    for (const p of prices) {
      byIndex[p.index] = p
    }
    set({ health, instruments, prices: byIndex })
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
}))
