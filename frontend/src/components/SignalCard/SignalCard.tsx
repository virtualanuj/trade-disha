import type { GateOut, SignalOut } from '../../api/types'
import { countdown, fmtIstTime, fmtPrice } from '../../lib/format'

const REASON_TEXT: Record<NonNullable<GateOut['reason']>, string> = {
  below_threshold: 'bias below the entry threshold',
  active_exists: 'a signal is already active',
  outside_hours: 'outside signal hours',
  feed_down: 'feed not live',
  no_price: 'no ATM option price yet',
  rearm: 'waiting for bias to re-arm',
}

function topReasons(s: SignalOut, n = 3): string[] {
  const inds = s.breakdown.indicators ?? []
  const sign = s.direction === 'BUY_CE' ? 1 : -1
  return inds
    .filter((i) => i.quality === 'ok' && i.contribution * sign > 0)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, n)
    .map((i) => i.note)
}

interface Props {
  signal: SignalOut | undefined
  gate: GateOut | undefined
  now: number
  /** Milestone 5 wires this to the paper-trade action. */
  onPaperTrade?: (signal: SignalOut) => void
}

export function SignalCard({ signal, gate, now, onPaperTrade }: Props) {
  if (!signal) {
    return (
      <div
        className="rounded border border-dashed border-border p-4 text-xs text-fg-muted"
        data-testid="signal-card"
      >
        <div className="text-[10px] uppercase tracking-wide">Signal</div>
        <div className="mt-1">
          No active signal
          {gate?.reason ? (
            <span>
              {' '}
              · last minute ({fmtIstTime(gate.minute_ts + 60_000)}): {REASON_TEXT[gate.reason]}
            </span>
          ) : null}
        </div>
      </div>
    )
  }
  const isCall = signal.direction === 'BUY_CE'
  const remaining = countdown(signal.expires_at, now)
  const urgent = signal.expires_at - now < 60_000
  return (
    <div
      className={`rounded border p-4 text-xs ${isCall ? 'border-bull/60' : 'border-bear/60'} bg-bg-elev`}
      data-testid="signal-card"
    >
      <div className="flex items-baseline justify-between">
        <span className={`text-base font-semibold ${isCall ? 'text-bull' : 'text-bear'}`}>
          BUY {signal.index} {signal.strike} {isCall ? 'CE' : 'PE'}
        </span>
        <span className="font-mono text-fg-muted">
          fired {fmtIstTime(signal.ts_fired)} · bias {signal.strength}
          {signal.target_basis === 'points' ? (
            <span className="ml-2 text-warn">expiry day</span>
          ) : null}
        </span>
      </div>
      <div className="mt-1 text-fg-muted">
        {signal.trading_symbol} · exp {signal.expiry} · lot {signal.lot_size}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Stat label="Entry" value={fmtPrice(signal.entry_price)} />
        <Stat
          label="Target"
          value={fmtPrice(signal.target_price)}
          sub={signal.target_points != null ? `+${String(signal.target_points)} pts` : undefined}
          cls="text-bull"
        />
        <Stat
          label="Stop"
          value={fmtPrice(signal.stop_price)}
          sub={signal.stop_points != null ? `-${String(signal.stop_points)} pts` : undefined}
          cls="text-bear"
        />
        <Stat label="Expires in" value={remaining} cls={urgent ? 'text-warn' : ''} />
      </div>
      {signal.delta_used != null ? (
        <div className="mt-1 text-[10px] text-fg-muted">
          delta {signal.delta_used.toFixed(2)} used for point conversion
        </div>
      ) : null}
      <ul className="mt-3 list-disc pl-4 text-fg-muted">
        {topReasons(signal).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <div className="mt-3">
        <button
          type="button"
          className="rounded border border-accent px-3 py-1 font-medium text-accent hover:bg-accent/10 disabled:opacity-50"
          disabled={!onPaperTrade}
          title={onPaperTrade ? undefined : 'Paper trading arrives in Milestone 5'}
          onClick={() => onPaperTrade?.(signal)}
        >
          Paper trade
        </button>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  sub,
  cls = '',
}: {
  label: string
  value: string
  sub?: string | undefined
  cls?: string
}) {
  return (
    <div>
      <div className="text-[10px] whitespace-nowrap uppercase tracking-wide text-fg-muted">
        {label}
      </div>
      <div className={`font-mono text-sm ${cls}`}>{value}</div>
      {sub ? <div className="text-[10px] text-fg-muted">{sub}</div> : null}
    </div>
  )
}
