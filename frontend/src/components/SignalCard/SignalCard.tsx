import { useState } from 'react'

import type { GateOut, PaperTradeOut, SignalOut } from '../../api/types'
import {
  countdown,
  fmtDate,
  fmtDuration,
  fmtIstTime,
  fmtMoney,
  fmtPrice,
  fmtSigned,
  pnlColour,
} from '../../lib/format'
import { directionLabel, instrumentLabel, isFuture, isLong } from '../../lib/direction'
import { ConfigVersionChip } from '../ConfigVersionChip/ConfigVersionChip'

const REASON_TEXT: Record<NonNullable<GateOut['reason']>, string> = {
  below_threshold: 'bias below the entry threshold',
  active_exists: 'a signal is already active',
  outside_hours: 'outside signal hours',
  feed_down: 'feed not live',
  no_price: 'no price to trade at yet',
  rearm: 'waiting for bias to re-arm',
  no_setup: 'bias too weak for a setup',
  flow_not_confirmed: 'setup in place, waiting for order flow to agree',
  spread_wide: 'setup and order flow agree, but bid-ask spread too wide',
  disabled: 'bullion signals are switched off in the config',
}

function topReasons(s: SignalOut, n = 3): string[] {
  const inds = s.breakdown.indicators ?? []
  const sign = isLong(s.direction) ? 1 : -1
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
  /** open paper trades on this index, shown whether or not they agree with the signal */
  openTrades?: PaperTradeOut[]
  /** why a paper trade cannot be opened right now, if it cannot */
  blocked?: string | undefined
  /** opens a paper trade; rejects with the server's reason */
  onPaperTrade?: (signal: SignalOut) => Promise<unknown>
}

export function SignalCard({ signal, gate, now, openTrades = [], blocked, onPaperTrade }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ id: string; text: string } | null>(null)
  if (!signal) {
    return (
      <div className="text-xs text-fg-muted" data-testid="signal-card">
        <div>
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
  const long = isLong(signal.direction)
  const remaining = countdown(signal.expires_at, now)
  const urgent = signal.expires_at - now < 60_000
  return (
    <div className="text-xs" data-testid="signal-card">
      <div className="flex items-baseline justify-between">
        <span className={`text-base font-semibold ${long ? 'text-bull' : 'text-bear'}`}>
          {directionLabel(signal.direction)} {signal.index}{' '}
          {isFuture(signal.direction) ? 'FUT' : instrumentLabel(signal)}
        </span>
        <span className="font-mono text-fg-muted">
          fired {fmtIstTime(signal.ts_fired)} · bias {signal.strength}
          {signal.config_version != null ? (
            <span className="ml-2">
              <ConfigVersionChip version={signal.config_version} />
            </span>
          ) : null}
          {signal.target_basis === 'points' ? (
            <span className="ml-2 text-warn">expiry day</span>
          ) : null}
        </span>
      </div>
      <div className="mt-1 text-fg-muted">
        {signal.trading_symbol} · exp {fmtDate(signal.expiry)} ·{' '}
        {isFuture(signal.direction)
          ? `₹${String(signal.lot_size)} per point per lot`
          : `lot ${String(signal.lot_size)}`}
      </div>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <Levels signal={signal} />
        <Stat label="Expires in" value={remaining} cls={urgent ? 'text-warn' : ''} />
      </div>
      <div className="mt-1 text-[10px] text-fg-muted">
        {signal.entry_mode === 'trigger'
          ? `Fired at the ask · spread ${signal.spread_pct != null ? signal.spread_pct.toFixed(2) : '—'}%. `
          : ''}
        {signal.target_points != null && signal.stop_points != null
          ? `Target +${String(signal.target_points)} pts, stop -${String(signal.stop_points)} pts on the index. `
          : ''}
        {signal.live
          ? 'A paper trade opens at the live price with the live target and stop.'
          : 'Live levels appear with the next price.'}
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
      {openTrades.length > 0 ? (
        <div
          className="mt-3 rounded border border-warn/60 bg-warn/10 p-2"
          data-testid="signal-open-trades"
        >
          <div className="font-medium text-warn">
            {openTrades.length} paper trade{openTrades.length === 1 ? '' : 's'} already open on{' '}
            {signal.index}
          </div>
          <ul className="mt-1 font-mono">
            {openTrades.map((t) => (
              <li key={t.id}>
                {instrumentLabel(t)} @ {fmtPrice(t.entry_price)} →{' '}
                <span className={pnlColour(t.live_net)}>{fmtMoney(t.live_net)}</span>{' '}
                <span className="text-fg-muted">({fmtDuration(now - t.entry_ts)})</span>
                {t.direction !== signal.direction ? (
                  <span className="ml-2 font-sans text-warn">opposite side</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          className="rounded border border-accent px-3 py-1 font-medium text-accent hover:bg-accent/10 disabled:opacity-50"
          disabled={!onPaperTrade || busy || blocked !== undefined}
          title={blocked ?? 'Open a paper trade at the current price. No real order is placed.'}
          onClick={() => {
            if (!onPaperTrade) return
            setBusy(true)
            setError(null)
            onPaperTrade(signal)
              .catch((e: unknown) => {
                setError({
                  id: signal.id,
                  text: e instanceof Error ? e.message : 'could not open',
                })
              })
              .finally(() => {
                setBusy(false)
              })
          }}
        >
          {busy ? 'Opening…' : 'Paper trade'}
        </button>
        {blocked ? <span className="text-fg-muted">{blocked}</span> : null}
        {error?.id === signal.id ? (
          <span className="text-bear" role="alert">
            Not opened: {error.text}
          </span>
        ) : null}
      </div>
    </div>
  )
}

/**
 * The levels the signal fired with, and the same rule applied to the price now (spec §9.2).
 * A paper trade takes the live row at its fill.
 */
function Levels({ signal }: { signal: SignalOut }) {
  const live = signal.live
  const moved = live ? live.ltp - signal.entry_price : 0
  return (
    <table className="text-xs">
      <thead>
        <tr className="text-[10px] uppercase tracking-wide text-fg-muted">
          <th className="pr-4 text-left font-normal" />
          <th className="pr-4 text-right font-normal">Entry</th>
          <th className="pr-4 text-right font-normal">Target</th>
          <th className="text-right font-normal">Stop</th>
        </tr>
      </thead>
      <tbody className="font-mono">
        {live ? (
          <tr data-testid="levels-live" className="text-sm">
            <td className="pr-4 font-sans text-[10px] uppercase tracking-wide text-fg-muted">
              Live
            </td>
            <td className="pr-4 text-right">
              {fmtPrice(live.ltp)}
              {moved !== 0 ? (
                <span className={`ml-1 text-[10px] ${pnlColour(moved)}`}>
                  {fmtSigned(moved, 2)}
                </span>
              ) : null}
            </td>
            <td className="pr-4 text-right text-bull">{fmtPrice(live.target)}</td>
            <td className="text-right text-bear">{fmtPrice(live.stop)}</td>
          </tr>
        ) : null}
        <tr data-testid="levels-fired" className={live ? 'text-fg-muted' : 'text-sm'}>
          <td className="pr-4 font-sans text-[10px] uppercase tracking-wide text-fg-muted">
            Fired
          </td>
          <td className="pr-4 text-right">{fmtPrice(signal.entry_price)}</td>
          <td className={`pr-4 text-right ${live ? '' : 'text-bull'}`}>
            {fmtPrice(signal.target_price)}
          </td>
          <td className={`text-right ${live ? '' : 'text-bear'}`}>{fmtPrice(signal.stop_price)}</td>
        </tr>
      </tbody>
    </table>
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
