import { useEffect, useMemo, useState } from 'react'

import { fetchJournal, fetchPaperTrades } from '../../api/client'
import type { JournalQuery } from '../../api/client'
import type {
  ExitReason,
  FillQuality,
  JournalOut,
  JournalStatsOut,
  PaperTradeOut,
} from '../../api/types'
import {
  fmtDuration,
  fmtIstDate,
  fmtIstTime,
  fmtMoney,
  fmtPrice,
  fmtSigned,
  pnlColour,
} from '../../lib/format'

const REASON_TEXT: Record<ExitReason, string> = {
  TARGET: 'Target',
  STOP: 'Stop',
  SQUARE_OFF: 'Square-off',
  MANUAL: 'Manual',
}

const QUALITY_TEXT: Record<Exclude<FillQuality, 'live'>, { label: string; title: string }> = {
  after_gap: {
    label: 'after gap',
    title: 'The feed was down; this exit used the first price after it came back.',
  },
  stale: {
    label: 'stale price',
    title: 'Squared off while the feed was down, at the last price the app had seen.',
  },
}

interface Loaded {
  trades: PaperTradeOut[]
  journal: JournalOut
}

interface Props {
  indices: string[]
  /** bumps when a trade changes, so the page refetches */
  revision: number
  load?: (q: JournalQuery, signal: AbortSignal) => Promise<Loaded>
}

async function loadFromApi(q: JournalQuery, signal: AbortSignal): Promise<Loaded> {
  const [trades, journal] = await Promise.all([
    fetchPaperTrades(q, signal),
    fetchJournal(q, signal),
  ])
  return { trades, journal }
}

export function Journal({ indices, revision, load = loadFromApi }: Props) {
  const [index, setIndex] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [reason, setReason] = useState<ExitReason | ''>('')
  const [quality, setQuality] = useState<FillQuality | ''>('')
  const [data, setData] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctl = new AbortController()
    load({ index, from, to }, ctl.signal)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : 'failed to load')
      })
    return () => {
      ctl.abort()
    }
  }, [index, from, to, revision, load])

  const rows = useMemo(
    () =>
      (data?.trades ?? []).filter(
        (t) =>
          (reason === '' || t.exit_reason === reason) &&
          (quality === '' || t.exit_fill_quality === quality),
      ),
    [data, reason, quality],
  )

  const field = 'rounded border border-border bg-bg px-2 py-1 text-fg'
  return (
    <section
      className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4 text-xs"
      data-testid="journal"
    >
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-4 text-base font-semibold">Paper-trade journal</h1>
        <label className="flex flex-col gap-1 text-fg-muted">
          Index
          <select
            className={field}
            value={index}
            onChange={(e) => {
              setIndex(e.target.value)
            }}
          >
            <option value="">All</option>
            {indices.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-fg-muted">
          From
          <input
            type="date"
            className={field}
            value={from}
            onChange={(e) => {
              setFrom(e.target.value)
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-fg-muted">
          To
          <input
            type="date"
            className={field}
            value={to}
            onChange={(e) => {
              setTo(e.target.value)
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-fg-muted">
          Exit
          <select
            className={field}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value as ExitReason | '')
            }}
          >
            <option value="">Any</option>
            {Object.entries(REASON_TEXT).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-fg-muted">
          Fill
          <select
            className={field}
            value={quality}
            onChange={(e) => {
              setQuality(e.target.value as FillQuality | '')
            }}
          >
            <option value="">Any</option>
            <option value="live">Live</option>
            <option value="after_gap">After gap</option>
            <option value="stale">Stale price</option>
          </select>
        </label>
      </div>

      {error ? (
        <div className="text-bear" role="alert">
          Could not load the journal: {error}
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(data?.journal.stats ?? []).map((s) => (
          <StatsCard key={s.scope} stats={s} />
        ))}
      </div>
      {data && data.journal.open_trades > 0 ? (
        <div className="text-fg-muted">
          {data.journal.open_trades} trade{data.journal.open_trades === 1 ? ' is' : 's are'} still
          open and not counted above.
        </div>
      ) : null}

      <div className="rounded border border-border bg-bg-elev p-3">
        <div className="mb-2 text-[10px] uppercase tracking-wide text-fg-muted">
          Trades · {rows.length}
        </div>
        {rows.length === 0 ? (
          <div className="text-fg-muted">{data ? 'No paper trades match.' : 'Loading…'}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full font-mono whitespace-nowrap">
              <thead className="text-fg-muted">
                <tr className="h-6 font-sans">
                  <th className="text-left font-normal">Date</th>
                  <th className="text-left font-normal">Option</th>
                  <th className="text-right font-normal">Qty</th>
                  <th className="text-right font-normal">In</th>
                  <th className="text-right font-normal">Entry</th>
                  <th className="text-right font-normal">Slip</th>
                  <th className="text-right font-normal">Out</th>
                  <th className="text-right font-normal">Exit</th>
                  <th className="text-left font-normal pl-3">Reason</th>
                  <th className="text-right font-normal">Held</th>
                  <th className="text-right font-normal">Gross</th>
                  <th className="text-right font-normal">Net</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <TradeRow key={t.id} t={t} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

function StatsCard({ stats: s }: { stats: JournalStatsOut }) {
  const reasons = (Object.keys(REASON_TEXT) as ExitReason[])
    .filter((r) => s.by_reason[r])
    .map((r) => `${REASON_TEXT[r]} ${String(s.by_reason[r])}`)
    .join(' · ')
  return (
    <div className="rounded border border-border bg-bg-elev p-3" data-testid={`stats-${s.scope}`}>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wide text-fg-muted">
          {s.scope === 'overall' ? 'Overall' : s.scope}
        </span>
        <span className="text-fg-muted">
          {s.trades} closed trade{s.trades === 1 ? '' : 's'}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-3">
        <Figure
          label="Net result"
          value={fmtMoney(s.net_total)}
          cls={pnlColour(s.net_total)}
          sub={`gross ${fmtMoney(s.gross_total)}`}
        />
        <Figure
          label="Hit rate"
          value={s.hit_rate == null ? '—' : `${(s.hit_rate * 100).toFixed(0)}%`}
          sub={`${String(s.hits)} of ${String(s.trades)} net-positive`}
        />
        <Figure label="Avg win" value={fmtMoney(s.avg_win)} cls="text-bull" />
        <Figure label="Avg loss" value={fmtMoney(s.avg_loss)} cls="text-bear" />
      </div>
      <div className="mt-2 text-fg-muted">
        {reasons || 'No exits yet'}
        {s.avg_duration_s != null ? ` · avg held ${fmtDuration(s.avg_duration_s * 1000)}` : ''}
        {s.non_live_fills > 0 ? (
          <span className="ml-1 text-warn">
            · {s.non_live_fills} exit{s.non_live_fills === 1 ? '' : 's'} not on a live price
          </span>
        ) : null}
      </div>
    </div>
  )
}

function Figure({
  label,
  value,
  sub,
  cls = '',
}: {
  label: string
  value: string
  sub?: string
  cls?: string
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</div>
      <div className={`font-mono text-sm ${cls}`}>{value}</div>
      {sub ? <div className="text-[10px] text-fg-muted">{sub}</div> : null}
    </div>
  )
}

function TradeRow({ t }: { t: PaperTradeOut }) {
  const open = t.status === 'open'
  const badge =
    t.exit_fill_quality && t.exit_fill_quality !== 'live' ? QUALITY_TEXT[t.exit_fill_quality] : null
  return (
    <tr className="h-7 border-t border-border/60">
      <td className="text-fg-muted">{fmtIstDate(t.entry_ts)}</td>
      <td className={t.direction === 'BUY_CE' ? 'text-bull' : 'text-bear'}>
        {t.index} {t.strike} {t.direction === 'BUY_CE' ? 'CE' : 'PE'}
      </td>
      <td className="text-right">{t.qty}</td>
      <td className="text-right">{fmtIstTime(t.entry_ts)}</td>
      <td className="text-right">{fmtPrice(t.entry_price)}</td>
      <td
        className="text-right text-fg-muted"
        title={`signal entry ${fmtPrice(t.signal_entry)}; fill minus signal price`}
      >
        {fmtSigned(t.slippage, 2)}
      </td>
      <td className="text-right">{t.exit_ts == null ? '—' : fmtIstTime(t.exit_ts)}</td>
      <td className="text-right">{fmtPrice(t.exit_price)}</td>
      <td className="pl-3 font-sans">
        {open ? (
          <span className="text-accent">open</span>
        ) : (
          ((t.exit_reason && REASON_TEXT[t.exit_reason]) ?? '—')
        )}
        {badge ? (
          <span className="ml-2 rounded bg-warn/20 px-1 text-warn" title={badge.title}>
            {badge.label}
            {t.exit_price_age_ms != null ? ` ${fmtDuration(t.exit_price_age_ms)} old` : ''}
          </span>
        ) : null}
      </td>
      <td className="text-right text-fg-muted">
        {t.exit_ts == null ? '—' : fmtDuration(t.exit_ts - t.entry_ts)}
      </td>
      <td className={`text-right ${pnlColour(t.gross)}`}>{fmtMoney(t.gross)}</td>
      <td className={`text-right ${pnlColour(t.net)}`} title={`cost ₹${String(t.cost)}`}>
        {fmtMoney(t.net)}
      </td>
    </tr>
  )
}
