import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PaperTradeDetailOut, PaperTradeOut, SignalOut } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { TradeLog } from './TradeLog'

/** the evidence table sits inside an open row's detail: it renders when its row does */
const evidence = vi.hoisted(() => ({ renders: 0 }))
vi.mock('../EvidenceTable/EvidenceTable', () => ({
  EvidenceTable: () => {
    evidence.renders++
    return null
  },
}))

const closed: PaperTradeOut = {
  ...trade,
  id: 'c1',
  status: 'closed',
  exit_price: 130,
  exit_ts: trade.entry_ts + 600_000,
  exit_reason: 'TARGET',
  exit_fill_quality: 'live',
  gross: 1885,
  net: 1825,
}
const signal: SignalOut = {
  id: 's1',
  index: 'NIFTY',
  minute_ts: trade.entry_ts - 60_000,
  ts_fired: trade.entry_ts - 2_000,
  direction: 'BUY_CE',
  instrument_key: trade.instrument_key,
  trading_symbol: trade.trading_symbol,
  strike: 25000,
  expiry: '2026-11-17',
  lot_size: 65,
  entry_price: 100,
  target_price: 130,
  stop_price: 85,
  target_basis: 'pct',
  target_points: null,
  stop_points: null,
  delta_used: null,
  bias: 0.62,
  strength: 62,
  breakdown: {},
  expires_at: trade.entry_ts + 300_000,
  status: 'traded',
  status_ts: trade.entry_ts,
  entry_ask: null,
  spread_pct: null,
  entry_mode: 'minute_close',
  shadow: false,
  flow_score: null,
  config_version: null,
  outcome: null,
  live: null,
  trade: null,
}

async function openRow(t: PaperTradeOut, now: number) {
  const load = vi.fn(() => Promise.resolve([t]))
  const loadDetail = vi.fn(() =>
    Promise.resolve<PaperTradeDetailOut>({ trade: t, signal, levels: [] }),
  )
  const page = (at: number) => (
    <TradeLog markets={['NIFTY']} revision={0} now={at} load={load} loadDetail={loadDetail} />
  )
  const view = render(page(now))
  fireEvent.click(await screen.findByTestId(`trade-toggle-${t.id}`))
  await screen.findByTestId(`trade-detail-${t.id}`)
  return (at: number) => {
    view.rerender(page(at))
  }
}

describe('TradeLog rows and the clock', () => {
  it('a closed trade does not re-render as the clock moves', async () => {
    const tick = await openRow(closed, 1_000)
    const before = evidence.renders
    for (let i = 1; i <= 10; i++) tick(1_000 + i * 500)
    expect(evidence.renders).toBe(before)
  })

  it('an open trade does: its time held moves', async () => {
    const tick = await openRow(trade, 1_000)
    const before = evidence.renders
    for (let i = 1; i <= 10; i++) tick(1_000 + i * 500)
    expect(evidence.renders).toBe(before + 10)
  })
})
