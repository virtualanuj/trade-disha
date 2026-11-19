import { useState } from 'react'

import type { BiasOut, IndicatorOut } from '../../api/types'
import { fmtSigned } from '../../lib/format'

const GROUP_LABEL: Record<IndicatorOut['group'], string> = {
  trend: 'Price trend',
  oi: 'Open interest',
  premium: 'Premium behaviour',
  flow: 'Order flow',
  macro: 'Macro: dollar, crude, metals',
}

const NAME_LABEL: Record<string, string> = {
  ema_cross: 'EMA crossover',
  vwap_position: 'Futures vs VWAP',
  supertrend: 'Supertrend',
  pcr: 'Put-call ratio',
  oi_change_atm: 'ATM OI build-up',
  max_pain_drift: 'Max-pain drift',
  premium_momentum: 'CE vs PE momentum',
  iv_change: 'IV change',
  premium_confirmation: 'Premium confirmation',
  dollar_index: 'Dollar index (proxy)',
  usd_inr: 'USD/INR',
  crude: 'Crude oil',
  gold: 'Gold',
  silver: 'Silver',
  gift_nifty: 'GIFT Nifty gap',
  futures_oi: 'Futures OI build-up',
  net_volume: 'Net traded volume',
  book_imbalance: 'Order-book lean',
  peer_metal: 'Other metal’s trend',
}

function ScoreBar({ score }: { score: number }) {
  const w = Math.abs(score) * 50
  const pos = score >= 0
  return (
    <div className="relative h-2 w-24 rounded bg-bg-row" aria-hidden="true">
      <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
      <div
        className={`absolute inset-y-0 rounded ${pos ? 'bg-bull' : 'bg-bear'}`}
        style={
          pos ? { left: '50%', width: `${String(w)}%` } : { right: '50%', width: `${String(w)}%` }
        }
      />
    </div>
  )
}

/** A factor's on/off switch: on means it counts in the bias (E15). */
function FactorSwitch({
  label,
  on,
  busy,
  onChange,
}: {
  label: string
  on: boolean
  busy: boolean
  onChange: (on: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={`Use ${label} in the bias`}
      title={on ? `Leave ${label} out of the bias` : `Count ${label} in the bias`}
      disabled={busy}
      onClick={() => {
        onChange(!on)
      }}
      className={`relative inline-flex h-3.5 w-6 shrink-0 rounded-full transition-colors disabled:opacity-50 ${on ? 'bg-accent/80' : 'bg-border'}`}
    >
      <span
        className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-bg transition-[left] ${on ? 'left-3' : 'left-0.5'}`}
      />
    </button>
  )
}

function valueTitle(v: Record<string, number>): string {
  return Object.entries(v)
    .map(([k, x]) => `${k}: ${Number.isInteger(x) ? String(x) : x.toFixed(3)}`)
    .join('\n')
}

interface Props {
  bias: BiasOut | undefined
  /** factors switched off for this index or metal; with `onToggle`, each row gets a switch */
  off?: string[]
  /** resolves once the server has the change; rejects with a reason to show */
  onToggle?: (name: string, enabled: boolean) => Promise<unknown>
  onAllOn?: () => Promise<unknown>
}

export function EvidenceTable({ bias, off = [], onToggle, onAllOn }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const run = (key: string, action: () => Promise<unknown>) => {
    setBusy(key)
    setError(null)
    action()
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        setBusy(null)
      })
  }
  if (!bias) {
    return <p className="text-xs text-fg-muted">Evidence appears after the first minute closes.</p>
  }
  // A group with no indicators and no weight plays no part: bullion has no option chain
  // (spec §9a), the index has no flow group, and without the live feed there is no macro
  // data (spec §8.6).
  const groups = (['trend', 'oi', 'premium', 'flow', 'macro'] as const).filter(
    (g) => (bias.group_weights[g] ?? 0) > 0 || bias.indicators.some((i) => i.group === g),
  )
  return (
    <div className="text-xs" data-testid="evidence">
      <table className="w-full">
        <thead className="text-fg-muted">
          <tr className="h-6">
            <th className="text-left font-normal">Evidence</th>
            <th className="text-left font-normal">Reading</th>
            <th className="text-left font-normal">Score</th>
            <th className="pl-3 text-right font-normal">Weight</th>
            <th className="pl-3 text-right font-normal">Contrib.</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const rows = bias.indicators.filter((i) => i.group === g)
            const gw = bias.group_weights[g] ?? 0
            const gs = bias.group_scores[g] ?? 0
            return [
              <tr key={`${g}-head`} className="h-6 border-t border-border bg-bg-row/40">
                <td colSpan={3} className="font-semibold">
                  {GROUP_LABEL[g]}
                  <span className="ml-2 font-normal text-fg-muted">score {fmtSigned(gs, 2)}</span>
                </td>
                <td className="text-right font-mono">{gw.toFixed(3)}</td>
                <td className="text-right font-mono">{fmtSigned(gs * gw, 3)}</td>
              </tr>,
              ...rows.map((r) => {
                const label = NAME_LABEL[r.name] ?? r.name
                const on = !off.includes(r.name) // what the trader asked for
                const pending = on !== r.enabled // the bias shown predates the switch
                const dim = r.quality !== 'ok' || !r.enabled
                const marker = !r.enabled ? 'off' : r.quality !== 'info' ? r.quality : null
                return (
                  <tr key={r.name} className={`h-7 ${dim ? 'text-fg-muted/70' : ''}`}>
                    <td className="pr-2">
                      <div className="flex items-center gap-2">
                        {onToggle ? (
                          <FactorSwitch
                            label={label}
                            on={on}
                            busy={busy !== null}
                            onChange={(enabled) => {
                              run(r.name, () => onToggle(r.name, enabled))
                            }}
                          />
                        ) : null}
                        {label}
                      </div>
                    </td>
                    <td className="pr-2" title={valueTitle(r.value)}>
                      {r.note}
                      {pending ? (
                        <span className="ml-1 italic text-warn">
                          ({on ? 'on' : 'off'} from the next minute close)
                        </span>
                      ) : dim && marker ? (
                        <span className="ml-1 italic">({marker})</span>
                      ) : null}
                    </td>
                    <td className="pr-2">
                      <div className="flex items-center gap-2">
                        <ScoreBar score={dim ? 0 : r.score} />
                        <span className="font-mono">{fmtSigned(r.score, 2)}</span>
                      </div>
                    </td>
                    <td className="text-right font-mono">{r.weight.toFixed(3)}</td>
                    <td className="text-right font-mono">{fmtSigned(r.contribution, 3)}</td>
                  </tr>
                )
              }),
            ]
          })}
          <tr className="h-7 border-t border-border font-semibold">
            <td colSpan={4}>Bias</td>
            <td className="text-right font-mono">{fmtSigned(bias.bias, 3)}</td>
          </tr>
        </tbody>
      </table>
      {onToggle && onAllOn && off.length > 0 ? (
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => {
            run('*', onAllOn)
          }}
          className="mt-2 text-accent hover:underline disabled:opacity-50"
        >
          Turn all back on
        </button>
      ) : null}
      {error ? (
        <p role="alert" className="mt-1 text-bear">
          {error}
        </p>
      ) : null}
    </div>
  )
}
