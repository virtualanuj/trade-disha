import { render, screen } from '@testing-library/react'

import type { HealthResponse } from '../../api/types'
import { tickAgeColour } from '../../lib/format'
import { TopBar } from './TopBar'

const health: HealthResponse = {
  status: 'ok',
  app: 'tradedisha',
  version: '0.1.0',
  milestone: 1,
  market_status: 'live',
  now_ms: 0,
  auth: 'not_required',
  feed: {
    state: 'connected',
    last_tick_ts: 1000,
    tick_age_ms: 100,
    reconnects: 0,
    subscribed: 44,
    provider: 'synthetic',
  },
  replay_day: null,
}

const noop = () => undefined

describe('TopBar', () => {
  it('shows market status, feed provider and tick age', () => {
    render(
      <TopBar
        health={health}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />,
    )
    expect(screen.getByTestId('market-pill')).toHaveTextContent('LIVE')
    expect(screen.getByTestId('feed-pill')).toHaveTextContent(
      /Feed: connected \(synthetic\)\s*400ms/,
    )
    expect(screen.getByText('No login needed')).toBeInTheDocument()
  })

  it('reports a dropped backend socket', () => {
    render(
      <TopBar
        health={health}
        ws="closed"
        now={0}
        lastTickTs={null}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />,
    )
    expect(screen.getByTestId('feed-pill')).toHaveTextContent('disconnected, retrying')
  })

  it('colours tick age green, amber, red', () => {
    expect(tickAgeColour(500)).toBe('text-bull')
    expect(tickAgeColour(5000)).toBe('text-warn')
    expect(tickAgeColour(20_000)).toBe('text-bear')
    expect(tickAgeColour(null)).toBe('text-fg-muted')
  })
})
