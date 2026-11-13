import { useEffect, useState } from 'react'

import { fetchUsage, pruneTicks } from '../../api/client'
import type { PruneOut, UsageOut } from '../../api/types'
import { fmtBytes, fmtCount, fmtDate } from '../../lib/format'

interface Props {
  usage?: (untilDate?: string, signal?: AbortSignal) => Promise<UsageOut>
  prune?: (untilDate: string) => Promise<PruneOut>
}

type Result =
  | { kind: 'none' }
  | { kind: 'busy' }
  | { kind: 'done'; out: PruneOut }
  | { kind: 'error'; message: string }

/** Storage held, and deleting raw ticks up to and including a chosen date. */
export function DataPanel({ usage = fetchUsage, prune = pruneTicks }: Props) {
  const [open, setOpen] = useState(false)
  const [until, setUntil] = useState('')
  const [typed, setTyped] = useState('')
  const [data, setData] = useState<UsageOut | null>(null)
  const [result, setResult] = useState<Result>({ kind: 'none' })
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!open) return
    const ctl = new AbortController()
    usage(until || undefined, ctl.signal)
      .then(setData)
      .catch(() => {
        if (!ctl.signal.aborted) setData(null)
      })
    return () => {
      ctl.abort()
    }
  }, [open, until, revision, usage])

  /** the chosen date as it is shown, which is also what must be typed to confirm */
  const shown = fmtDate(until)
  const confirmed = until !== '' && typed === shown
  const nothing = data?.prune_rows === 0

  const run = () => {
    setResult({ kind: 'busy' })
    prune(until)
      .then((out) => {
        setResult({ kind: 'done', out })
        setTyped('')
        setRevision((r) => r + 1)
      })
      .catch((e: unknown) => {
        setResult({ kind: 'error', message: e instanceof Error ? e.message : 'failed' })
      })
  }

  const field = 'rounded border border-border bg-bg px-2 py-1 font-mono text-fg'
  return (
    <div className="relative text-xs">
      <button
        type="button"
        className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg"
        aria-expanded={open}
        onClick={() => {
          setOpen((o) => !o)
        }}
      >
        Data
      </button>
      {open ? (
        <div
          className="absolute top-7 right-0 z-20 w-[380px] rounded border border-border bg-bg-elev p-3 whitespace-normal shadow-lg"
          data-testid="data-panel"
        >
          <div className="font-semibold">Stored data</div>
          <table className="mt-2 w-full font-mono">
            <tbody>
              <Row label="Database size" value={fmtBytes(data?.db_bytes)} />
              <Row label="Raw ticks" value={fmtCount(data?.tick_rows)} />
              <Row label="Days of ticks" value={fmtCount(data?.tick_days)} />
              <Row label="Oldest tick day" value={fmtDate(data?.oldest)} />
              <Row label="Newest tick day" value={fmtDate(data?.newest)} />
            </tbody>
          </table>

          <div className="mt-3 border-t border-border pt-3 font-semibold">Delete raw ticks</div>
          <p className="mt-1 text-fg-muted">
            Removes ticks up to and including the chosen date. Candles, option-chain history, market
            views, signals and paper trades are not affected. Days whose ticks are deleted can no
            longer be replayed.
          </p>
          <label className="mt-2 flex items-center justify-between gap-2 text-fg-muted">
            Up to and including
            <input
              type="date"
              className={field}
              value={until}
              onChange={(e) => {
                setUntil(e.target.value)
                setTyped('')
                setResult({ kind: 'none' })
              }}
            />
          </label>
          {until && data ? (
            <div className="mt-2" data-testid="prune-preview">
              {nothing ? (
                <span className="text-fg-muted">No ticks on or before {shown}.</span>
              ) : (
                <span>
                  This deletes <b>{fmtCount(data.prune_days)}</b> day
                  {data.prune_days === 1 ? '' : 's'}, <b>{fmtCount(data.prune_rows)}</b> ticks,
                  about <b>{fmtBytes(data.prune_bytes_estimate)}</b>. It cannot be undone.
                </span>
              )}
            </div>
          ) : null}
          {until && !nothing ? (
            <>
              <label className="mt-2 flex items-center justify-between gap-2 text-fg-muted">
                Type {shown} to confirm
                <input
                  type="text"
                  className={`${field} w-32`}
                  value={typed}
                  placeholder={shown}
                  onChange={(e) => {
                    setTyped(e.target.value.trim())
                  }}
                />
              </label>
              <button
                type="button"
                className="mt-2 rounded border border-bear px-3 py-1 font-medium text-bear hover:bg-bear/10 disabled:opacity-50"
                disabled={!confirmed || result.kind === 'busy'}
                onClick={run}
              >
                {result.kind === 'busy' ? 'Deleting…' : 'Delete ticks'}
              </button>
            </>
          ) : null}
          {result.kind === 'done' ? (
            <div className="mt-2 text-bull" role="status">
              Deleted {fmtCount(result.out.rows_deleted)} ticks up to{' '}
              {fmtDate(result.out.until_date)}; {fmtBytes(result.out.bytes_freed)} freed.
            </div>
          ) : null}
          {result.kind === 'error' ? (
            <div className="mt-2 text-bear" role="alert">
              Not deleted: {result.message}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr className="h-5">
      <td className="font-sans text-fg-muted">{label}</td>
      <td className="text-right">{value}</td>
    </tr>
  )
}
