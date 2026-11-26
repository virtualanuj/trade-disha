import { Fragment, useEffect, useState, type ReactNode } from 'react'

import type { HealthResponse } from '../../api/types'
import { fmtDate, fmtIstTime, fmtTickAge, tickAgeColour } from '../../lib/format'
import { toolClass } from '../../lib/toolbar'
import { VIEW_LABEL, VIEWS, type View } from '../../lib/view'
import { LatencyPeek } from '../DebugOverlay/DebugOverlay'
import { HoverCard } from '../HoverCard/HoverCard'
import {
  DashboardIcon,
  JournalIcon,
  LatencyIcon,
  LoginIcon,
  LogoutIcon,
  MoonIcon,
  NewsIcon,
  RestoreIcon,
  SunIcon,
  TradesIcon,
} from '../Icons/Icons'

const VIEW_ICON: Record<View, () => ReactNode> = {
  dashboard: DashboardIcon,
  journal: JournalIcon,
  trades: TradesIcon,
}
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
  /** which page is showing; with `onView`, draws the Dashboard · Journal · Trades buttons */
  view?: View
  onView?: (view: View) => void
  openTradeCount?: number
  /** the Trades tab's hover card (E27); it reads the trades itself, so it is passed in */
  tradesPeek?: ReactNode
  /** a panel is minimised */
  panelsChanged?: boolean
  onRestorePanels?: () => void
  /** the headlines are not on show: taken out of the right-hand column, or minimised */
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
    <span className={`flex items-center gap-1.5 ${colour}`} data-testid="market-pill">
      <span aria-hidden="true">●</span>
      <span className="font-medium">
        {bullionTab ? 'MCX ' : ''}
        {status ? MARKET_LABEL[status] : '…'}
      </span>
      <span className="font-mono tabular-nums text-fg-muted">{fmtIstTime(now)} IST</span>
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
      <span className="flex items-center gap-1.5 text-bear" data-testid="feed-pill">
        <span aria-hidden="true">●</span>
        Backend: {ws === 'connecting' ? 'connecting…' : 'disconnected, retrying'}
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
      className={`flex items-center gap-1.5 ${colour}`}
      data-testid="feed-pill"
      title={
        `${feed?.provider ?? 'no'} feed, ${state}, ${String(feed?.subscribed ?? 0)} instruments` +
        '; the number is the age of the newest tick'
      }
    >
      <span aria-hidden="true">●</span>
      {/* the dot's colour says connected; any other state is spelled out */}
      {state === 'connected' ? 'Feed' : `Feed: ${state}`}
      {/* fixed width and even digits, so a changing age never moves what follows */}
      <span className="inline-block w-[5ch] text-right font-mono tabular-nums">
        {fmtTickAge(age)}
      </span>
    </span>
  )
}

const CONFIRM_MS = 4000

function AuthPill({ health }: { health: HealthResponse | null }) {
  const auth = health?.auth
  if (auth === 'not_required') {
    return <span className="text-fg-muted">No login needed</span>
  }
  const colour = auth === 'valid' ? 'text-bull' : 'text-warn'
  return (
    <span className={`flex items-center gap-1.5 ${colour}`}>
      <span aria-hidden="true">●</span>
      Login: {auth ?? '…'}
    </span>
  )
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
        className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 font-medium whitespace-nowrap text-bg hover:opacity-90"
        title="Sign in to Upstox to start the live feed (needed once a day)"
      >
        <LoginIcon />
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
        className={`inline-flex items-center gap-1.5 rounded-md border bg-bg px-2.5 py-1 whitespace-nowrap hover:border-bear hover:text-bear disabled:opacity-60 ${
          step === 'confirm' ? 'border-warn text-warn' : 'border-border text-fg'
        }`}
        title="End the Upstox login now; the live feed stops until you log in again"
      >
        <LogoutIcon />
        {label}
      </button>
      {error ? <span className="text-bear">{error}</span> : null}
    </>
  )
}

/** A thin rule between groups of the bar. */
function Rule() {
  return <span className="mx-0.5 h-5 w-px shrink-0 bg-border" aria-hidden="true" />
}

/** The pages as tabs: the one place in the bar that changes what the page shows. */
function PageTabs({
  view,
  onView,
  openTradeCount,
  tradesPeek,
}: {
  view: View
  onView: (view: View) => void
  openTradeCount: number
  tradesPeek: ReactNode
}) {
  return (
    <nav
      className="flex items-center gap-0.5 rounded-md border border-border bg-bg p-0.5"
      aria-label="Pages"
    >
      {VIEWS.map((v) => {
        const Icon = VIEW_ICON[v]
        const tab = (
          <button
            key={v}
            type="button"
            onClick={() => {
              onView(v)
            }}
            className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-2 py-0.5 ${
              view === v
                ? 'bg-accent/15 font-medium text-accent'
                : 'text-fg-muted hover:bg-bg-row hover:text-fg'
            }`}
            aria-pressed={view === v}
          >
            <Icon />
            {VIEW_LABEL[v]}
            {v === 'trades' && openTradeCount > 0 && view !== 'trades' ? (
              <span
                className="min-w-4 rounded-full bg-accent px-1 text-center text-[10px] leading-4 font-semibold text-bg"
                title={`${String(openTradeCount)} open paper trade${openTradeCount === 1 ? '' : 's'}`}
                aria-label={`${String(openTradeCount)} open`}
              >
                {openTradeCount}
              </span>
            ) : null}
          </button>
        )
        // hovered, the open trades (E27); not on the Trades page, which lists them
        return v === 'trades' && tradesPeek != null ? (
          <HoverCard key={v} card={view === 'trades' ? null : tradesPeek} label="Open trades">
            {tab}
          </HoverCard>
        ) : (
          <Fragment key={v}>{tab}</Fragment>
        )
      })}
    </nav>
  )
}

/**
 * Left: the brand (a link home, to the dashboard) and a status strip (read only, no
 * borders). Right: the page tabs, the dashboard's view tools, the app's tools, then Login
 * or Logout on its own. The bar wraps
 * onto a second line rather than scroll, so nothing is ever hidden off the edge.
 */
export function TopBar(props: Props) {
  const { health, ws, now, lastTickTs, theme, onToggleTheme, debug, onToggleDebug, configControl } =
    props
  const { view, onView, openTradeCount = 0, tradesPeek, dataControl, bullionTab = false } = props
  const { panelsChanged = false, onRestorePanels, newsHidden = false, onToggleNews } = props
  const { onLogout } = props
  /** panel controls only mean something on the dashboard; no view given is the dashboard */
  const onDashboard = (view ?? 'dashboard') === 'dashboard'
  const restore = panelsChanged && onRestorePanels && onDashboard
  const news = onToggleNews && onDashboard
  return (
    <header className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border bg-bg-elev px-4 py-1.5 text-xs">
      {/* a real link home: a plain click switches page in place, a new tab opens the app */}
      <a
        href="/"
        className="font-semibold tracking-wide whitespace-nowrap hover:text-accent"
        title="Go to the dashboard"
        onClick={(e) => {
          if (!onView || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
          e.preventDefault()
          onView('dashboard')
        }}
      >
        TradeDisha
      </a>
      <div
        className="flex items-center gap-2.5 rounded-md bg-bg px-2.5 py-1 whitespace-nowrap"
        role="group"
        aria-label="Status"
      >
        <MarketPill health={health} now={now} bullionTab={bullionTab} />
        <span className="h-3 w-px bg-border" aria-hidden="true" />
        <FeedPill
          health={health}
          ws={ws}
          now={now}
          lastTickTs={lastTickTs}
          bullionTab={bullionTab}
        />
        <span className="h-3 w-px bg-border" aria-hidden="true" />
        <AuthPill health={health} />
        {health?.replay_day ? (
          <>
            <span className="h-3 w-px bg-border" aria-hidden="true" />
            <span className="text-accent">Replay: {fmtDate(health.replay_day)}</span>
          </>
        ) : null}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-x-1 gap-y-1.5">
        {view && onView ? (
          <>
            <PageTabs
              view={view}
              onView={onView}
              openTradeCount={openTradeCount}
              tradesPeek={tradesPeek}
            />
            <Rule />
          </>
        ) : null}
        {restore ? (
          <button
            type="button"
            onClick={onRestorePanels}
            className={toolClass(true)}
            title="Expand every minimised panel"
          >
            <RestoreIcon />
            Restore panels
          </button>
        ) : null}
        {news ? (
          <button
            type="button"
            onClick={onToggleNews}
            className={toolClass(!newsHidden)}
            aria-pressed={!newsHidden}
            title={newsHidden ? 'Show the headlines' : 'Hide the headlines'}
          >
            <NewsIcon />
            Headlines
          </button>
        ) : null}
        {restore || news ? <Rule /> : null}
        {dataControl}
        {configControl}
        {/* hovered, the p95s (E27); the click keeps the full overlay on screen */}
        <HoverCard card={debug ? null : <LatencyPeek />} label="Latency">
          <button
            type="button"
            onClick={onToggleDebug}
            className={toolClass(debug)}
            aria-pressed={debug}
          >
            <LatencyIcon />
            Latency
          </button>
        </HoverCard>
        <button
          type="button"
          onClick={onToggleTheme}
          className={toolClass()}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>
        <AuthSlot health={health} onLogout={onLogout} />
      </div>
    </header>
  )
}

/** Login or Logout, set apart from the tools by a rule; nothing when neither applies. */
function AuthSlot({
  health,
  onLogout,
}: {
  health: HealthResponse | null
  onLogout?: (() => Promise<void>) | undefined
}) {
  const auth = health?.auth
  const shown = auth === 'valid' ? onLogout !== undefined : auth === 'missing' || auth === 'expired'
  if (!shown) return null
  return (
    <>
      <Rule />
      <AuthButton health={health} onLogout={onLogout} />
    </>
  )
}
