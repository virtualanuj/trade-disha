import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { JournalQuery } from '../../api/client'
import type { PaperTradeDetailOut, PaperTradeOut, SignalOut } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { TradeLog } from './TradeLog'

const DAY = 86_400_000

/** NIFTY 25000 CE: filled 101 against a signal at 100, out at the 130 target. */
const win: PaperTradeOut = {
  ...trade,
  id: 'w1',
  status: 'closed',
  exit_price: 130,
  exit_ts: trade.entry_ts + 12 * 60_000,
  exit_reason: 'TARGET',
  exit_fill_quality: 'live',
  gross: 1885,
  net: 1825,
  ltp: null,
  live_gross: null,
  live_net: null,
}
const loss: PaperTradeOut = {
  ...win,
  id: 'l1',
  entry_ts: win.entry_ts + 60 * 60_000,
  exit_ts: win.entry_ts + 70 * 60_000,
  exit_price: 85,
  exit_reason: 'SQUARE_OFF',
  exit_fill_quality: 'stale',
  exit_price_age_ms: 300_000,
  gross: -1040,
  net: -1100,
}
/** a GOLD short the day before */
const gold: PaperTradeOut = {
  ...win,
  id: 'g1',
  index: 'GOLD',
  direction: 'SELL_FUT',
  trading_symbol: 'GOLD FUT 05 DEC 26',
  qty: 100,
  entry_ts: win.entry_ts - DAY,
  exit_ts: win.entry_ts - DAY + 30 * 60_000,
  signal_entry: 135_000,
  entry_price: 135_000,
  slippage: 0,
  target_price: 134_000,
  stop_price: 135_500,
  exit_price: 134_000,
  gross: 100_000,
  net: 99_800,
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
  breakdown: {
    indicators: [
      {
        name: 'ema_cross',
        group: 'trend',
        score: 0.8,
        note: 'EMA9 above EMA21 by 0.10%',
        quality: 'ok',
        value: {},
        weight: 0.4,
        contribution: 0.32,
        enabled: true,
      },
    ],
    group_scores: { trend: 0.8 },
    group_weights: { trend: 0.4 },
    is_expiry_day: false,
  },
  expires_at: trade.entry_ts + 300_000,
  status: 'traded',
  status_ts: trade.entry_ts,
  entry_ask: 100.5,
  spread_pct: 0.42,
  entry_mode: 'trigger',
  shadow: false,
  flow_score: 0.71,
  config_version: 7,
  outcome: {
    result: 'target',
    result_ts: trade.entry_ts + 11 * 60_000,
    end_ts: trade.entry_ts + 60 * 60_000,
    best_price: 134,
    best_ts: trade.entry_ts + 20 * 60_000,
    best_pct: 34,
    worst_price: 97,
    worst_ts: trade.entry_ts + 60_000,
    worst_pct: -3,
    px_1m: 98,
    px_5m: 112,
    px_15m: 131,
    spot_pre_move: null,
    spot_best_move: null,
    late_share: null,
    final: true,
  },
  live: null,
}

const detailOf = (t: PaperTradeOut): PaperTradeDetailOut => ({ trade: t, signal })

function setup(trades: PaperTradeOut[] = [win, loss, gold]) {
  const load = vi.fn<(q: JournalQuery, signal: AbortSignal) => Promise<PaperTradeOut[]>>(() =>
    Promise.resolve(trades),
  )
  const loadDetail = vi.fn<(id: string, signal?: AbortSignal) => Promise<PaperTradeDetailOut>>(
    (id) => {
      const t = trades.find((x) => x.id === id)
      return t ? Promise.resolve(detailOf(t)) : Promise.reject(new Error('unknown trade'))
    },
  )
  render(
    <TradeLog
      markets={['NIFTY', 'BANKNIFTY', 'GOLD', 'SILVER']}
      revision={0}
      load={load}
      loadDetail={loadDetail}
    />,
  )
  return { load, loadDetail }
}

const toggle = (id: string) => screen.getByTestId(`trade-toggle-${id}`)

describe('TradeLog', () => {
  it('asks only for closed trades, and passes the market and dates', async () => {
    const { load } = setup()
    await screen.findByTestId('trade-w1')
    expect(load).toHaveBeenLastCalledWith(
      { index: '', from: '', to: '', status: 'closed' },
      expect.any(AbortSignal),
    )
    fireEvent.change(screen.getByLabelText('Market'), { target: { value: 'GOLD' } })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } })
    await waitFor(() => {
      expect(load).toHaveBeenLastCalledWith(
        { index: 'GOLD', from: '2026-11-01', to: '', status: 'closed' },
        expect.any(AbortSignal),
      )
    })
  })

  it('groups trades by day, newest first, with each day’s result', async () => {
    setup([gold, win, loss])
    const days = await screen.findAllByTestId(/^day-/)
    expect(days.map((d) => d.dataset.testid)).toEqual(['day-15/11/2023', 'day-14/11/2023'])
    const today = days[0]
    if (!today) throw new Error('no day')
    expect(today).toHaveTextContent('2 trades')
    expect(today).toHaveTextContent('1 won · 1 lost')
    expect(today).toHaveTextContent('+₹725')
    expect(days[1]).toHaveTextContent('1 trade')
    expect(days[1]).toHaveTextContent('+₹99,800')
    const order = screen.getAllByTestId(/^trade-[wlg]1$/).map((r) => r.dataset.testid)
    expect(order).toEqual(['trade-l1', 'trade-w1', 'trade-g1'])
    expect(screen.getByTestId('trade-g1')).toHaveTextContent('GOLD FUT short')
    expect(screen.getByTestId('trade-l1')).toHaveTextContent('stale price 5m old')
  })

  it('filters by exit reason and fill on the page, without asking the server again', async () => {
    const { load } = setup()
    await screen.findByTestId('trade-w1')
    fireEvent.change(screen.getByLabelText('Exit'), { target: { value: 'SQUARE_OFF' } })
    expect(screen.getByTestId('trade-l1')).toBeInTheDocument()
    expect(screen.queryByTestId('trade-w1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('trade-g1')).not.toBeInTheDocument()
    expect(screen.getByTestId('day-15/11/2023')).toHaveTextContent('1 trade')

    fireEvent.change(screen.getByLabelText('Fill'), { target: { value: 'live' } })
    expect(await screen.findByText('No closed paper trades match.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Exit'), { target: { value: '' } })
    expect(screen.getAllByTestId(/^trade-[wlg]1$/)).toHaveLength(2)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('says so when no trade matches', async () => {
    setup([])
    expect(await screen.findByText('No closed paper trades match.')).toBeInTheDocument()
  })

  it('opens a trade’s detail on click: levels, signal, outcome and evidence', async () => {
    const { loadDetail } = setup()
    await screen.findByTestId('trade-w1')
    expect(toggle('w1')).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle('w1'))
    expect(toggle('w1')).toHaveAttribute('aria-expanded', 'true')
    const detail = await screen.findByTestId('trade-detail-w1')
    expect(loadDetail).toHaveBeenCalledWith('w1', expect.any(AbortSignal))

    const facts = within(detail)
    expect(facts.getByTestId('fact-fill')).toHaveTextContent('100.00 → 101.00')
    expect(facts.getByTestId('fact-fill')).toHaveTextContent('+1.00')
    // risk 101 − 85 = 16, reward 130 − 101 = 29
    expect(facts.getByTestId('fact-rr')).toHaveTextContent('1 : 1.8')
    // risk in money 16 × 65 = 1,040; net 1,825 is 1.8 R
    expect(facts.getByTestId('fact-r')).toHaveTextContent('+1.8 R')
    expect(facts.getByTestId('fact-net')).toHaveTextContent('+₹1,825')
    expect(facts.getByTestId('fact-bias')).toHaveTextContent('+0.620 · strength 62')
    expect(facts.getByTestId('fact-rule')).toHaveTextContent('order-flow trigger')
    expect(facts.getByTestId('fact-spread')).toHaveTextContent('0.42%')
    expect(facts.getByRole('button', { name: 'Config version 7' })).toBeInTheDocument()
    expect(facts.getByTestId('fact-result')).toHaveTextContent('target')
    expect(facts.getByTestId('fact-best')).toHaveTextContent('134.00 (+34.0%)')
    expect(facts.getByTestId('fact-later')).toHaveTextContent('98.00 · 112.00 · 131.00')
    expect(facts.getByText('EMA9 above EMA21 by 0.10%')).toBeInTheDocument()
  })

  it('works the risk out from the other side for a short future', async () => {
    setup()
    await screen.findByTestId('trade-g1')
    fireEvent.click(toggle('g1'))
    const detail = await screen.findByTestId('trade-detail-g1')
    // risk 135,500 − 135,000 = 500, reward 135,000 − 134,000 = 1,000
    expect(within(detail).getByTestId('fact-rr')).toHaveTextContent('1 : 2.0')
  })

  it('keeps a loaded detail: closing and opening again does not refetch', async () => {
    const { loadDetail } = setup()
    await screen.findByTestId('trade-w1')
    fireEvent.click(toggle('w1'))
    await screen.findByTestId('trade-detail-w1')
    fireEvent.click(toggle('w1'))
    expect(screen.queryByTestId('trade-detail-w1')).not.toBeInTheDocument()
    fireEvent.click(toggle('w1'))
    expect(await screen.findByTestId('trade-detail-w1')).toBeInTheDocument()
    expect(loadDetail).toHaveBeenCalledTimes(1)
  })

  it('shows a failed detail and tries again on request', async () => {
    const { loadDetail } = setup()
    await screen.findByTestId('trade-w1')
    loadDetail.mockRejectedValueOnce(new Error('server down'))
    fireEvent.click(toggle('w1'))
    expect(await screen.findByRole('alert')).toHaveTextContent('server down')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('trade-detail-w1')).toBeInTheDocument()
    expect(loadDetail).toHaveBeenCalledTimes(2)
  })

  it('still shows the trade when its signal is missing', async () => {
    const load = vi.fn(() => Promise.resolve([win]))
    const loadDetail = vi.fn(() => Promise.resolve({ trade: win, signal: null }))
    render(<TradeLog markets={['NIFTY']} revision={0} load={load} loadDetail={loadDetail} />)
    await screen.findByTestId('trade-w1')
    await act(async () => {
      fireEvent.click(toggle('w1'))
      await Promise.resolve()
    })
    const detail = await screen.findByTestId('trade-detail-w1')
    expect(detail).toHaveTextContent('The signal for this trade was not found.')
    expect(within(detail).getByTestId('fact-net')).toHaveTextContent('+₹1,825')
  })

  it('refetches the list when a trade changes', async () => {
    const load = vi.fn(() => Promise.resolve([win]))
    const loadDetail = vi.fn(() => Promise.resolve(detailOf(win)))
    const { rerender } = render(
      <TradeLog markets={['NIFTY']} revision={0} load={load} loadDetail={loadDetail} />,
    )
    await screen.findByTestId('trade-w1')
    rerender(<TradeLog markets={['NIFTY']} revision={1} load={load} loadDetail={loadDetail} />)
    await waitFor(() => {
      expect(load).toHaveBeenCalledTimes(2)
    })
  })
})
