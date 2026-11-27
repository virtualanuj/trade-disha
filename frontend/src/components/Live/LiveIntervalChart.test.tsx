import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChartInterval, ChartOut } from '../../api/types'
import { chartKey, useMarketStore } from '../../state/store'

const chartProps = vi.hoisted(() => ({ last: null as Record<string, unknown> | null }))
vi.mock('../PriceChart/PriceChart', () => ({
  PriceChart: (p: Record<string, unknown>) => {
    chartProps.last = p
    return <div data-testid="price-chart" />
  },
}))

const { LiveIntervalChart } = await import('./Live')

const out = (interval: ChartInterval): ChartOut => ({
  name: 'GOLD',
  interval,
  candles: [{ t: 0, o: 1, h: 1, l: 1, c: 1, v: 1, synthetic: false, bv: 1, sv: 0 }],
  overlays: [],
  vol_candles: [],
})

describe('LiveIntervalChart', () => {
  beforeEach(() => {
    useMarketStore.setState({ chartBars: {} })
    chartProps.last = null
  })

  it('loads the chart once, then draws it with its bar size', async () => {
    const load = vi.fn((_: string, iv: ChartInterval) => Promise.resolve(out(iv)))
    render(
      <LiveIntervalChart
        name="GOLD"
        interval="30s"
        signals={[]}
        theme="dark"
        height={200}
        load={load}
      />,
    )
    expect(screen.getByTestId('interval-chart-loading')).toHaveTextContent('Loading…')
    await screen.findByTestId('price-chart')
    expect(load).toHaveBeenCalledTimes(1)
    expect(load.mock.calls[0]?.slice(0, 2)).toEqual(['GOLD', '30s'])
    expect(chartProps.last).toMatchObject({
      barMs: 30_000,
      barText: '30-second',
      dataKey: 'GOLD|30s',
    })
  })

  it('does not fetch a chart already loaded, and loads again after a reconnect clears it', async () => {
    useMarketStore.getState().loadChart(out('5m'))
    const load = vi.fn((_: string, iv: ChartInterval) => Promise.resolve(out(iv)))
    render(
      <LiveIntervalChart
        name="GOLD"
        interval="5m"
        signals={[]}
        theme="dark"
        height={200}
        load={load}
      />,
    )
    expect(screen.getByTestId('price-chart')).toBeInTheDocument()
    expect(load).not.toHaveBeenCalled()
    act(() => {
      useMarketStore.setState({ chartBars: {} })
    })
    await screen.findByTestId('price-chart')
    expect(load).toHaveBeenCalledTimes(1)
    expect(useMarketStore.getState().chartBars[chartKey('GOLD', '5m')]).toBeDefined()
  })

  it('says when the chart cannot be loaded', async () => {
    const load = vi.fn(() => Promise.reject(new Error('boom')))
    render(
      <LiveIntervalChart
        name="GOLD"
        interval="10s"
        signals={[]}
        theme="dark"
        height={200}
        load={load}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the 10-second chart: boom',
    )
  })
})
