import { describe, expect, it } from 'vitest'

import type { PaperTradeOut } from '../api/types'
import { trade } from '../components/OpenTrades/fixtures'
import { summarise, summaryScopes } from './tradeStats'

const MIN = 60_000

/** a closed NIFTY call: in at 100, stop 90 (risk 10 x qty), out after `held` minutes */
function closed(id: string, net: number, over: Partial<PaperTradeOut> = {}): PaperTradeOut {
  const entry_ts = over.entry_ts ?? trade.entry_ts
  return {
    ...trade,
    id,
    status: 'closed',
    entry_price: 100,
    stop_price: 90,
    qty: 10,
    cost: 20,
    gross: net + 20,
    net,
    exit_price: 100,
    exit_ts: entry_ts + 10 * MIN,
    exit_reason: net > 0 ? 'TARGET' : 'STOP',
    exit_fill_quality: 'live',
    ltp: null,
    live_gross: null,
    live_net: null,
    ...over,
  }
}

describe('summarise', () => {
  it('is empty-safe', () => {
    const s = summarise([])
    expect(s.closed).toBe(0)
    expect(s.hitRate).toBeNull()
    expect(s.profitFactor).toBeNull()
    expect(s.expectancy).toBeNull()
    expect(s.maxDrawdown).toBe(0)
  })

  it.each([
    {
      name: 'two wins and a loss',
      nets: [300, -100, 200],
      want: { net: 400, wins: 2, losses: 1, hitRate: 2 / 3, profitFactor: 5, avgWin: 250 },
    },
    {
      name: 'a flat trade counts as a loss, as on the server',
      nets: [0, 100],
      want: { net: 100, wins: 1, losses: 1, hitRate: 0.5, profitFactor: null, avgWin: 100 },
    },
  ])('$name', ({ nets, want }) => {
    const s = summarise(nets.map((n, i) => closed(`t${String(i)}`, n)))
    expect(s.net).toBe(want.net)
    expect(s.wins).toBe(want.wins)
    expect(s.losses).toBe(want.losses)
    expect(s.hitRate).toBeCloseTo(want.hitRate)
    if (want.profitFactor === null) expect(s.profitFactor).toBeNull()
    else expect(s.profitFactor).toBeCloseTo(want.profitFactor)
    expect(s.avgWin).toBe(want.avgWin)
    expect(s.expectancy).toBeCloseTo(want.net / nets.length)
  })

  it('works out R, costs, best and worst, the drawdown and the losing streak in exit order', () => {
    const t0 = trade.entry_ts
    // exits in time order: +300, -100, -150, +50, -200 ; cumulative 300, 200, 50, 100, -100
    const trades = [
      closed('a', 300, { entry_ts: t0 }),
      closed('e', -200, { entry_ts: t0 + 40 * MIN }),
      closed('b', -100, { entry_ts: t0 + 10 * MIN }),
      closed('d', 50, { entry_ts: t0 + 30 * MIN }),
      closed('c', -150, { entry_ts: t0 + 20 * MIN }),
    ]
    const s = summarise(trades)
    expect(s.avgR).toBeCloseTo((300 - 200 - 100 + 50 - 150) / 5 / 100) // risk is ₹100 a trade
    expect(s.cost).toBe(100)
    expect(s.gross).toBe(-100 + 100)
    expect(s.best?.id).toBe('a')
    expect(s.worst?.id).toBe('e')
    expect(s.maxDrawdown).toBe(400) // from the 300 peak to -100
    expect(s.lossStreak).toBe(2)
    expect(s.avgHeldMs).toBe(10 * MIN)
    expect(s.byReason).toEqual({ TARGET: 2, STOP: 3 })
  })

  it('keeps open trades apart: counted with their live P&L, never in the results', () => {
    const open: PaperTradeOut = { ...trade, id: 'o', live_net: 590 }
    const s = summarise([closed('a', 100), open])
    expect(s.closed).toBe(1)
    expect(s.net).toBe(100)
    expect(s.open).toBe(1)
    expect(s.unrealised).toBe(590)
  })

  it('counts exits not made on a live price', () => {
    const s = summarise([closed('a', 100, { exit_fill_quality: 'stale' }), closed('b', 100)])
    expect(s.nonLive).toBe(1)
  })
})

describe('summaryScopes', () => {
  it('splits like the server: index options and each index, bullion and each metal, by hand', () => {
    const scopes = summaryScopes([
      closed('n', 100),
      closed('b', 100, { index: 'BANKNIFTY' }),
      closed('g', 100, { index: 'GOLD', direction: 'SELL_FUT' }),
      closed('m', 100, { manual: true }),
    ])
    expect(scopes.map((s) => [s.label, s.summary.closed])).toEqual([
      ['Index options', 2],
      ['BANKNIFTY', 1],
      ['NIFTY', 1],
      ['Bullion', 1],
      ['Opened by hand', 1],
    ])
    expect(scopes.filter((s) => s.total).map((s) => s.label)).toEqual([
      'Index options',
      'Bullion',
      'Opened by hand',
    ])
  })

  it('leaves out groups with no trades, and splits a group only with two markets or more', () => {
    expect(summaryScopes([closed('g', 100, { index: 'SILVER' })]).map((s) => s.label)).toEqual([
      'Bullion',
    ])
  })
})
