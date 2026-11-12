import type { HealthResponse } from '../../api/types'
import { fmtAge, fmtIstTime, tickAgeColour } from '../../lib/format'
import type { WsState } from '../../state/store'
import type { Theme } from '../../theme/useTheme'

interface Props {
  health: HealthResponse | null
  ws: WsState
  now: number
  lastTickTs: number | null
  theme: Theme
  onToggleTheme: () => void
  debug: boolean
  onToggleDebug: () => void
}

const MARKET_LABEL: Record<HealthResponse['market_status'], string> = {
  pre_open: 'PRE-OPEN',
  live: 'LIVE',
  closed: 'CLOSED',
  holiday: 'HOLIDAY',
}

function MarketPill({ health, now }: { health: HealthResponse | null; now: number }) {
  const status = health?.market_status
  const colour =
    status === 'live' ? 'text-bull' : status === 'pre_open' ? 'text-warn' : 'text-fg-muted'
  return (
    <span className={`flex items-center gap-2 ${colour}`} data-testid="market-pill">
      <span aria-hidden="true">●</span>
      <span className="font-medium">{status ? MARKET_LABEL[status] : '…'}</span>
      <span className="font-mono text-fg-muted">{fmtIstTime(now)} IST</span>
    </span>
  )
}

function FeedPill({
  health,
  ws,
  now,
  lastTickTs,
}: {
  health: HealthResponse | null
  ws: WsState
  now: number
  lastTickTs: number | null
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
  const colour = state === 'connected' ? tickAgeColour(age) : 'text-bear'
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

function AuthPill({ health }: { health: HealthResponse | null }) {
  const auth = health?.auth
  if (auth === 'not_required') {
    return <span className="text-fg-muted">Login: not needed</span>
  }
  if (auth === 'valid') {
    return <span className="text-bull">Login: valid</span>
  }
  return (
    <span className="flex items-center gap-2 text-warn">
      Login: {auth ?? '…'}
      <button
        type="button"
        className="rounded border border-border px-2 py-0.5 text-fg-muted"
        disabled
        title="Upstox login arrives with the live feed"
      >
        Login
      </button>
    </span>
  )
}

export function TopBar(props: Props) {
  const { health, ws, now, lastTickTs, theme, onToggleTheme, debug, onToggleDebug } = props
  return (
    <header className="flex h-11 items-center gap-6 border-b border-border bg-bg-elev px-4">
      <span className="font-semibold tracking-wide">TradeDisha</span>
      <MarketPill health={health} now={now} />
      <FeedPill health={health} ws={ws} now={now} lastTickTs={lastTickTs} />
      <AuthPill health={health} />
      {health?.replay_day ? <span className="text-accent">Replay: {health.replay_day}</span> : null}
      <span className="ml-auto" />
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
    </header>
  )
}
