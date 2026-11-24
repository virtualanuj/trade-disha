import { useEffect, useState, type ReactNode } from 'react'

import type { HealthResponse } from '../../api/types'
import { fmtAge, fmtDate, fmtIstTime, tickAgeColour } from '../../lib/format'
import type { WsState } from '../../state/store'
import type { Theme } from '../../theme/useTheme'

interface Props {
  health: HealthResponse | null
  ws: WsState
  now: number
  /** newest tick of the market on screen: the indices, or MCX bullion on its tab */
  lastTickTs: number | null
  /** the BULLION tab is selected: market and feed follow MCX hours, not NSE */
  bullionTab?: boolean
  theme: Theme
  onToggleTheme: () => void
  debug: boolean
  onToggleDebug: () => void
  configControl?: ReactNode
  dataControl?: ReactNode
  /** which page is showing; omitted hides the Journal button */
  view?: 'dashboard' | 'journal'
  onToggleView?: () => void
  openTradeCount?: number
  /** a panel is minimised */
  panelsChanged?: boolean
  onRestorePanels?: () => void
  /** the headlines are taken out of the right-hand column (E10) */
  newsHidden?: boolean
  /** shows the Headlines toggle on the dashboard */
  onToggleNews?: () => void
  /** ends the Upstox login; resolves once the server has done it. Omitted hides Logout. */
  onLogout?: (() => Promise<void>) | undefined
}

const MARKET_LABEL: Record<HealthResponse['market_status'], string> = {
  pre_open: 'PRE-OPEN',
  live: 'LIVE',
  closed: 'CLOSED',
  holiday: 'HOLIDAY',
}

/** MCX session for the BULLION tab; a stale feed is still an open market. */
function mcxStatus(health: HealthResponse | null): HealthResponse['market_status'] | undefined {
  const b = health?.bullion?.status
  return b === 'stale' ? 'live' : b
}

/** Whether silence from the market on screen would be a fault (it is open, or ticking). */
function ticksExpected(health: HealthResponse | null, bullionTab: boolean): boolean {
  if (bullionTab) return mcxStatus(health) === 'live'
  return health?.market_status === 'live' || health?.feed_live === true
}

function MarketPill({
  health,
  now,
  bullionTab,
}: {
  health: HealthResponse | null
  now: number
  bullionTab: boolean
}) {
  const status = bullionTab ? mcxStatus(health) : health?.market_status
  const colour =
    status === 'live' ? 'text-bull' : status === 'pre_open' ? 'text-warn' : 'text-fg-muted'
  return (
    <span className={`flex items-center gap-2 ${colour}`} data-testid="market-pill">
      <span aria-hidden="true">●</span>
      <span className="font-medium">
        {bullionTab ? 'MCX ' : ''}
        {status ? MARKET_LABEL[status] : '…'}
      </span>
      <span className="font-mono text-fg-muted">{fmtIstTime(now)} IST</span>
    </span>
  )
}

function FeedPill({
  health,
  ws,
  now,
  lastTickTs,
  bullionTab,
}: {
  health: HealthResponse | null
  ws: WsState
  now: number
  lastTickTs: number | null
  bullionTab: boolean
}) {
  if (ws !== 'open') {
    return (
      <span className="text-bear" data-testid="feed-pill">
        ● Backend: {ws === 'connecting' ? 'connecting…' : 'disconnected, retrying'}
      </span>
    )
  }
  const feed = health?.feed
  const age = lastTickTs == null ? null : Math.max(0, now - lastTickTs)
  const state = feed?.state ?? 'disconnected'
  // Silence from a closed market is expected: only a fresh tick is worth colouring then.
  const ageColour = tickAgeColour(age)
  const quietOk = !ticksExpected(health, bullionTab) && ageColour !== 'text-bull'
  const colour = state !== 'connected' ? 'text-bear' : quietOk ? 'text-fg-muted' : ageColour
  return (
    <span
      className={colour}
      data-testid="feed-pill"
      title={`${String(feed?.subscribed ?? 0)} instruments`}
    >
      ● Feed: {state}
      {feed ? <span className="text-fg-muted"> ({feed.provider})</span> : null}
      <span className="ml-2 font-mono">{fmtAge(age)}</span>
    </span>
  )
}

const CONFIRM_MS = 4000

function AuthPill({ health }: { health: HealthResponse | null }) {
  const auth = health?.auth
  if (auth === 'not_required') {
    return <span className="text-fg-muted">No login needed</span>
  }
  if (auth === 'valid') {
    return <span className="text-bull">Login: valid</span>
  }
  return <span className="text-warn">Login: {auth ?? '…'}</span>
}

/** The rightmost control: Login while there is no valid login, Logout once there is. */
function AuthButton({
  health,
  onLogout,
}: {
  health: HealthResponse | null
  onLogout?: (() => Promise<void>) | undefined
}) {
  const auth = health?.auth
  if (auth === 'valid') {
    return onLogout ? <LogoutButton onLogout={onLogout} /> : null
  }
  if (auth === 'missing' || auth === 'expired') {
    return (
      <a
        href="/api/auth/login"
        className="rounded border border-border px-2 py-0.5 text-fg hover:border-accent hover:text-accent"
        title="Sign in to Upstox to start the live feed (needed once a day)"
      >
        Login
      </a>
    )
  }
  return null
}

/** Two clicks: the first asks, the second logs out. The ask lapses after a few seconds. */
function LogoutButton({ onLogout }: { onLogout: () => Promise<void> }) {
  const [step, setStep] = useState<'idle' | 'confirm' | 'busy'>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (step !== 'confirm') return
    const t = setTimeout(() => {
      setStep('idle')
    }, CONFIRM_MS)
    return () => {
      clearTimeout(t)
    }
  }, [step])

  const click = () => {
    if (step === 'idle') {
      setError(null)
      setStep('confirm')
      return
    }
    setStep('busy')
    onLogout()
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'logout failed')
      })
      .finally(() => {
        setStep('idle')
      })
  }

  const label = step === 'confirm' ? 'Confirm logout?' : step === 'busy' ? 'Logging out…' : 'Logout'
  return (
    <>
      <button
        type="button"
        onClick={click}
        disabled={step === 'busy'}
        className={`rounded border px-2 py-0.5 hover:border-accent hover:text-accent disabled:opacity-60 ${
          step === 'confirm' ? 'border-warn text-warn' : 'border-border text-fg'
        }`}
        title="End the Upstox login now; the live feed stops until you log in again"
      >
        {label}
      </button>
      {error ? <span className="text-bear">{error}</span> : null}
    </>
  )
}

export function TopBar(props: Props) {
  const { health, ws, now, lastTickTs, theme, onToggleTheme, debug, onToggleDebug, configControl } =
    props
  const { view, onToggleView, openTradeCount = 0, dataControl, bullionTab = false } = props
  const { panelsChanged = false, onRestorePanels, newsHidden = false, onToggleNews } = props
  const { onLogout } = props
  return (
    <header className="flex h-11 items-center gap-4 border-b border-border bg-bg-elev px-4 text-xs whitespace-nowrap">
      <span className="font-semibold tracking-wide">TradeDisha</span>
      <MarketPill health={health} now={now} bullionTab={bullionTab} />
      <FeedPill health={health} ws={ws} now={now} lastTickTs={lastTickTs} bullionTab={bullionTab} />
      <AuthPill health={health} />
      {health?.replay_day ? (
        <span className="text-accent">Replay: {fmtDate(health.replay_day)}</span>
      ) : null}
      <span className="ml-auto" />
      {panelsChanged && onRestorePanels && view !== 'journal' ? (
        <button
          type="button"
          onClick={onRestorePanels}
          className="rounded border border-border px-2 py-0.5 text-accent hover:text-fg"
          title="Expand every minimised panel"
        >
          Restore panels
        </button>
      ) : null}
      {onToggleNews && view !== 'journal' ? (
        <button
          type="button"
          onClick={onToggleNews}
          className={`rounded border border-border px-2 py-0.5 ${newsHidden ? 'text-fg-muted' : 'text-accent'} hover:text-fg`}
          aria-pressed={!newsHidden}
          title={newsHidden ? 'Show the headlines' : 'Hide the headlines'}
        >
          Headlines
        </button>
      ) : null}
      {view && onToggleView ? (
        <button
          type="button"
          onClick={onToggleView}
          className={`rounded border border-border px-2 py-0.5 ${view === 'journal' ? 'text-accent' : 'text-fg-muted'} hover:text-fg`}
          aria-pressed={view === 'journal'}
        >
          {view === 'journal' ? 'Dashboard' : 'Journal'}
          {openTradeCount > 0 && view !== 'journal' ? (
            <span className="ml-1 text-accent" title="open paper trades">
              {openTradeCount} open
            </span>
          ) : null}
        </button>
      ) : null}
      {dataControl}
      {configControl}
      <button
        type="button"
        onClick={onToggleDebug}
        className={`rounded border border-border px-2 py-0.5 ${debug ? 'text-accent' : 'text-fg-muted'} hover:text-fg`}
        aria-pressed={debug}
      >
        Latency
      </button>
      <button
        type="button"
        onClick={onToggleTheme}
        className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        {theme === 'dark' ? 'Light' : 'Dark'}
      </button>
      <AuthButton health={health} onLogout={onLogout} />
    </header>
  )
}
