import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { HealthResponse } from '../../api/types'
import { fmtTickAge, tickAgeColour } from '../../lib/format'
import { OPEN_DELAY_MS } from '../HoverCard/HoverCard'
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
    const feed = screen.getByTestId('feed-pill')
    expect(feed).toHaveTextContent(/Feed\s*400ms/)
    expect(feed).not.toHaveTextContent('connected')
    expect(feed).toHaveAttribute('title', expect.stringContaining('synthetic feed, connected'))
    expect(screen.getByText('No login needed')).toBeInTheDocument()
  })

  it('keeps the tick age a fixed width, so a changing number never moves what follows', () => {
    const bar = (now: number) => (
      <TopBar
        health={health}
        ws="open"
        now={now}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />
    )
    const { rerender } = render(bar(1400))
    const age = () => screen.getByText(/^(\d+ms|[\d.]+s|\d+[mh])$/)
    expect(age()).toHaveTextContent('400ms')
    expect(age()).toHaveClass('w-[5ch]', 'tabular-nums')
    rerender(bar(13_400))
    expect(age()).toHaveTextContent('12.4s')
    expect(age()).toHaveClass('w-[5ch]', 'tabular-nums')
  })

  it.each([
    [null, '—'],
    [0, '0ms'],
    [999, '999ms'],
    [1_000, '1.0s'],
    [59_949, '59.9s'],
    [60_000, '1m'],
    [3_599_999, '59m'],
    [3_600_000, '1h'],
    [86_400_000, '24h'],
  ] as const)('writes a tick age of %s ms as %s, never wider than five', (ms, text) => {
    expect(fmtTickAge(ms)).toBe(text)
    expect(fmtTickAge(ms).length).toBeLessThanOrEqual(5)
  })

  it('takes the brand home to the dashboard, and puts the page tabs on the right', () => {
    const onView = vi.fn()
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
        view="journal"
        onView={onView}
      />,
    )
    const home = screen.getByRole('link', { name: 'TradeDisha' })
    expect(home).toHaveAttribute('href', '/')
    fireEvent.click(home)
    expect(onView).toHaveBeenCalledWith('dashboard')

    // the tabs come after the status strip, with the tools
    const status = screen.getByRole('group', { name: 'Status' })
    const pages = screen.getByRole('navigation', { name: 'Pages' })
    const latency = screen.getByRole('button', { name: 'Latency' })
    const follows = (a: Element, b: Element) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
    expect(follows(status, pages)).toBe(true)
    expect(follows(pages, latency)).toBe(true)
  })

  it('puts Logout last, after the tools, and offers the theme by name', () => {
    render(
      <TopBar
        health={{ ...health, auth: 'valid' }}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
        view="dashboard"
        onView={noop}
        onLogout={() => Promise.resolve()}
      />,
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons.at(-1)).toHaveTextContent('Logout')
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Status' })).toHaveTextContent('Login: valid')
  })

  it('spells out a feed state other than connected', () => {
    const down: HealthResponse = { ...health, feed: { ...health.feed, state: 'disconnected' } }
    render(
      <TopBar
        health={down}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
      />,
    )
    expect(screen.getByTestId('feed-pill')).toHaveTextContent('Feed: disconnected')
    expect(screen.getByTestId('feed-pill')).toHaveClass('text-bear')
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
    const login = screen.getByRole('link', { name: 'Login' })
    expect(login).toHaveAttribute('href', '/api/auth/login')
    expect(login.parentElement?.lastElementChild).toBe(login)
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

  it('logs out after a confirm and waits for the server', async () => {
    let finish: () => void = noop
    const onLogout = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
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
        onLogout={onLogout}
      />,
    )
    const button = screen.getByRole('button', { name: 'Logout' })
    expect(button.parentElement?.lastElementChild).toBe(button)
    fireEvent.click(button)
    expect(onLogout).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm logout?' }))
    expect(onLogout).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Logging out…' })).toBeDisabled()
    await act(async () => {
      finish()
      await Promise.resolve()
    })
    expect(screen.getByRole('button', { name: 'Logout' })).toBeEnabled()
  })

  it('shows why a logout failed', async () => {
    const onLogout = vi.fn(() => Promise.reject(new Error('Upstox is down')))
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
        onLogout={onLogout}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm logout?' }))
    expect(await screen.findByText('Upstox is down')).toBeInTheDocument()
  })

  it('offers no logout without a valid login or a handler', () => {
    const { rerender } = render(
      <TopBar
        health={{ ...health, auth: 'missing' }}
        ws="open"
        now={0}
        lastTickTs={null}
        theme="dark"
        onToggleTheme={noop}
        debug={false}
        onToggleDebug={noop}
        onLogout={() => Promise.resolve()}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Logout' })).not.toBeInTheDocument()
    rerender(
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
    expect(screen.queryByRole('button', { name: 'Logout' })).not.toBeInTheDocument()
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
    rerender(<TopBar {...base} view="journal" onView={noop} onToggleNews={noop} />)
    expect(screen.queryByRole('button', { name: 'Headlines' })).not.toBeInTheDocument()
    rerender(<TopBar {...base} view="trades" onView={noop} onToggleNews={noop} />)
    expect(screen.queryByRole('button', { name: 'Headlines' })).not.toBeInTheDocument()
  })

  it('switches between the dashboard, the journal and the trades page', () => {
    const onView = vi.fn()
    const base = {
      health,
      ws: 'open' as const,
      now: 1400,
      lastTickTs: 1000,
      theme: 'dark' as const,
      onToggleTheme: noop,
      debug: false,
      onToggleDebug: noop,
      onView,
      openTradeCount: 2,
    }
    const { rerender } = render(<TopBar {...base} view="dashboard" />)
    const pages = within(screen.getByRole('navigation', { name: 'Pages' }))
    expect(pages.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-pressed', 'true')
    const trades = pages.getByRole('button', { name: /Trades/ })
    expect(trades).toHaveTextContent('Trades2')
    expect(within(trades).getByTitle('2 open paper trades')).toHaveTextContent('2')
    fireEvent.click(pages.getByRole('button', { name: /Trades/ }))
    expect(onView).toHaveBeenLastCalledWith('trades')

    rerender(<TopBar {...base} view="trades" />)
    expect(pages.getByRole('button', { name: 'Trades' })).toHaveAttribute('aria-pressed', 'true')
    expect(pages.getByRole('button', { name: 'Dashboard' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    fireEvent.click(pages.getByRole('button', { name: /Journal/ }))
    expect(onView).toHaveBeenLastCalledWith('journal')
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

vi.mock('../DebugOverlay/DebugOverlay', () => ({
  LatencyPeek: () => <div data-testid="latency-peek" />,
}))

describe('TopBar hover cards (E27)', () => {
  const bar = (view: 'dashboard' | 'trades', debug = false) =>
    render(
      <TopBar
        health={health}
        ws="open"
        now={1400}
        lastTickTs={1000}
        theme="dark"
        onToggleTheme={noop}
        debug={debug}
        onToggleDebug={noop}
        view={view}
        onView={noop}
        tradesPeek={<div data-testid="trades-peek" />}
      />,
    )
  const hover = (el: Element) => {
    fireEvent.mouseEnter(el)
    act(() => {
      vi.advanceTimersByTime(OPEN_DELAY_MS)
    })
  }

  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('previews the open trades on the Trades tab, but not on the Trades page', () => {
    const { unmount } = bar('dashboard')
    hover(screen.getByRole('button', { name: /Trades/ }))
    expect(screen.getByRole('tooltip', { name: 'Open trades' })).toContainElement(
      screen.getByTestId('trades-peek'),
    )
    unmount()
    bar('trades')
    hover(screen.getByRole('button', { name: /Trades/ }))
    expect(screen.queryByTestId('trades-peek')).not.toBeInTheDocument()
  })

  it('previews the latency, but not while the overlay is on', () => {
    const { unmount } = bar('dashboard')
    hover(screen.getByRole('button', { name: 'Latency' }))
    expect(screen.getByRole('tooltip', { name: 'Latency' })).toContainElement(
      screen.getByTestId('latency-peek'),
    )
    unmount()
    bar('dashboard', true)
    hover(screen.getByRole('button', { name: 'Latency' }))
    expect(screen.queryByTestId('latency-peek')).not.toBeInTheDocument()
  })
})
