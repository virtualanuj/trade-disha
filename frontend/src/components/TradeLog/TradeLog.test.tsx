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

/** still open: entered two hours after `win`, 111 now, +₹590 net so far */
const opened: PaperTradeOut = { ...trade, id: 'o1', entry_ts: win.entry_ts + 2 * 3_600_000 }
const NOW = opened.entry_ts + 25 * 60_000

interface Extra {
  latest?: PaperTradeOut[]
  closeBlock?: (t: PaperTradeOut) => string | null
}

function setup(trades: PaperTradeOut[] = [win, loss, gold], extra: Extra = {}) {
  const { latest = [], closeBlock } = extra
  const onClose = vi.fn<(id: string) => Promise<unknown>>(() => Promise.resolve({}))
  const load = vi.fn<(q: JournalQuery, signal: AbortSignal) => Promise<PaperTradeOut[]>>(() =>
    Promise.resolve(trades),
  )
  const loadDetail = vi.fn<(id: string, signal?: AbortSignal) => Promise<PaperTradeDetailOut>>(
    (id) => {
      const t = trades.find((x) => x.id === id)
      return t ? Promise.resolve(detailOf(t)) : Promise.reject(new Error('unknown trade'))
    },
  )
  const page = (store: PaperTradeOut[]) => (
    <TradeLog
      markets={['NIFTY', 'BANKNIFTY', 'GOLD', 'SILVER']}
      revision={0}
      latest={store}
      now={NOW}
      load={load}
      loadDetail={loadDetail}
      onClose={onClose}
      closeBlock={closeBlock}
    />
  )
  const { rerender } = render(page(latest))
  return {
    load,
    loadDetail,
    onClose,
    pushLive: (store: PaperTradeOut[]) => {
      rerender(page(store))
    },
  }
}

const toggle = (id: string) => screen.getByTestId(`trade-toggle-${id}`)

describe('TradeLog', () => {
  it('asks for open and closed trades, and passes the market and dates', async () => {
    const { load } = setup()
    await screen.findByTestId('trade-w1')
    expect(load).toHaveBeenLastCalledWith({ index: '', from: '', to: '' }, expect.any(AbortSignal))
    fireEvent.change(screen.getByLabelText('Market'), { target: { value: 'GOLD' } })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } })
    await waitFor(() => {
      expect(load).toHaveBeenLastCalledWith(
        { index: 'GOLD', from: '2026-11-01', to: '' },
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
    expect(await screen.findByText('No paper trades match.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Exit'), { target: { value: '' } })
    expect(screen.getAllByTestId(/^trade-[wlg]1$/)).toHaveLength(2)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('lists open trades first, with live P&L and an unrealised total', async () => {
    setup([opened, win, loss, gold])
    const group = await screen.findByTestId('open-group')
    expect(group).toHaveTextContent('Open now')
    expect(group).toHaveTextContent('1 trade')
    expect(group).toHaveTextContent('unrealised')
    expect(group).toHaveTextContent('+₹590')
    const order = screen.getAllByTestId(/^trade-[owlg]1$/).map((r) => r.dataset.testid)
    expect(order).toEqual(['trade-o1', 'trade-l1', 'trade-w1', 'trade-g1'])
    const row = screen.getByTestId('trade-o1')
    expect(row).toHaveTextContent('111.00') // the price now
    expect(row).toHaveTextContent('open')
    expect(row).toHaveTextContent('25m')
    expect(row).toHaveTextContent('+₹590')
    // the day's result counts only closed trades
    expect(screen.getByTestId('day-15/11/2023')).toHaveTextContent('2 trades')
    expect(screen.getByTestId('day-15/11/2023')).toHaveTextContent('+₹725')
  })

  it('takes the live price from the socket, and moves a trade the moment it closes', async () => {
    const { pushLive, load } = setup([opened, win])
    await screen.findByTestId('trade-o1')
    pushLive([{ ...opened, ltp: 120, live_gross: 1235, live_net: 1175 }])
    expect(screen.getByTestId('trade-o1')).toHaveTextContent('120.00')
    expect(screen.getByTestId('open-group')).toHaveTextContent('+₹1,175')

    const closedNow: PaperTradeOut = {
      ...opened,
      status: 'closed',
      exit_price: 130,
      exit_ts: NOW,
      exit_reason: 'TARGET',
      exit_fill_quality: 'live',
      gross: 1885,
      net: 1825,
    }
    pushLive([closedNow])
    expect(screen.queryByTestId('open-group')).not.toBeInTheDocument()
    expect(screen.getByTestId('trade-o1')).toHaveTextContent('Target')
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('closes an open trade from its row; a closed trade has no button', async () => {
    const { onClose } = setup([opened, win])
    await screen.findByTestId('trade-o1')
    expect(within(screen.getByTestId('trade-w1')).queryByRole('button', { name: /Close/ })).toBe(
      null,
    )
    let finish: (v: unknown) => void = () => undefined
    onClose.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const button = within(screen.getByTestId('trade-o1')).getByRole('button', { name: 'Close' })
    expect(button).toHaveAttribute('title', 'Close at the current price')
    fireEvent.click(button)
    expect(onClose).toHaveBeenCalledWith('o1')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Closing…')
    await act(async () => {
      finish({})
      await Promise.resolve()
    })
    expect(button).toHaveTextContent('Close')
    expect(button).toBeEnabled()
  })

  it('shows why a close was refused', async () => {
    const { onClose } = setup([opened])
    await screen.findByTestId('trade-o1')
    onClose.mockRejectedValueOnce(new Error('feed not live'))
    fireEvent.click(within(screen.getByTestId('trade-o1')).getByRole('button', { name: 'Close' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not closed: feed not live')
  })

  it('cannot close while that market has no live price', async () => {
    const { onClose } = setup([opened], {
      closeBlock: (t) => (t.index === 'NIFTY' ? 'Feed not live: no price to close at' : null),
    })
    await screen.findByTestId('trade-o1')
    const button = within(screen.getByTestId('trade-o1')).getByRole('button', { name: 'Close' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Feed not live: no price to close at')
    fireEvent.click(button)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows only closed trades while an exit or fill filter is set', async () => {
    setup([opened, win])
    await screen.findByTestId('open-group')
    fireEvent.change(screen.getByLabelText('Fill'), { target: { value: 'live' } })
    expect(screen.queryByTestId('open-group')).not.toBeInTheDocument()
    expect(screen.getByTestId('trade-w1')).toBeInTheDocument()
  })

  it('shows an open trade’s detail at the current price', async () => {
    const { pushLive } = setup([opened])
    await screen.findByTestId('trade-o1')
    fireEvent.click(toggle('o1'))
    const detail = within(await screen.findByTestId('trade-detail-o1'))
    expect(detail.getByTestId('fact-exit')).toHaveTextContent('111.00')
    expect(detail.getByTestId('fact-exit')).toHaveTextContent('open')
    expect(detail.getByTestId('fact-held')).toHaveTextContent('25m')
    expect(detail.getByTestId('fact-net')).toHaveTextContent('Net so far')
    expect(detail.getByTestId('fact-net')).toHaveTextContent('+₹590')
    pushLive([{ ...opened, ltp: 120, live_gross: 1235, live_net: 1175 }])
    expect(detail.getByTestId('fact-exit')).toHaveTextContent('120.00')
    expect(detail.getByTestId('fact-net')).toHaveTextContent('+₹1,175')
  })

  it('says so when no trade matches', async () => {
    setup([])
    expect(await screen.findByText('No paper trades match.')).toBeInTheDocument()
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
    render(
      <TradeLog markets={['NIFTY']} now={NOW} revision={0} load={load} loadDetail={loadDetail} />,
    )
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
      <TradeLog markets={['NIFTY']} now={NOW} revision={0} load={load} loadDetail={loadDetail} />,
    )
    await screen.findByTestId('trade-w1')
    rerender(
      <TradeLog markets={['NIFTY']} now={NOW} revision={1} load={load} loadDetail={loadDetail} />,
    )
    await waitFor(() => {
      expect(load).toHaveBeenCalledTimes(2)
    })
  })
})
