import { fireEvent, render, screen, within } from '@testing-library/react'

import type { IndexPrices, IndexStatsOut, ResolvedIndexOut, SectorOut } from '../../api/types'
import { IndexTiles } from './IndexTiles'

const inst = (key: string, type: ResolvedIndexOut['spot']['instrument_type']) => ({
  instrument_key: key,
  trading_symbol: key,
  instrument_type: type,
  expiry: type === 'INDEX' ? null : '2026-11-24',
  strike: null,
  lot_size: 75,
})

const nifty: ResolvedIndexOut = {
  index: 'NIFTY',
  spot: inst('NSE_INDEX|Nifty 50', 'INDEX'),
  future: inst('NSE_FO|NIFTYFUT', 'FUT'),
  options_expiry: '2026-11-17',
  is_expiry_day: false,
  strike_step: 50,
  atm: 25000,
  lot_size: 75,
  strikes: [],
}

const prices: IndexPrices = {
  index: 'NIFTY',
  spot_ltp: 25060,
  spot_ts: 1_700_000_000_000,
  fut_ltp: 25095.5,
  fut_ts: 1_700_000_000_000,
}

const stats: IndexStatsOut = {
  index: 'NIFTY',
  day_open: 25000,
  day_high: 25100,
  day_low: 24980,
  range_pos: 0.6667,
  prev_close: 24900,
  change: 160,
  change_pct: 0.64,
  high_52w: 26300,
  low_52w: 21700,
  fut_premium: 35.5,
  vix: 13.2,
  vix_change_pct: 10,
  updated_ts: 1_700_000_000_000,
  sectors: [],
}

const sector = (label: string, over: Partial<SectorOut> = {}): SectorOut => ({
  name: `Nifty ${label}`,
  label,
  ltp: null,
  prev_close: null,
  change: null,
  change_pct: null,
  ...over,
})

describe('IndexTiles', () => {
  it('renders a placeholder before instruments arrive', () => {
    render(<IndexTiles instruments={[]} prices={{}} />)
    expect(screen.getByText(/Waiting for instruments/)).toBeInTheDocument()
  })

  it('renders spot and futures prices in Indian format', () => {
    render(
      <IndexTiles
        instruments={[nifty]}
        prices={{
          NIFTY: {
            index: 'NIFTY',
            spot_ltp: 25012.5,
            spot_ts: 1_700_000_000_000,
            fut_ltp: 25050,
            fut_ts: 1_700_000_000_000,
          },
        }}
      />,
    )
    expect(screen.getByText('25,012.50')).toBeInTheDocument()
    expect(screen.getByText('25,050.00')).toBeInTheDocument()
    expect(screen.getByText(/exp 17\/11\/2026/)).toBeInTheDocument()
    expect(screen.getByText('Fut 24/11/2026')).toBeInTheDocument()
  })

  it('keeps the details closed until asked, then shows every group', () => {
    render(<IndexTiles instruments={[nifty]} prices={{ NIFTY: prices }} stats={{ NIFTY: stats }} />)
    expect(screen.queryByTestId('index-details')).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /Details/ })
    expect(toggle).toHaveTextContent('+160.00 (+0.64%)') // the day's change shows while closed

    fireEvent.click(toggle)

    const d = screen.getByTestId('index-details')
    expect(d).toHaveTextContent('Open25,000.00')
    expect(d).toHaveTextContent('High25,100.00')
    expect(d).toHaveTextContent('Low24,980.00')
    expect(d).toHaveTextContent('High26,300.00-4.7%')
    expect(d).toHaveTextContent('Low21,700.00+15.5%')
    expect(d).toHaveTextContent('Prev close24,900.00')
    expect(d).toHaveTextContent('Premium over spot+35.50')
    expect(d).toHaveTextContent('VIX13.20+10.00%')
    expect(
      screen.getByRole('img', { name: "Position in the day's range: 67%" }),
    ).toBeInTheDocument()
    expect(localStorage.getItem('tradedisha.detailsOpen')).toBe('true')
  })

  it('shows a dash for what the feed cannot supply', () => {
    localStorage.setItem('tradedisha.detailsOpen', 'true')
    const bare = {
      ...stats,
      prev_close: null,
      change: null,
      change_pct: null,
      high_52w: null,
      low_52w: null,
      vix: null,
      vix_change_pct: null,
    }
    render(<IndexTiles instruments={[nifty]} prices={{ NIFTY: prices }} stats={{ NIFTY: bare }} />)
    const d = screen.getByTestId('index-details')
    expect(d).toHaveTextContent('Prev close—')
    expect(d).toHaveTextContent('VIX—')
    expect(d).toHaveTextContent('High—')
    expect(screen.queryByRole('img', { name: /52-week range/ })).not.toBeInTheDocument()
  })

  it('shows ATM and its strikes in Details, not beside spot and futures', () => {
    const pair = (strike: number) => ({
      strike,
      ce: inst(`NSE_FO|CE${String(strike)}`, 'CE'),
      pe: inst(`NSE_FO|PE${String(strike)}`, 'PE'),
    })
    const withStrikes = { ...nifty, strikes: [24900, 24950, 25000, 25050, 25100].map(pair) }
    render(
      <IndexTiles
        instruments={[withStrikes]}
        prices={{ NIFTY: prices }}
        stats={{ NIFTY: stats }}
      />,
    )
    expect(screen.queryByText('ATM')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Details/ }))
    const d = screen.getByTestId('index-details')
    expect(d).toHaveTextContent('ATM25000')
    expect(d).toHaveTextContent('Strikes5')
  })

  it('shows each sector as a small box: name, value, then change with %, in order', () => {
    const sectors = [
      sector('IT', { ltp: 37880, prev_close: 37416, change: 464, change_pct: 1.24 }),
      sector('Auto', { ltp: 24512.4, prev_close: 24712.4, change: -200, change_pct: -0.81 }),
      sector('Media', { ltp: 1800, prev_close: 1800, change: 0, change_pct: 0 }),
    ]
    render(
      <IndexTiles
        instruments={[nifty]}
        prices={{ NIFTY: prices }}
        stats={{ NIFTY: { ...stats, sectors } }}
      />,
    )
    const block = screen.getByTestId('index-sectors')
    const rows = within(block).getAllByTestId('sector')
    expect(rows.map((r) => [...r.children].map((c) => c.textContent))).toEqual([
      ['IT', '37,880.00', '+464.00 (+1.24%)'],
      ['Auto', '24,512.40', '-200.00 (-0.81%)'],
      ['Media', '1,800.00', '0.00 (0.00%)'],
    ])
    const change = (row: HTMLElement | undefined) => row?.lastElementChild
    expect(change(rows[0])).toHaveClass('text-bull')
    expect(change(rows[1])).toHaveClass('text-bear')
    expect(change(rows[2])).toHaveClass('text-fg-muted')
    expect(rows[0]).toHaveClass('rounded', 'border')
    expect(rows[0]).toHaveAttribute('title', 'Nifty IT · prev close 37,416.00 · +464.00')
  })

  it('shows a dash for a sector without prices', () => {
    render(
      <IndexTiles
        instruments={[nifty]}
        prices={{ NIFTY: prices }}
        stats={{ NIFTY: { ...stats, sectors: [sector('Metal')] } }}
      />,
    )
    const [row] = screen.getAllByTestId('sector')
    expect([...(row?.children ?? [])].map((c) => c.textContent)).toEqual(['Metal', '—', '—'])
    expect(row).toHaveAttribute('title', 'Nifty Metal')
  })

  it('has no sectors block when the index has none', () => {
    render(<IndexTiles instruments={[nifty]} prices={{ NIFTY: prices }} stats={{ NIFTY: stats }} />)
    expect(screen.queryByTestId('index-sectors')).not.toBeInTheDocument()
  })

  it('shows the sector name in readable text, not small and muted', () => {
    render(
      <IndexTiles
        instruments={[nifty]}
        prices={{ NIFTY: prices }}
        stats={{ NIFTY: { ...stats, sectors: [sector('FMCG')] } }}
      />,
    )
    const name = screen.getByText('FMCG')
    expect(name).toHaveClass('text-xs', 'font-semibold', 'text-fg')
    expect(name).not.toHaveClass('text-fg-muted')
  })

  it('collapses the sectors like Details, remembers it, and sums them up while closed', () => {
    const sectors = [
      sector('IT', { ltp: 2, prev_close: 1, change: 1, change_pct: 100 }),
      sector('Auto', { ltp: 2, prev_close: 3, change: -1, change_pct: -33.33 }),
      sector('Pharma', { ltp: 2, prev_close: 1, change: 1, change_pct: 100 }),
      sector('Media', { ltp: 2, prev_close: 2, change: 0, change_pct: 0 }),
      sector('Metal'),
    ]
    const view = () => (
      <IndexTiles
        instruments={[nifty]}
        prices={{ NIFTY: prices }}
        stats={{ NIFTY: { ...stats, sectors } }}
      />
    )
    const { unmount } = render(view())
    const toggle = screen.getByRole('button', { name: /Sectors/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'true') // open by default
    expect(screen.getAllByTestId('sector')).toHaveLength(5)

    fireEvent.click(toggle)
    expect(screen.queryAllByTestId('sector')).toHaveLength(0)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveTextContent('2 up · 1 down')
    expect(localStorage.getItem('tradedisha.sectorsOpen')).toBe('false')

    unmount()
    render(view())
    expect(screen.getByRole('button', { name: /Sectors/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })
})
