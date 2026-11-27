import { useEffect, useState } from 'react'

import { fetchJournal } from '../../api/client'
import type { JournalQuery } from '../../api/client'
import type { ExitReason, JournalOut, JournalStatsOut } from '../../api/types'
import { fmtDuration, fmtMoney, pnlColour } from '../../lib/format'
import { REASON_TEXT } from '../../lib/tradeText'

/** "overall" is index options only; bullion has its own total (spec §10). */
const SCOPE_LABEL: Partial<Record<string, string>> = {
  overall: 'Index options',
  bullion: 'Bullion',
  manual: 'Opened by hand',
}

interface Props {
  /** the Trades page's market and date range */
  query: JournalQuery
  /** bumps when a trade changes, so the cards refetch */
  revision: number
  load?: ((q: JournalQuery, signal: AbortSignal) => Promise<JournalOut>) | undefined
}

/** The summary cards under the executed trades: overall, per index, bullion, per metal, by hand. */
export function JournalStats({ query, revision, load = fetchJournal }: Props) {
  const { index = '', from = '', to = '' } = query
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

  return (
    <div className="flex flex-col gap-3" data-testid="journal-stats">
      <h2 className="text-sm font-semibold">Summary</h2>
      {error ? (
        <div className="text-bear" role="alert">
          Could not load the summary: {error}
        </div>
      ) : null}
      {journal || error ? null : <div className="text-fg-muted">Loading…</div>}
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
    </div>
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
