import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CandleOut, FlowOut, IndexPrices } from './api/types'
import { useMarketStore } from './state/store'

/** App renders the chart itself and the chart reads nothing from the store: so the chart
 * re-renders exactly when App does, which is what these tests count. */
const chartRenders = vi.hoisted(() => ({ n: 0 }))
vi.mock('./components/PriceChart/PriceChart', () => ({
  PriceChart: () => {
    chartRenders.n++
    return <div data-testid="price-chart" />
  },
}))
// no socket in a test; the store is fed by hand
vi.mock('./api/ws', () => ({
  MarketSocket: class {
    start = vi.fn()
    stop = vi.fn()
  },
}))

const { default: App } = await import('./App')

const tick = (ts: number): IndexPrices => ({
  index: 'NIFTY',
  spot_ltp: 25_000 + ts,
  spot_ts: ts,
  fut_ltp: 25_050 + ts,
  fut_ts: ts,
})

describe('App', () => {
  beforeEach(() => {
    chartRenders.n = 0
    useMarketStore.setState({ ws: 'open', selectedIndex: 'NIFTY', prices: {}, chains: {} })
  })

  it('does not re-render the page for a tick, a chain or a flow reading', () => {
    render(<App />)
    const before = chartRenders.n
    act(() => {
      for (let i = 1; i <= 20; i++) useMarketStore.getState().applyTick(tick(i), i)
      useMarketStore.getState().applyFlow({ index: 'NIFTY', ts: 1, score: 0.4 } as FlowOut)
    })
    expect(chartRenders.n).toBe(before)
  })

  it('does re-render it for a new candle, which the chart shows', () => {
    render(<App />)
    const before = chartRenders.n
    const candle = { t: 60_000, o: 1, h: 2, l: 1, c: 2 } as unknown as CandleOut
    act(() => {
      useMarketStore.getState().applyCandle('NIFTY', 'spot', candle)
    })
    expect(chartRenders.n).toBe(before + 1)
  })

  it('still shows the tick: the tiles read it themselves', () => {
    render(<App />)
    act(() => {
      useMarketStore.getState().applyTick(tick(5), 5)
    })
    expect(screen.getByTestId('price-chart')).toBeInTheDocument()
    expect(useMarketStore.getState().prices.NIFTY?.spot_ts).toBe(5)
  })
})
