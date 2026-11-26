import { useState } from 'react'

import { setTradeLevels } from '../../api/client'
import type { PaperTradeOut } from '../../api/types'
import { directionLabel } from '../../lib/direction'
import { parseLevel } from '../../lib/ticket'

interface Props {
  trade: PaperTradeOut
  /** called once the server has taken the new levels, or on Cancel */
  onDone: () => void
  save?: (tradeId: string, target: number, stop: number) => Promise<unknown>
}

/**
 * Change an open paper trade's target and stop (E23). The server rounds them to the
 * nearest rupee (E24), checks them against the current price and refuses, with the
 * reason, levels the price has already passed. The
 * trade itself comes back on the socket, so nothing here touches the store.
 */
export function LevelsEditor({ trade, onDone, save = setTradeLevels }: Props) {
  const [target, setTarget] = useState(String(trade.target_price))
  const [stop, setStop] = useState(String(trade.stop_price))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const short = directionLabel(trade.direction) === 'SELL'

  const submit = () => {
    const t = parseLevel(target)
    const s = parseLevel(stop)
    if (t === null || s === null) {
      setError('enter a number for both')
      return
    }
    setBusy(true)
    setError(null)
    save(trade.id, t, s)
      .then(onDone)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'could not change the levels')
      })
      .finally(() => {
        setBusy(false)
      })
  }

  return (
    <form
      noValidate // the server rounds to the rupee; the step only sets the arrows
      className="flex flex-wrap items-center gap-2 py-1 font-sans text-xs"
      aria-label={`Levels for ${trade.trading_symbol}`}
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <LevelInput
        label="Target"
        hint={short ? 'below the price' : 'above the price'}
        value={target}
        onChange={setTarget}
        cls="text-bull"
      />
      <LevelInput
        label="Stop"
        hint={short ? 'above the price' : 'below the price'}
        value={stop}
        onChange={setStop}
        cls="text-bear"
      />
      <button
        type="submit"
        className="rounded border border-accent px-2 py-0.5 text-accent hover:bg-accent/10 disabled:opacity-50"
        disabled={busy}
      >
        {busy ? 'Saving…' : 'Save'}
      </button>
      <button
        type="button"
        className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg"
        onClick={onDone}
      >
        Cancel
      </button>
      {error ? (
        <span className="text-bear" role="alert">
          Not changed: {error}
        </span>
      ) : null}
    </form>
  )
}

export function LevelInput({
  label,
  hint,
  value,
  onChange,
  cls,
}: {
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
  cls: string
}) {
  return (
    <label className="flex items-center gap-1" title={hint}>
      <span className={cls}>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="1"
        min="0"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
        }}
        className="w-24 rounded border border-border bg-bg px-1 py-0.5 text-right font-mono text-fg"
      />
    </label>
  )
}
