import { render, screen } from '@testing-library/react'

import type { BannerOut, BullionStatusOut, HealthResponse } from '../../api/types'
import { currentBanner } from './banner'
import { StatusBanner } from './StatusBanner'

function health(banner: BannerOut | null, bullion: BullionStatusOut | null = null): HealthResponse {
  return {
    status: 'ok',
    app: 'tradedisha',
    version: '0.1.0',
    milestone: 1,
    market_status: 'live',
    now_ms: 0,
    auth: 'valid',
    feed: {
      state: 'connected',
      last_tick_ts: null,
      tick_age_ms: null,
      reconnects: 0,
      subscribed: 0,
      provider: 'upstox',
    },
    replay_day: null,
    feed_live: banner === null,
    banner,
    bullion,
    serves_frontend: false,
  }
}

describe('StatusBanner', () => {
  it('shows nothing when all is well', () => {
    const { container } = render(<StatusBanner banner={currentBanner(health(null), 'open')} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('says since when the data is stale during a feed outage', () => {
    const b = currentBanner(
      health({ code: 'feed_gap', level: 'error', since_ms: 1_794_548_100_000 }),
      'open',
    )
    render(<StatusBanner banner={b} />)
    const el = screen.getByRole('alert')
    expect(el).toHaveTextContent(
      /Feed is not delivering prices.*last known data from \d\d:\d\d:\d\d/,
    )
    expect(b?.stale).toBe(true)
  })

  it('offers the login when it is missing or expired', () => {
    render(
      <StatusBanner
        banner={currentBanner(
          health({ code: 'login_expired', level: 'error', since_ms: null }),
          'open',
        )}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('expired')
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/api/auth/login')
  })

  it('treats a closed market as information, not an error', () => {
    const b = currentBanner(
      health({ code: 'market_closed', level: 'info', since_ms: null }),
      'open',
    )
    render(<StatusBanner banner={b} />)
    expect(screen.getByRole('status')).toHaveTextContent(/market closed/i)
    expect(b?.stale).toBe(false)
  })

  it('makes a closed market hard to miss: a titled, amber band', () => {
    const b = currentBanner(
      health({ code: 'market_closed', level: 'info', since_ms: null }),
      'open',
    )
    render(<StatusBanner banner={b} />)
    const el = screen.getByRole('status')
    expect(el).toHaveClass('bg-warn/15')
    expect(el).toHaveClass('text-sm')
    expect(screen.getByText('NSE market closed')).toHaveClass('font-semibold')
    expect(el).toHaveTextContent(/09:15 to 15:30 IST/)
  })

  it('puts a lost backend connection above everything else', () => {
    const b = currentBanner(health(null), 'closed')
    expect(b?.text).toMatch(/Lost connection to the TradeDisha backend/)
    expect(b?.stale).toBe(true)
  })

  describe('on the BULLION tab (MCX keeps its own hours)', () => {
    const closed: BannerOut = { code: 'market_closed', level: 'info', since_ms: null }

    it('hides the NSE "market closed" banner while MCX is live', () => {
      expect(currentBanner(health(closed, { status: 'live', since_ms: null }), 'open', true)).toBe(
        null,
      )
      expect(currentBanner(health(closed, { status: 'live', since_ms: null }), 'open')?.title).toBe(
        'NSE market closed',
      )
    })

    it('says since when bullion prices are stale and dims them', () => {
      const b = currentBanner(
        health(closed, { status: 'stale', since_ms: 1_794_548_100_000 }),
        'open',
        true,
      )
      expect(b?.level).toBe('error')
      expect(b?.text).toMatch(/Bullion prices are not updating from \d\d:\d\d:\d\d/)
      expect(b?.stale).toBe(true)
    })

    it('says MCX is closed or on holiday', () => {
      expect(
        currentBanner(health(null, { status: 'closed', since_ms: null }), 'open', true)?.title,
      ).toBe('MCX closed')
      expect(
        currentBanner(health(null, { status: 'holiday', since_ms: null }), 'open', true)?.title,
      ).toBe('MCX holiday')
    })

    it('still warns of an index outage, without dimming live bullion', () => {
      const gap: BannerOut = { code: 'feed_gap', level: 'error', since_ms: 1_794_548_100_000 }
      const b = currentBanner(health(gap, { status: 'live', since_ms: null }), 'open', true)
      expect(b?.text).toMatch(/Feed is not delivering prices/)
      expect(b?.stale).toBe(false)
    })

    it('keeps the login banner first', () => {
      const login: BannerOut = { code: 'login_expired', level: 'error', since_ms: null }
      const b = currentBanner(health(login, { status: 'live', since_ms: null }), 'open', true)
      expect(b?.login).toBe(true)
    })
  })
})
