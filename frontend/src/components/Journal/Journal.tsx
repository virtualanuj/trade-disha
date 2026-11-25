import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchJournal } from '../../api/client'
import type { JournalQuery } from '../../api/client'
import type { ExitReason, JournalOut, JournalStatsOut } from '../../api/types'
import { fmtDuration, fmtMoney, pnlColour } from '../../lib/format'
import { REASON_TEXT } from '../../lib/tradeText'

/** "overall" is index options only; bullion has its own total (spec §10). */
const SCOPE_LABEL: Partial<Record<string, string>> = {
  overall: 'Index options',
  bullion: 'Bullion',
}

interface Props {
  indices: string[]
  /** bumps when a trade changes, so the page refetches */
  revision: number
  /** the paper bank strip, shown above the filters */
  bank?: ReactNode
  load?: (q: JournalQuery, signal: AbortSignal) => Promise<JournalOut>
}

/** The paper bank and the summary figures; each trade is on the Trades page (E19). */
export function Journal({ indices, revision, bank, load = fetchJournal }: Props) {
  const [index, setIndex] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [journal, setJournal] = useState<JournalOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctl = new AbortController()
    load({ index, from, to }, ctl.signal)
      .then((j) => {
        setJournal(j)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : 'failed to load')
      })
    return () => {
      ctl.abort()
    }
  }, [index, from, to, revision, load])

  const field = 'rounded border border-border bg-bg px-2 py-1 text-fg'
  return (
    <section
      className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4 text-xs"
      data-testid="journal"
    >
      {bank ? <div className="rounded border border-border bg-bg-elev p-3">{bank}</div> : null}
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
        <span className="pb-1 text-fg-muted">
          Each trade, with its signal and evidence, is on the{' '}
          <a href="#trades" className="text-accent hover:underline">
            Trades page
          </a>
          .
        </span>
      </div>

      {error ? (
        <div className="text-bear" role="alert">
          Could not load the journal: {error}
        </div>
      ) : null}

      {journal ? null : <div className="text-fg-muted">Loading…</div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(journal?.stats ?? []).map((s) => (
          <StatsCard key={s.scope} stats={s} />
        ))}
      </div>
      {journal && journal.open_trades > 0 ? (
        <div className="text-fg-muted">
          {journal.open_trades} trade{journal.open_trades === 1 ? ' is' : 's are'} still open and
          not counted above.
        </div>
      ) : null}
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
          {SCOPE_LABEL[s.scope] ?? s.scope}
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
