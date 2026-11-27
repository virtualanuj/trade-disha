import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  BullionEtfOut,
  BullionMetalOut,
  CandleOut,
  FlowOut,
  IndexPrices,
  ResolvedIndexOut,
} from './api/types'
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

  it('shows the rates strip, which reads its prices itself (E26)', () => {
    render(<App />)
    const before = chartRenders.n
    act(() => {
      useMarketStore.getState().applyTick(tick(5), 5)
      useMarketStore.getState().applyQuotes([
        {
          name: 'SENSEX',
          ltp: 80_911.05,
          prev_close: 80_605.95,
          change: 305.1,
          change_pct: 0.38,
          updated_ts: 5,
        },
      ])
    })
    expect(chartRenders.n).toBe(before)
    expect(screen.getByTestId('rate-NIFTY')).toHaveTextContent('25,005.00')
    expect(screen.getByTestId('rate-SENSEX')).toHaveTextContent('80,911.05+0.38%')
  })

  it('groups the tabs by exchange; NSE BULLION shows the ETFs alone, MCX GOLD its metal (E32)', () => {
    const gold = { metal: 'GOLD', ltp: 134_914, mini: null } as unknown as BullionMetalOut
    const etf = { metal: 'GOLD', symbol: 'GOLDBEES', ltp: 108.42 } as unknown as BullionEtfOut
    act(() => {
      useMarketStore.setState({
        instruments: [{ index: 'NIFTY', future: { expiry: null } } as unknown as ResolvedIndexOut],
        bullion: { metals: [gold], ratio: null, etfs: [etf] },
      })
    })
    render(<App />)
    expect(screen.getByRole('tablist', { name: 'Market' })).toHaveTextContent(
      'NSENIFTYBULLIONMCXGOLD',
    )

    fireEvent.click(screen.getByRole('tab', { name: 'NSE BULLION' }))
    expect(screen.getByTestId('etf-view')).toBeInTheDocument()
    expect(screen.queryByTestId('price-chart')).not.toBeInTheDocument()
    expect(screen.queryByTestId('bullion-GOLD')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'MCX GOLD' }))
    expect(screen.getByTestId('bullion-GOLD')).toBeInTheDocument()
    expect(screen.getByTestId('price-chart')).toBeInTheDocument()
    expect(screen.queryByTestId('etf-view')).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Metal' })).not.toBeInTheDocument() // no switch
  })

  it('switches the chart interval, remembers it, and a closed bar redraws only the chart (E27)', () => {
    const bar = { t: 10_000, o: 1, h: 2, l: 1, c: 2, v: 0, synthetic: false, bv: null, sv: null }
    act(() => {
      useMarketStore.getState().loadChart({
        name: 'NIFTY',
        interval: '10s',
        candles: [],
        overlays: [],
        vol_candles: [],
      })
    })
    render(<App />)
    expect(screen.getByRole('radio', { name: '1m' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByRole('radio', { name: '10s' }))
    expect(screen.getByRole('radio', { name: '10s' })).toHaveAttribute('aria-checked', 'true')
    expect(localStorage.getItem('tradedisha.chartInterval')).toBe('"10s"')
    expect(screen.getByTestId('price-chart')).toBeInTheDocument()

    const before = chartRenders.n
    act(() => {
      useMarketStore.getState().applyTick(tick(7), 7)
      useMarketStore.getState().applyChartBar({
        name: 'NIFTY',
        interval: '10s',
        role: 'price',
        candle: bar,
        overlay: null,
      })
    })
    expect(chartRenders.n).toBe(before + 1) // the chart, not the page
  })
})
