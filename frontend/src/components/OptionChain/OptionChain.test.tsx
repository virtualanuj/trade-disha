import { render, screen } from '@testing-library/react'

import type { ChainOut, LegOut } from '../../api/types'
import { oiHeat } from '../../lib/chain'
import { OptionChain } from './OptionChain'

const leg = (over: Partial<LegOut> = {}): LegOut => ({
  ltp: 100,
  chg_pct: 1.5,
  oi: 1_250_000,
  oi_chg_open: 50_000,
  oi_chg_min: 1_000,
  iv: 13.2,
  buildup: 'long_buildup',
  ...over,
})

const chain: ChainOut = {
  index: 'NIFTY',
  expiry: '2026-11-17',
  step: 50,
  atm: 25000,
  spot: 25010,
  pcr: 1.18,
  max_pain: 25050,
  total_ce_oi: 3_000_000,
  total_pe_oi: 3_540_000,
  oi_baseline: 'session_open',
  max_abs_oi_chg: 50_000,
  updated_ts: 1_700_000_000_000,
  rows: [
    { strike: 24950, ce: leg(), pe: leg({ oi_chg_open: -20_000, buildup: 'long_unwinding' }) },
    { strike: 25000, ce: leg(), pe: leg() },
    { strike: 25050, ce: leg({ oi: null, oi_chg_open: null }), pe: leg() },
  ],
}

describe('OptionChain', () => {
  it('shows PCR, max pain and highlights the ATM row', () => {
    render(<OptionChain chain={chain} />)
    expect(screen.getByTestId('chain-summary')).toHaveTextContent('1.18')
    expect(screen.getByTestId('chain-summary')).toHaveTextContent('25050')
    expect(screen.getByTestId('atm-row')).toHaveTextContent('25000')
    expect(screen.getAllByText('12.5L').length).toBeGreaterThan(0)
    expect(screen.getAllByTitle('Long unwinding')).toHaveLength(2)
  })

  it('renders a placeholder without a chain', () => {
    render(<OptionChain chain={undefined} />)
    expect(screen.getByText(/Waiting for option chain/)).toBeInTheDocument()
  })

  it('oiHeat is log-scaled and bounded', () => {
    expect(oiHeat(null, 100)).toBe(0)
    expect(oiHeat(0, 100)).toBe(0)
    expect(oiHeat(100, 100)).toBe(1)
    expect(oiHeat(10, 100)).toBeGreaterThan(0.4)
    expect(oiHeat(-500, 100)).toBe(1)
  })
})
