import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchBankStatement } from '../../api/client'
import type { StatementQuery } from '../../api/client'
import type { BankStatementOut, StatementKind, StatementRowOut } from '../../api/types'
import { instrumentLabel } from '../../lib/direction'
import { fmtDate, fmtIstTime, fmtMoney, fmtRupees, pnlColour } from '../../lib/format'

const KIND_TEXT: Record<StatementKind, string> = {
  OPEN: 'Opening deposit',
  DEPOSIT: 'Deposit',
  WITHDRAW: 'Withdrawal',
  BLOCK: 'Blocked',
  SETTLE: 'Settled',
}

const KIND_HELP: Record<StatementKind, string> = {
  OPEN: 'The cash first put in: the opening balance when the bank was opened.',
  DEPOSIT: 'The opening balance was raised in Config: the difference is cash in.',
  WITHDRAW: 'The opening balance was lowered in Config: the difference is cash out.',
  BLOCK: 'A trade opened: its premium (options) or margin (futures) plus cost is held.',
  SETTLE: 'A trade closed: its block is released and its net P&L settles into the balance.',
}

interface Props {
  /** the indices and metals to filter by */
  markets: string[]
  /** bumps when a trade changes, so the statement refetches */
  revision: number
  /** the number of cash moves the socket's bank shows: a deposit or withdrawal refetches */
  cashMoves: number
  /** the paper bank strip, shown above the filters */
  bank?: ReactNode
  load?: (q: StatementQuery, signal: AbortSignal) => Promise<BankStatementOut>
}

/**
 * The paper bank's statement (E26): every cash move, oldest first, with the balance, the
 * money blocked and the money available after it. The summary cards are on the Trades page.
 */
export function Journal({ markets, revision, cashMoves, bank, load = fetchBankStatement }: Props) {
  const [index, setIndex] = useState('')
  const [kind, setKind] = useState<StatementKind | ''>('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [statement, setStatement] = useState<BankStatementOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctl = new AbortController()
    load({ index, kind, from, to }, ctl.signal)
      .then((s) => {
        setStatement(s)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : 'failed to load')
      })
    return () => {
      ctl.abort()
    }
  }, [index, kind, from, to, revision, cashMoves, load])

  const field = 'rounded border border-border bg-bg px-2 py-1 text-fg'
  const rows = statement?.rows ?? []
  return (
    <section
      className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4 text-xs"
      data-testid="journal"
    >
      {bank ? <div className="rounded border border-border bg-bg-elev p-3">{bank}</div> : null}
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-4 text-base font-semibold">Paper bank statement</h1>
        <label className="flex flex-col gap-1 text-fg-muted">
          Market
          <select
            className={field}
            value={index}
            onChange={(e) => {
              setIndex(e.target.value)
            }}
          >
            <option value="">All</option>
            {markets.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-fg-muted">
          Kind
          <select
            className={field}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as StatementKind | '')
            }}
          >
            <option value="">Any</option>
            {(Object.keys(KIND_TEXT) as StatementKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_TEXT[k]}
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
          Each trade, and the summary figures, are on the{' '}
          <a href="#trades" className="text-accent hover:underline">
            Trades page
          </a>
          .
        </span>
      </div>

      {error ? (
        <div className="text-bear" role="alert">
          Could not load the statement: {error}
        </div>
      ) : null}

      <div className="rounded border border-border bg-bg-elev p-3">
        {rows.length === 0 ? (
          <div className="text-fg-muted">
            {statement ? 'No cash moves match.' : error ? '' : 'Loading…'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full font-mono whitespace-nowrap" data-testid="bank-statement">
              <thead className="text-fg-muted">
                <tr className="h-6 font-sans">
                  <th className="text-left font-normal">Date</th>
                  <th className="pl-3 text-left font-normal">Kind</th>
                  <th className="pl-3 text-left font-normal">Trade</th>
                  <th
                    className="text-right font-normal"
                    title="Change in the money blocked by open trades"
                  >
                    Held
                  </th>
                  <th className="text-right font-normal" title="Change in the balance">
                    Cash
                  </th>
                  <th className="text-right font-normal">Balance</th>
                  <th className="text-right font-normal">Blocked</th>
                  <th className="text-right font-normal">Available</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <Row key={`${r.kind}-${r.trade_id ?? ''}-${String(r.ts)}-${String(i)}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

function tradeText(r: StatementRowOut): string {
  if (r.direction === null || r.index === null) return ''
  const label = instrumentLabel({
    direction: r.direction,
    strike: r.strike ?? 0,
    index: r.index,
    ...(r.trading_symbol === null ? {} : { trading_symbol: r.trading_symbol }),
  })
  return `${r.index} ${label}`
}

function Row({ r }: { r: StatementRowOut }) {
  const trade = tradeText(r)
  return (
    <tr className="h-6 border-t border-border" data-testid="statement-row">
      <td className="text-fg-muted">
        {fmtDate(r.ts)} {fmtIstTime(r.ts)}
      </td>
      <td className="pl-3 font-sans" title={KIND_HELP[r.kind]}>
        {KIND_TEXT[r.kind]}
      </td>
      <td className="pl-3 font-sans">
        {trade ? (
          <a href="#trades" className="hover:underline" title="Open the Trades page">
            {trade}
          </a>
        ) : null}
      </td>
      <td className="text-right text-fg-muted">{r.held === 0 ? '' : fmtMoney(r.held)}</td>
      <td className={`text-right ${pnlColour(r.cash)}`}>
        {r.kind === 'BLOCK' ? '' : r.kind === 'OPEN' ? fmtRupees(r.cash) : fmtMoney(r.cash)}
      </td>
      <td className="text-right">{fmtRupees(r.balance)}</td>
      <td className="text-right text-fg-muted">{fmtRupees(r.blocked)}</td>
      <td className={`text-right ${r.available <= 0 ? 'text-bear' : ''}`}>
        {fmtRupees(r.available)}
      </td>
    </tr>
  )
}
