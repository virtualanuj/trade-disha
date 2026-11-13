import type { BiasOut, IndicatorOut } from '../../api/types'
import { fmtSigned } from '../../lib/format'

const GROUP_LABEL: Record<IndicatorOut['group'], string> = {
  trend: 'Price trend',
  oi: 'Open interest',
  premium: 'Premium behaviour',
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

function valueTitle(v: Record<string, number>): string {
  return Object.entries(v)
    .map(([k, x]) => `${k}: ${Number.isInteger(x) ? String(x) : x.toFixed(3)}`)
    .join('\n')
}

export function EvidenceTable({ bias }: { bias: BiasOut | undefined }) {
  if (!bias) {
    return <p className="text-xs text-fg-muted">Evidence appears after the first minute closes.</p>
  }
  const groups: IndicatorOut['group'][] = ['trend', 'oi', 'premium']
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
                const dim = r.quality !== 'ok'
                return (
                  <tr key={r.name} className={`h-7 ${dim ? 'text-fg-muted/70' : ''}`}>
                    <td className="pr-2">{NAME_LABEL[r.name] ?? r.name}</td>
                    <td className="pr-2" title={valueTitle(r.value)}>
                      {r.note}
                      {dim ? <span className="ml-1 italic">({r.quality})</span> : null}
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
    </div>
  )
}
