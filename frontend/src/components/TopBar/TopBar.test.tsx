import { fireEvent, render, screen } from '@testing-library/react'

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
  feed_live: true,
  banner: null,
  bullion: null,
  serves_frontend: false,
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

  it('offers the Upstox login when the live feed has no valid login', () => {
    render(
      <TopBar
        health={{ ...health, auth: 'missing' }}
        ws="open"
        now={0}
        lastTickTs={null}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />,
    )
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/api/auth/login')
  })

  it('hides the login once it is valid', () => {
    render(
      <TopBar
        health={{ ...health, auth: 'valid' }}
        ws="open"
        now={0}
        lastTickTs={null}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />,
    )
    expect(screen.getByText('Login: valid')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument()
  })

  it('colours tick age green, amber, red', () => {
    expect(tickAgeColour(500)).toBe('text-bull')
    expect(tickAgeColour(5000)).toBe('text-warn')
    expect(tickAgeColour(20_000)).toBe('text-bear')
    expect(tickAgeColour(null)).toBe('text-fg-muted')
  })

  it('offers to restore the panels only while one is minimised', () => {
    const onRestorePanels = vi.fn()
    const bar = (changed: boolean) => (
      <TopBar
        health={health}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
        panelsChanged={changed}
        onRestorePanels={onRestorePanels}
      />
    )
    const { rerender } = render(bar(false))
    expect(screen.queryByRole('button', { name: 'Restore panels' })).not.toBeInTheDocument()
    rerender(bar(true))
    fireEvent.click(screen.getByRole('button', { name: 'Restore panels' }))
    expect(onRestorePanels).toHaveBeenCalledTimes(1)
  })

  it('toggles the headlines, showing whether they are on', () => {
    const onToggleNews = vi.fn()
    const bar = (hidden: boolean) => (
      <TopBar
        health={health}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
        view="dashboard"
        newsHidden={hidden}
        onToggleNews={onToggleNews}
      />
    )
    const { rerender } = render(bar(false))
    const button = screen.getByRole('button', { name: 'Headlines' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(button)
    expect(onToggleNews).toHaveBeenCalledTimes(1)
    rerender(bar(true))
    expect(screen.getByRole('button', { name: 'Headlines' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('has no headlines toggle on the journal or without a handler', () => {
    const base = {
      health,
      ws: 'open' as const,
      now: 1400,
      lastTickTs: 1000,
      theme: 'dark' as const,
      onToggleTheme: noop,
      debug: false,
      onToggleDebug: noop,
    }
    const { rerender } = render(<TopBar {...base} view="dashboard" />)
    expect(screen.queryByRole('button', { name: 'Headlines' })).not.toBeInTheDocument()
    rerender(<TopBar {...base} view="journal" onToggleView={noop} onToggleNews={noop} />)
    expect(screen.queryByRole('button', { name: 'Headlines' })).not.toBeInTheDocument()
  })

  describe('NSE and MCX keep different hours', () => {
    const closedNse: HealthResponse = { ...health, market_status: 'closed', feed_live: false }
    const pill = (h: HealthResponse, bullionTab = false, lastTickTs = 1000) =>
      render(
        <TopBar
          health={h}
          ws="open"
          now={60_000}
          lastTickTs={lastTickTs}
          bullionTab={bullionTab}
          theme="dark"
          onToggleTheme={noop}
          debug={false}
          onToggleDebug={noop}
        />,
      )

    it('does not turn the feed red when the index is quiet because NSE has closed', () => {
      pill(closedNse)
      expect(screen.getByTestId('feed-pill')).toHaveClass('text-fg-muted')
      expect(screen.getByTestId('feed-pill')).not.toHaveClass('text-bear')
    })

    it('still turns it red when the index goes quiet during the session', () => {
      pill({ ...health, feed_live: false })
      expect(screen.getByTestId('feed-pill')).toHaveClass('text-bear')
    })

    it('measures MCX ticks and shows MCX status on the BULLION tab', () => {
      pill({ ...closedNse, bullion: { status: 'live', since_ms: null } }, true, 59_500)
      expect(screen.getByTestId('feed-pill')).toHaveClass('text-bull')
      expect(screen.getByTestId('market-pill')).toHaveTextContent('MCX LIVE')
      expect(screen.getByTestId('market-pill')).toHaveClass('text-bull')
    })

    it('turns bullion red when MCX is open but its ticks stop', () => {
      pill({ ...closedNse, bullion: { status: 'stale', since_ms: 1000 } }, true, 1000)
      expect(screen.getByTestId('feed-pill')).toHaveClass('text-bear')
    })

    it('mutes bullion once MCX has closed', () => {
      pill({ ...closedNse, bullion: { status: 'closed', since_ms: null } }, true, 1000)
      expect(screen.getByTestId('feed-pill')).toHaveClass('text-fg-muted')
      expect(screen.getByTestId('market-pill')).toHaveTextContent('MCX CLOSED')
    })
  })
})
