import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { closePaperTrade, fetchPaperTradeDetail, fetchPaperTrades } from '../../api/client'
import type { JournalQuery } from '../../api/client'
import type {
  ExitReason,
  FillQuality,
  OutcomeOut,
  PaperTradeDetailOut,
  PaperTradeOut,
  SignalOut,
} from '../../api/types'
import { directionLabel, instrumentLabel, isLong } from '../../lib/direction'
import {
  fmtDate,
  fmtDuration,
  fmtIstTime,
  fmtMoney,
  fmtPrice,
  fmtRupees,
  fmtSigned,
  pnlColour,
} from '../../lib/format'
import { biasFromSignal } from '../../lib/signalBias'
import { QUALITY_TEXT, REASON_TEXT } from '../../lib/tradeText'
import { ConfigVersionChip } from '../ConfigVersionChip/ConfigVersionChip'
import { EvidenceTable } from '../EvidenceTable/EvidenceTable'

/** trade, qty, in, out, entry, exit, reason, held, net, and the Close button */
const COLUMNS = 10

const RULE_TEXT: Record<SignalOut['entry_mode'], string> = {
  minute_close: 'minute close',
  trigger: 'order-flow trigger',
}

const RESULT_TEXT: Record<OutcomeOut['result'], { text: string; cls: string }> = {
  open: { text: 'still following', cls: 'text-fg-muted' },
  target: { text: 'target first', cls: 'text-bull' },
  stop: { text: 'stop first', cls: 'text-bear' },
  neither: { text: 'neither', cls: 'text-fg-muted' },
}

type Detail =
  | { kind: 'loading' }
  | { kind: 'ok'; detail: PaperTradeDetailOut }
  | { kind: 'error'; text: string }

interface Props {
  /** the indices and metals to filter by */
  markets: string[]
  /** bumps when a trade changes, so the page refetches */
  revision: number
  /**
   * the socket's copies of open and today's trades: newer than the page's fetch, so an open
   * trade's price and P&L tick, and a close shows before the refetch lands
   */
  latest?: PaperTradeOut[]
  /** for how long an open trade has been held */
  now: number
  load?: (q: JournalQuery, signal: AbortSignal) => Promise<PaperTradeOut[]>
  loadDetail?: (tradeId: string, signal?: AbortSignal) => Promise<PaperTradeDetailOut>
  /** closes an open trade at the current price; rejects with the server's reason */
  onClose?: (tradeId: string) => Promise<unknown>
  /** why a trade cannot be closed right now (its market has no live price), or null */
  closeBlock?: ((t: PaperTradeOut) => string | null) | undefined
}

/**
 * Executed paper trades (E19): the open ones at the current price, then closed trades by
 * day; each opens to its levels and fills, the signal it was taken on, what the instrument
 * did after it, and the evidence then.
 */
export function TradeLog({
  markets,
  revision,
  latest = [],
  now,
  load = fetchPaperTrades,
  loadDetail = fetchPaperTradeDetail,
  onClose = closePaperTrade,
  closeBlock,
}: Props) {
  const [market, setMarket] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [reason, setReason] = useState<ExitReason | ''>('')
  const [quality, setQuality] = useState<FillQuality | ''>('')
  const [trades, setTrades] = useState<PaperTradeOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [details, setDetails] = useState<Partial<Record<string, Detail>>>({})
  /** the trade being closed, and why the last close was refused */
  const [closing, setClosing] = useState<string | null>(null)
  const [closeError, setCloseError] = useState<string | null>(null)
  /** aborts detail fetches still running when the page goes away */
  const detailCtl = useRef<AbortController | null>(null)

  useEffect(() => {
    const ctl = new AbortController()
    detailCtl.current = ctl
    return () => {
      ctl.abort()
    }
  }, [])

  useEffect(() => {
    const ctl = new AbortController()
    load({ index: market, from, to }, ctl.signal)
      .then((t) => {
        setTrades(t)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : 'failed to load')
      })
    return () => {
      ctl.abort()
    }
  }, [market, from, to, revision, load])

  const fetchDetail = useCallback(
    (id: string) => {
      const signal = detailCtl.current?.signal
      setDetails((d) => ({ ...d, [id]: { kind: 'loading' } }))
      loadDetail(id, signal)
        .then((detail) => {
          setDetails((d) => ({ ...d, [id]: { kind: 'ok', detail } }))
        })
        .catch((e: unknown) => {
          if (signal?.aborted) return
          const text = e instanceof Error ? e.message : 'failed to load'
          setDetails((d) => ({ ...d, [id]: { kind: 'error', text } }))
        })
    },
    [loadDetail],
  )

  /** stable between toggles, so the memoised rows skip the clock's re-renders */
  const toggle = useCallback(
    (id: string) => {
      const opening = !expanded.has(id)
      setExpanded((s) => {
        const next = new Set(s)
        if (opening) next.add(id)
        else next.delete(id)
        return next
      })
      const known = details[id]
      if (opening && (known === undefined || known.kind === 'error')) fetchDetail(id)
    },
    [expanded, details, fetchDetail],
  )

  /** the server says which trades match; the socket's copy of each is the newer one */
  const current = useMemo(() => {
    const byId = new Map(latest.map((t) => [t.id, t]))
    return (trades ?? []).map((t) => byId.get(t.id) ?? t)
  }, [trades, latest])
  /** exit reason and fill are narrowed here, and only a closed trade has either */
  const exitFilter = reason !== '' || quality !== ''
  const openRows = useMemo(
    () =>
      exitFilter
        ? []
        : current.filter((t) => t.status === 'open').sort((a, b) => b.entry_ts - a.entry_ts),
    [current, exitFilter],
  )
  const days = useMemo(
    () =>
      byDay(
        current.filter(
          (t) =>
            t.status === 'closed' &&
            (reason === '' || t.exit_reason === reason) &&
            (quality === '' || t.exit_fill_quality === quality),
        ),
      ),
    [current, reason, quality],
  )

  /** the socket's paper_trade frame then moves the row; the revision refetches the list */
  const close = useCallback(
    (id: string) => {
      setClosing(id)
      setCloseError(null)
      onClose(id)
        .catch((e: unknown) => {
          setCloseError(e instanceof Error ? e.message : 'could not close')
        })
        .finally(() => {
          setClosing(null)
        })
    },
    [onClose],
  )

  const rowsOf = (list: PaperTradeOut[]) =>
    list.map((t) => (
      <TradeRows
        key={t.id}
        t={t}
        // only an open trade shows time passing; a closed row keeps equal props and is skipped
        now={t.status === 'open' ? now : 0}
        open={expanded.has(t.id)}
        detail={details[t.id]}
        onToggle={toggle}
        onRetry={fetchDetail}
        closing={closing === t.id}
        closeBlock={t.status === 'open' ? (closeBlock?.(t) ?? null) : null}
        onClose={close}
      />
    ))

  const field = 'rounded border border-border bg-bg px-2 py-1 text-fg'
  return (
    <section
      className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4 text-xs"
      data-testid="trade-log"
    >
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-4 text-base font-semibold">Executed paper trades</h1>
        <label className="flex flex-col gap-1 text-fg-muted">
          Market
          <select
            className={field}
            value={market}
            onChange={(e) => {
              setMarket(e.target.value)
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
          Could not load the trades: {error}
        </div>
      ) : null}
      {closeError ? (
        <div className="text-bear" role="alert">
          Not closed: {closeError}
        </div>
      ) : null}

      <div className="rounded border border-border bg-bg-elev p-3">
        {days.length === 0 && openRows.length === 0 ? (
          <div className="text-fg-muted">{trades ? 'No paper trades match.' : 'Loading…'}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full font-mono whitespace-nowrap">
              <thead className="text-fg-muted">
                <tr className="h-6 font-sans">
                  <th className="text-left font-normal">Trade</th>
                  <th className="text-right font-normal">Qty</th>
                  <th className="text-right font-normal">In</th>
                  <th className="text-right font-normal">Out</th>
                  <th className="text-right font-normal">Entry</th>
                  <th className="text-right font-normal">Exit</th>
                  <th className="pl-3 text-left font-normal">Reason</th>
                  <th className="text-right font-normal">Held</th>
                  <th className="text-right font-normal">Net</th>
                  <th />
                </tr>
              </thead>
              {openRows.length > 0 ? (
                <tbody>
                  <OpenRow trades={openRows} />
                  {rowsOf(openRows)}
                </tbody>
              ) : null}
              {days.map((d) => (
                <tbody key={d.day}>
                  <DayRow day={d.day} trades={d.trades} />
                  {rowsOf(d.trades)}
                </tbody>
              ))}
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

/** Trades by their IST entry day, newest day and newest trade first. */
function byDay(trades: PaperTradeOut[]): { day: string; trades: PaperTradeOut[] }[] {
  const sorted = [...trades].sort((a, b) => b.entry_ts - a.entry_ts)
  const out: { day: string; trades: PaperTradeOut[] }[] = []
  for (const t of sorted) {
    const day = fmtDate(t.entry_ts)
    const last = out[out.length - 1]
    if (last?.day === day) last.trades.push(t)
    else out.push({ day, trades: [t] })
  }
  return out
}

function DayRow({ day, trades }: { day: string; trades: PaperTradeOut[] }) {
  const net = trades.reduce((sum, t) => sum + (t.net ?? 0), 0)
  const won = trades.filter((t) => (t.net ?? 0) > 0).length
  const n = trades.length
  return (
    <tr className="h-8 border-t border-border bg-bg-row/40 font-sans" data-testid={`day-${day}`}>
      <td colSpan={COLUMNS - 2} className="font-semibold">
        {day}
        <span className="ml-3 font-normal text-fg-muted">
          {n} trade{n === 1 ? '' : 's'} · {won} won · {n - won} lost
        </span>
      </td>
      <td className={`text-right font-mono font-semibold ${pnlColour(net)}`}>{fmtMoney(net)}</td>
      <td />
    </tr>
  )
}

/** The open trades' heading: how many, and their net so far at the current price. */
function OpenRow({ trades }: { trades: PaperTradeOut[] }) {
  const net = trades.reduce((sum, t) => sum + (t.live_net ?? 0), 0)
  const n = trades.length
  return (
    <tr className="h-8 border-t border-border bg-accent/10 font-sans" data-testid="open-group">
      <td colSpan={COLUMNS - 2} className="font-semibold text-accent">
        Open now
        <span className="ml-3 font-normal text-fg-muted">
          {n} trade{n === 1 ? '' : 's'} · unrealised, at the current price
        </span>
      </td>
      <td className={`text-right font-mono font-semibold ${pnlColour(net)}`}>{fmtMoney(net)}</td>
      <td />
    </tr>
  )
}

/** Net P&L: realised once closed, at the current price while open. */
function netOf(t: PaperTradeOut): number | null {
  return t.status === 'open' ? t.live_net : t.net
}

function heldMs(t: PaperTradeOut, now: number): number | null {
  if (t.status === 'open') return now - t.entry_ts
  return t.exit_ts == null ? null : t.exit_ts - t.entry_ts
}

const TradeRows = memo(function TradeRows({
  t,
  now,
  open,
  detail,
  onToggle,
  onRetry,
  closing,
  closeBlock,
  onClose,
}: {
  t: PaperTradeOut
  now: number
  open: boolean
  detail: Detail | undefined
  onToggle: (id: string) => void
  onRetry: (id: string) => void
  closing: boolean
  closeBlock: string | null
  onClose: (id: string) => void
}) {
  const live = t.status === 'open'
  const net = netOf(t)
  const badge =
    t.exit_fill_quality && t.exit_fill_quality !== 'live' ? QUALITY_TEXT[t.exit_fill_quality] : null
  const panelId = `trade-detail-${t.id}`
  return (
    <>
      <tr className="h-7 border-t border-border/60" data-testid={`trade-${t.id}`}>
        <td>
          <button
            type="button"
            className={`flex items-center gap-1 hover:underline ${isLong(t.direction) ? 'text-bull' : 'text-bear'}`}
            aria-expanded={open}
            aria-controls={open ? panelId : undefined}
            onClick={() => {
              onToggle(t.id)
            }}
            data-testid={`trade-toggle-${t.id}`}
            title={open ? 'Hide the details' : 'Show the details'}
          >
            <span aria-hidden="true" className="w-3 text-fg-muted">
              {open ? '▾' : '▸'}
            </span>
            {t.index} {instrumentLabel(t)}
          </button>
        </td>
        <td className="text-right">{t.qty}</td>
        <td className="text-right">{fmtIstTime(t.entry_ts)}</td>
        <td className="text-right">{t.exit_ts == null ? '—' : fmtIstTime(t.exit_ts)}</td>
        <td className="text-right">{fmtPrice(t.entry_price)}</td>
        <td className={`text-right ${live ? 'text-fg-muted' : ''}`}>
          {live ? <span title="The price now">{fmtPrice(t.ltp)}</span> : fmtPrice(t.exit_price)}
        </td>
        <td className="pl-3 font-sans">
          {live ? (
            <span className="text-accent">open</span>
          ) : (
            ((t.exit_reason && REASON_TEXT[t.exit_reason]) ?? '—')
          )}
          {live && t.warning === 'bias_reversed' ? (
            <span
              className="ml-2 rounded bg-warn/20 px-1 text-warn"
              title="The current market view opposes this trade. Nothing is closed for you."
            >
              bias reversed
            </span>
          ) : null}
          {badge ? (
            <span className="ml-2 rounded bg-warn/20 px-1 text-warn" title={badge.title}>
              {badge.label}
              {t.exit_price_age_ms != null ? ` ${fmtDuration(t.exit_price_age_ms)} old` : ''}
            </span>
          ) : null}
        </td>
        <td className="text-right text-fg-muted">{fmtDuration(heldMs(t, now))}</td>
        <td
          className={`text-right ${pnlColour(net)}`}
          title={live ? 'So far, at the current price' : undefined}
        >
          {fmtMoney(net)}
        </td>
        <td className="pl-3 text-right font-sans">
          {live ? (
            <button
              type="button"
              className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50"
              disabled={closeBlock !== null || closing}
              title={closeBlock ?? 'Close at the current price'}
              onClick={() => {
                onClose(t.id)
              }}
            >
              {closing ? 'Closing…' : 'Close'}
            </button>
          ) : null}
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={COLUMNS} className="pb-3 font-sans whitespace-normal">
            <DetailBody
              t={t}
              now={now}
              detail={detail}
              onRetry={() => {
                onRetry(t.id)
              }}
              panelId={panelId}
            />
          </td>
        </tr>
      ) : null}
    </>
  )
})

function DetailBody({
  t,
  now,
  detail,
  onRetry,
  panelId,
}: {
  t: PaperTradeOut
  now: number
  detail: Detail | undefined
  onRetry: () => void
  panelId: string
}) {
  if (detail === undefined || detail.kind === 'loading') {
    return <div className="px-4 py-2 text-fg-muted">Loading…</div>
  }
  if (detail.kind === 'error') {
    return (
      <div className="flex items-center gap-3 px-4 py-2 text-bear" role="alert">
        Could not load the trade: {detail.text}
        <button
          type="button"
          className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg"
          onClick={onRetry}
        >
          Try again
        </button>
      </div>
    )
  }
  // the row's trade, not the fetched copy: it carries the live price while the trade is open
  const signal = detail.detail.signal
  return (
    <div
      id={panelId}
      className="mt-1 flex flex-col gap-4 rounded border border-border bg-bg p-3"
      data-testid={panelId}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <TradeFacts t={t} now={now} />
        {signal ? (
          <>
            <SignalFacts s={signal} />
            <OutcomeFacts s={signal} />
          </>
        ) : (
          <p className="text-fg-muted md:col-span-2">The signal for this trade was not found.</p>
        )}
      </div>
      {signal ? (
        <div>
          <Heading>Evidence when it fired</Heading>
          <EvidenceTable bias={biasFromSignal(signal)} />
        </div>
      ) : null}
    </div>
  )
}

function Heading({ children }: { children: ReactNode }) {
  return <div className="mb-1 text-[10px] uppercase tracking-wide text-fg-muted">{children}</div>
}

function Fact({
  id,
  label,
  title,
  children,
}: {
  id: string
  label: string
  title?: string
  children: ReactNode
}) {
  return (
    <div className="flex h-6 items-baseline justify-between gap-3" data-testid={`fact-${id}`}>
      <dt className="text-fg-muted" title={title}>
        {label}
      </dt>
      <dd className="text-right font-mono">{children}</dd>
    </div>
  )
}

/** Price risked and gained per unit: a bought option or future gains upwards, a short downwards. */
function riskReward(t: PaperTradeOut): { risk: number; reward: number } {
  const up = directionLabel(t.direction) === 'BUY'
  const risk = up ? t.entry_price - t.stop_price : t.stop_price - t.entry_price
  const reward = up ? t.target_price - t.entry_price : t.entry_price - t.target_price
  return { risk, reward }
}

function TradeFacts({ t, now }: { t: PaperTradeOut; now: number }) {
  const { risk, reward } = riskReward(t)
  const riskMoney = risk * t.qty
  const live = t.status === 'open'
  const net = netOf(t)
  const gross = live ? t.live_gross : t.gross
  const badge =
    t.exit_fill_quality && t.exit_fill_quality !== 'live' ? QUALITY_TEXT[t.exit_fill_quality] : null
  return (
    <div>
      <Heading>Trade</Heading>
      <div className="mb-1 font-mono text-fg-muted">{t.trading_symbol}</div>
      <dl>
        <Fact id="fill" label="Signal → fill" title="Fill minus signal price is the slippage">
          {fmtPrice(t.signal_entry)} → {fmtPrice(t.entry_price)}
          <span className="ml-2 text-fg-muted">{fmtSigned(t.slippage, 2)}</span>
        </Fact>
        <Fact id="levels" label="Target / stop">
          <span className="text-bull">{fmtPrice(t.target_price)}</span>
          {' / '}
          <span className="text-bear">{fmtPrice(t.stop_price)}</span>
        </Fact>
        <Fact id="rr" label="Risk : reward" title="From the fill to the stop, and to the target">
          {risk > 0 ? `1 : ${(reward / risk).toFixed(1)}` : '—'}
        </Fact>
        {live ? (
          <Fact id="exit" label="Now" title="The last price; the trade is still open">
            {fmtPrice(t.ltp)}
            {t.ltp_ts != null ? <span className="ml-2">{fmtIstTime(t.ltp_ts)}</span> : null}
            <span className="ml-2 font-sans text-accent">open</span>
          </Fact>
        ) : (
          <Fact id="exit" label="Exit">
            {fmtPrice(t.exit_price)}
            {t.exit_ts != null ? <span className="ml-2">{fmtIstTime(t.exit_ts)}</span> : null}
            <span className="ml-2 font-sans">
              {(t.exit_reason && REASON_TEXT[t.exit_reason]) ?? '—'}
            </span>
          </Fact>
        )}
        {badge ? (
          <Fact id="quality" label="Exit price" title={badge.title}>
            <span className="text-warn">
              {badge.label}
              {t.exit_price_age_ms != null ? `, ${fmtDuration(t.exit_price_age_ms)} old` : ''}
            </span>
          </Fact>
        ) : null}
        <Fact id="held" label={live ? 'Held so far' : 'Held'}>
          {fmtDuration(heldMs(t, now))}
        </Fact>
        <Fact id="gross" label="Gross / cost">
          <span className={pnlColour(gross)}>{fmtMoney(gross)}</span>
          {' / '}
          {fmtRupees(t.cost)}
        </Fact>
        <Fact id="net" label={live ? 'Net so far' : 'Net'}>
          <span className={`font-semibold ${pnlColour(net)}`}>{fmtMoney(net)}</span>
        </Fact>
        <Fact
          id="r"
          label={live ? 'Result so far in R' : 'Result in R'}
          title={`Net over the money at risk from fill to stop (${fmtRupees(riskMoney)})`}
        >
          {riskMoney > 0 && net != null ? `${fmtSigned(net / riskMoney, 1)} R` : '—'}
        </Fact>
        <Fact id="blocked" label="Held in the bank" title="Premium or margin, plus cost">
          {fmtRupees(t.blocked)}
        </Fact>
      </dl>
    </div>
  )
}

function SignalFacts({ s }: { s: SignalOut }) {
  return (
    <div>
      <Heading>Signal</Heading>
      <dl>
        <Fact id="fired" label="Fired">
          {fmtIstTime(s.ts_fired)}
          <span className="ml-2 font-sans text-fg-muted">
            on the {fmtIstTime(s.minute_ts).slice(0, 5)} minute
          </span>
        </Fact>
        <Fact id="call" label="Call">
          <span className={isLong(s.direction) ? 'text-bull' : 'text-bear'}>
            {directionLabel(s.direction)} {instrumentLabel(s)}
          </span>
        </Fact>
        <Fact id="bias" label="Bias">
          {fmtSigned(s.bias, 3)} · strength {s.strength}
        </Fact>
        <Fact id="rule" label="Entry rule">
          <span className="font-sans">{RULE_TEXT[s.entry_mode]}</span>
        </Fact>
        {s.flow_score != null ? (
          <Fact id="flow" label="Order flow">
            {fmtSigned(s.flow_score, 2)}
          </Fact>
        ) : null}
        {s.spread_pct != null ? (
          <Fact id="spread" label="Spread" title="Bid-ask spread when it fired, as % of the mid">
            {s.spread_pct.toFixed(2)}%
          </Fact>
        ) : null}
        <Fact id="expiry" label="Expiry">
          {fmtDate(s.expiry)}
        </Fact>
        <Fact id="config" label="Config">
          {s.config_version == null ? '—' : <ConfigVersionChip version={s.config_version} />}
        </Fact>
      </dl>
    </div>
  )
}

function OutcomeFacts({ s }: { s: SignalOut }) {
  const o = s.outcome
  return (
    <div>
      <Heading>After the signal</Heading>
      {o ? (
        <dl>
          <Fact
            id="result"
            label="Reached"
            title="Whether the price touched the signal's target or stop first, traded or not"
          >
            <span className={`font-sans ${RESULT_TEXT[o.result].cls}`}>
              {RESULT_TEXT[o.result].text}
            </span>
            {o.result_ts != null && o.result !== 'neither' ? (
              <span className="ml-2">{fmtIstTime(o.result_ts)}</span>
            ) : null}
          </Fact>
          <Fact id="best" label="Best" title="Against the signal's entry price">
            {fmtPrice(o.best_price)} ({fmtSigned(o.best_pct)}%)
          </Fact>
          <Fact id="worst" label="Worst" title="Against the signal's entry price">
            {fmtPrice(o.worst_price)} ({fmtSigned(o.worst_pct)}%)
          </Fact>
          <Fact id="later" label="At 1 · 5 · 15 min">
            {fmtPrice(o.px_1m)} · {fmtPrice(o.px_5m)} · {fmtPrice(o.px_15m)}
          </Fact>
        </dl>
      ) : (
        <p className="text-fg-muted">Not scored.</p>
      )}
    </div>
  )
}
