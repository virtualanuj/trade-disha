import { render, screen, within } from '@testing-library/react'

import type { OutcomeOut, SignalOut } from '../../api/types'
import { SignalHistory } from './SignalHistory'

const FIRED = 1_700_000_060_000

function signal(id: string, outcome: Partial<OutcomeOut> | null, index = 'NIFTY'): SignalOut {
  return {
    id,
    index,
    minute_ts: FIRED - 60_000,
    ts_fired: FIRED,
    direction: 'BUY_CE',
    instrument_key: 'NSE_FO|X',
    trading_symbol: 'NIFTY17NOV2625000CE',
    strike: 25000,
    expiry: '2026-11-17',
    lot_size: 75,
    entry_price: 150,
    target_price: 195,
    stop_price: 127.5,
    target_basis: 'pct',
    target_points: null,
    stop_points: null,
    delta_used: null,
    bias: 0.62,
    strength: 62,
    breakdown: {},
    expires_at: FIRED + 300_000,
    status: 'lapsed',
    status_ts: FIRED + 300_000,
    entry_ask: null,
    spread_pct: null,
    entry_mode: 'minute_close',
    shadow: false,
    flow_score: null,
    outcome:
      outcome === null
        ? null
        : {
            result: 'open',
            result_ts: null,
            end_ts: FIRED + 1_800_000,
            best_price: 150,
            best_ts: FIRED,
            best_pct: 0,
            worst_price: 150,
            worst_ts: FIRED,
            worst_pct: 0,
            px_1m: null,
            px_5m: null,
            px_15m: null,
            spot_pre_move: null,
            spot_best_move: null,
            late_share: null,
            final: false,
            ...outcome,
          },
  }
}

function outcomeCell(id: string): HTMLElement {
  return screen.getByTestId(`outcome-${id}`)
}

describe('SignalHistory outcomes', () => {
  it('shows what each signal went on to do, with its best and worst move', () => {
    render(
      <SignalHistory
        index="NIFTY"
        signals={[
          signal('t', {
            result: 'target',
            result_ts: FIRED + 180_000,
            best_pct: 31.2,
            worst_pct: -2,
          }),
          signal('s', {
            result: 'stop',
            result_ts: FIRED + 120_000,
            best_pct: 0.6,
            worst_pct: -21.4,
          }),
          signal('n', { result: 'neither', result_ts: FIRED + 1_800_000, final: true }),
          signal('o', {}),
          signal('old', null),
        ]}
      />,
    )

    expect(outcomeCell('t')).toHaveTextContent('target')
    expect(outcomeCell('t')).toHaveTextContent('+31.2% / -2.0%')
    expect(within(outcomeCell('t')).getByText('target')).toHaveClass('text-bull')
    expect(within(outcomeCell('s')).getByText('stop')).toHaveClass('text-bear')
    expect(outcomeCell('s')).toHaveTextContent('+0.6% / -21.4%')
    expect(outcomeCell('n')).toHaveTextContent('neither')
    expect(outcomeCell('o')).toHaveTextContent('following')
    expect(outcomeCell('old')).toHaveTextContent('—')
  })

  it('sums up the day for the selected index only', () => {
    render(
      <SignalHistory
        index="NIFTY"
        signals={[
          signal('t', { result: 'target' }),
          signal('s1', { result: 'stop' }),
          signal('s2', { result: 'stop' }),
          signal('o', {}),
          signal('other', { result: 'target' }, 'BANKNIFTY'),
        ]}
      />,
    )

    expect(screen.getByTestId('signal-scorecard')).toHaveTextContent(
      '3 of 4 scored · 1 target · 2 stop · 0 neither',
    )
  })

  it('has no summary line before anything is scored', () => {
    render(<SignalHistory index="NIFTY" signals={[signal('o', {})]} />)

    expect(screen.queryByTestId('signal-scorecard')).toBeNull()
  })

  it('lists shadow signals greyed and tagged, and scores them on their own line', () => {
    const shadow: SignalOut = {
      ...signal('sh', { result: 'target' }),
      shadow: true,
      entry_mode: 'trigger',
    }
    render(<SignalHistory index="NIFTY" signals={[signal('live', { result: 'stop' }), shadow]} />)

    const row = screen.getByTestId('outcome-sh').closest('tr')
    expect(row).toHaveClass('opacity-60')
    expect(row).toHaveTextContent('shadow')
    expect(screen.getByTestId('outcome-live').closest('tr')).not.toHaveClass('opacity-60')
    expect(screen.getByTestId('signal-scorecard')).toHaveTextContent(
      '1 of 1 scored · 0 target · 1 stop · 0 neither',
    )
    expect(screen.getByTestId('shadow-scorecard')).toHaveTextContent(
      'shadow (trigger): 1 of 1 scored · 1 target · 0 stop · 0 neither',
    )
  })
})
