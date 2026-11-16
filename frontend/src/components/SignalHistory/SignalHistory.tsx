import type { OutcomeResult, SignalOut, SignalStatus } from '../../api/types'
import { instrumentLabel, isLong } from '../../lib/direction'
import { fmtIstTime, fmtPrice, fmtSigned } from '../../lib/format'
import { ConfigVersionChip } from '../ConfigVersionChip/ConfigVersionChip'

const STATUS_CLS: Record<SignalStatus, string> = {
  active: 'text-accent',
  traded: 'text-bull',
  lapsed: 'text-fg-muted',
  reversed: 'text-warn',
}

const RESULT_CLS: Record<OutcomeResult, string> = {
  open: 'text-fg-muted',
  target: 'text-bull',
  stop: 'text-bear',
  neither: 'text-fg-muted',
}

/** How the day's scored signals turned out; null until one has a result. */
function scoreLine(rows: SignalOut[]): string | null {
  const results = rows.map((s) => s.outcome?.result).filter((r) => r && r !== 'open')
  if (results.length === 0) return null
  const count = (r: OutcomeResult) => String(results.filter((x) => x === r).length)
  return (
    `${String(results.length)} of ${String(rows.length)} scored · ${count('target')} target` +
    ` · ${count('stop')} stop · ${count('neither')} neither`
  )
}

function Outcome({ signal }: { signal: SignalOut }) {
  const o = signal.outcome
  if (!o) return <span className="text-fg-muted">—</span>
  return (
    <>
      <span className={RESULT_CLS[o.result]}>{o.result === 'open' ? 'following' : o.result}</span>
      {o.result_ts != null && o.result !== 'neither' ? (
        <span className="ml-1 text-fg-muted">{fmtIstTime(o.result_ts)}</span>
      ) : null}
      <span
        className="ml-2 text-fg-muted"
        title="Best and worst option price reached after firing, against the entry price"
      >
        {fmtSigned(o.best_pct)}% / {fmtSigned(o.worst_pct)}%
      </span>
    </>
  )
}

export function SignalHistory({ signals, index }: { signals: SignalOut[]; index: string }) {
  const rows = signals.filter((s) => s.index === index)
  const score = scoreLine(rows.filter((s) => !s.shadow))
  const shadowRows = rows.filter((s) => s.shadow)
  const shadowScore = scoreLine(shadowRows)
  const scoreTitle =
    'Whether the option touched the target or the stop first after each signal, traded or not'
  return (
    <div className="text-xs" data-testid="signal-history">
      {score ? (
        <div className="mb-1 text-fg-muted" data-testid="signal-scorecard" title={scoreTitle}>
          {score}
        </div>
      ) : null}
      {shadowScore ? (
        <div
          className="mb-1 text-fg-muted"
          data-testid="shadow-scorecard"
          title="Signals the other entry rule would have given. Recorded for comparison; not tradable."
        >
          shadow ({shadowRows[0]?.entry_mode === 'trigger' ? 'trigger' : 'minute close'}):{' '}
          {shadowScore}
        </div>
      ) : null}
      {rows.length === 0 ? (
        <div className="text-fg-muted">None yet.</div>
      ) : (
        <table className="w-full font-mono">
          <thead className="text-fg-muted">
            <tr className="h-6 font-sans">
              <th className="text-left font-normal">Fired</th>
              <th className="text-left font-normal">Option</th>
              <th className="text-right font-normal">Entry</th>
              <th className="text-right font-normal">Target</th>
              <th className="text-right font-normal">Stop</th>
              <th className="text-right font-normal">Bias</th>
              <th
                className="text-right font-normal"
                title="The config version in force when the signal fired; hover one for its values"
              >
                Config
              </th>
              <th className="text-right font-normal">Status</th>
              <th className="text-right font-normal">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr
                key={s.id}
                className={`h-6 border-t border-border/60 ${s.shadow ? 'opacity-60' : ''}`}
              >
                <td>
                  {fmtIstTime(s.ts_fired)}
                  {s.shadow ? <span className="ml-1 font-sans text-warn">shadow</span> : null}
                </td>
                <td className={isLong(s.direction) ? 'text-bull' : 'text-bear'}>
                  {instrumentLabel(s)}
                </td>
                <td className="text-right">{fmtPrice(s.entry_price)}</td>
                <td className="text-right">{fmtPrice(s.target_price)}</td>
                <td className="text-right">{fmtPrice(s.stop_price)}</td>
                <td className="text-right">{s.strength}</td>
                <td className="text-right">
                  <ConfigVersionChip version={s.config_version} />
                </td>
                <td className={`text-right ${STATUS_CLS[s.status]}`}>
                  {s.status}
                  {s.status !== 'active' ? (
                    <span className="ml-1 text-fg-muted">{fmtIstTime(s.status_ts)}</span>
                  ) : null}
                </td>
                <td className="text-right" data-testid={`outcome-${s.id}`}>
                  <Outcome signal={s} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
