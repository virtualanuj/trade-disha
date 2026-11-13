import { render, screen } from '@testing-library/react'

import type { BannerOut, HealthResponse } from '../../api/types'
import { currentBanner } from './banner'
import { StatusBanner } from './StatusBanner'

function health(banner: BannerOut | null): HealthResponse {
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
    expect(screen.getByRole('status')).toHaveTextContent('Market closed')
    expect(b?.stale).toBe(false)
  })

  it('puts a lost backend connection above everything else', () => {
    const b = currentBanner(health(null), 'closed')
    expect(b?.text).toMatch(/Lost connection to the TradeDisha backend/)
    expect(b?.stale).toBe(true)
  })
})
