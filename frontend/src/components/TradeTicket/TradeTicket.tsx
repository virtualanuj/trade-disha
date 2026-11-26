import { useEffect, useMemo, useState } from 'react'

import { fetchTicket, openManualTrade } from '../../api/client'
import type { PaperTradeOut, TicketOut, TicketTarget } from '../../api/types'
import { directionLabel, instrumentLabel, isFuture, isLong } from '../../lib/direction'
import { fmtDate, fmtPrice, fmtRupees } from '../../lib/format'
import { parseLevel, parseLots } from '../../lib/ticket'
import { LevelInput } from '../LevelsEditor/LevelsEditor'

interface Props {
  target: TicketTarget
  /** the instrument's price now, from the socket; the ticket's own until it has one */
  ltp: number | null
  onClose: () => void
  /** the trade the server opened */
  onOpened: (trade: PaperTradeOut) => void
  load?: (t: TicketTarget, signal?: AbortSignal) => Promise<TicketOut>
  open?: typeof openManualTrade
}

type Loaded =
  { kind: 'loading' } | { kind: 'error'; text: string } | { kind: 'ok'; ticket: TicketOut }

/**
 * Open a paper trade by hand, with no signal (E23): an option from the chain, or a metal's
 * future either way. The target and stop are the signal rule's at the price now; left as
 * they are, the server works them out again at the fill. Typed ones are kept. Opening
 * waits for the server, which fills at its price and may refuse with a reason.
 */
export function TradeTicket({
  target,
  ltp,
  onClose,
  onOpened,
  load = fetchTicket,
  open = openManualTrade,
}: Props) {
  const [loaded, setLoaded] = useState<Loaded>({ kind: 'loading' })
  const [targetText, setTargetText] = useState<string | null>(null)
  const [stopText, setStopText] = useState<string | null>(null)
  /** lots typed on a future's ticket (E28); null: the contract's default */
  const [lotsText, setLotsText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const typedLots = lotsText === null ? undefined : parseLots(lotsText)
  /** what is asked of the server: the target, with the lots once a valid number is typed */
  const asked = useMemo(
    () => (typeof typedLots === 'number' ? { ...target, lots: typedLots } : target),
    [target, typedLots],
  )

  useEffect(() => {
    if (typedLots === null) return // not a number yet: keep the last ticket
    const ctl = new AbortController()
    load(asked, ctl.signal).then(
      (ticket) => {
        if (!ctl.signal.aborted) setLoaded({ kind: 'ok', ticket })
      },
      (e: unknown) => {
        if (!ctl.signal.aborted)
          setLoaded({ kind: 'error', text: e instanceof Error ? e.message : String(e) })
      },
    )
    return () => {
      ctl.abort()
    }
  }, [load, asked, typedLots])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const ticket = loaded.kind === 'ok' ? loaded.ticket : null
  const price = ltp ?? ticket?.ltp ?? null
  const short = directionLabel(target.direction) === 'SELL'
  const label = instrumentLabel({ direction: target.direction, strike: target.strike ?? 0 })
  /** a metal's mini names itself (GOLDM); otherwise the index or metal */
  const name = target.contract ?? target.index
  const future = isFuture(target.direction)

  const submit = () => {
    if (!ticket) return
    const typedTarget = targetText === null ? null : parseLevel(targetText)
    const typedStop = stopText === null ? null : parseLevel(stopText)
    if (
      (targetText !== null && typedTarget === null) ||
      (stopText !== null && typedStop === null)
    ) {
      setError('enter a number, or leave the box as it was')
      return
    }
    if (typedLots === null) {
      setError('lots must be a whole number from 1 to 100')
      return
    }
    setBusy(true)
    setError(null)
    open(asked, { quoted: price, target: typedTarget, stop: typedStop })
      .then((trade) => {
        onOpened(trade)
        onClose()
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'could not open the trade')
      })
      .finally(() => {
        setBusy(false)
      })
  }

  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-black/30"
        aria-hidden="true"
        data-testid="ticket-backdrop"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-label={`Paper trade ${name} ${label}`}
        className="fixed left-1/2 top-24 z-40 w-[min(380px,calc(100vw-2rem))] -translate-x-1/2 rounded border border-border bg-bg-elev p-4 text-xs shadow-xl"
        data-testid="trade-ticket"
      >
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">
            <span className={isLong(target.direction) ? 'text-bull' : 'text-bear'}>
              {directionLabel(target.direction)}
            </span>{' '}
            {name} {label}
          </h2>
          <span className="text-fg-muted">opened by hand</span>
        </div>

        {loaded.kind === 'loading' ? <p className="text-fg-muted">Loading…</p> : null}
        {loaded.kind === 'error' ? (
          <p className="text-bear" role="alert">
            {loaded.text}
          </p>
        ) : null}
        {ticket ? (
          <form
            noValidate // the server rounds to the rupee; the step only sets the arrows
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            <div className="font-mono text-fg-muted">
              {ticket.trading_symbol}
              {ticket.expiry ? ` · exp ${fmtDate(ticket.expiry)}` : ''}
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
              <dt className="text-fg-muted">Price now</dt>
              <dd className="text-right font-mono text-sm" data-testid="ticket-ltp">
                {fmtPrice(price)}
              </dd>
              <dt className="text-fg-muted">Quantity</dt>
              <dd className="text-right font-mono">
                {ticket.lots} lot{ticket.lots === 1 ? '' : 's'} · {ticket.qty}
              </dd>
              <dt className="text-fg-muted">Cost, round trip</dt>
              <dd className="text-right font-mono">{fmtRupees(ticket.cost)}</dd>
              <dt className="text-fg-muted" title="Premium or margin, plus cost">
                Held in the bank
              </dt>
              <dd className="text-right font-mono">{fmtRupees(ticket.blocked)}</dd>
              {ticket.available !== null ? (
                <>
                  <dt className="text-fg-muted">Free in the bank</dt>
                  <dd className="text-right font-mono">{fmtRupees(ticket.available)}</dd>
                </>
              ) : null}
            </dl>
            {future ? (
              <label className="flex items-center gap-1" title="Lots for this trade, 1 to 100">
                <span className="text-fg-muted">Lots</span>
                <input
                  type="number"
                  inputMode="numeric"
                  step="1"
                  min="1"
                  max="100"
                  aria-label="Lots"
                  value={lotsText ?? String(ticket.lots)}
                  onChange={(e) => {
                    setLotsText(e.target.value)
                  }}
                  className="w-16 rounded border border-border bg-bg px-1 py-0.5 text-right font-mono text-fg"
                />
                <span className="text-fg-muted">
                  {lotsText === null ? 'default for the contract' : ''}
                </span>
              </label>
            ) : null}
            <div className="flex flex-wrap gap-3">
              <LevelInput
                label="Target"
                hint={short ? 'below the price' : 'above the price'}
                value={targetText ?? (ticket.target === null ? '' : String(ticket.target))}
                onChange={setTargetText}
                cls="text-bull"
              />
              <LevelInput
                label="Stop"
                hint={short ? 'above the price' : 'below the price'}
                value={stopText ?? (ticket.stop === null ? '' : String(ticket.stop))}
                onChange={setStopText}
                cls="text-bear"
              />
            </div>
            <p className="text-fg-muted" data-testid="ticket-levels-note">
              {targetText === null && stopText === null
                ? 'Signal rule: worked out again at the fill.'
                : targetText !== null && stopText !== null
                  ? 'Your levels, to the nearest rupee.'
                  : 'Your level to the nearest rupee; the other set at the fill.'}
            </p>
            {ticket.refusal ? (
              <p className="text-warn" role="status" data-testid="ticket-refusal">
                Cannot open now: {ticket.refusal}
              </p>
            ) : null}
            {error ? (
              <p className="text-bear" role="alert">
                Not opened: {error}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-border px-3 py-1 text-fg-muted hover:text-fg"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded border border-accent px-3 py-1 font-medium text-accent hover:bg-accent/10 disabled:opacity-50"
                disabled={busy || ticket.refusal !== null}
              >
                {busy ? 'Opening…' : 'Open paper trade'}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </>
  )
}
