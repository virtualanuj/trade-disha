import type { SignalOut, SignalStatus } from '../../api/types'
import { fmtIstTime, fmtPrice } from '../../lib/format'

const STATUS_CLS: Record<SignalStatus, string> = {
  active: 'text-accent',
  traded: 'text-bull',
  lapsed: 'text-fg-muted',
  reversed: 'text-warn',
}

export function SignalHistory({ signals, index }: { signals: SignalOut[]; index: string }) {
  const rows = signals.filter((s) => s.index === index)
  return (
    <div className="text-xs" data-testid="signal-history">
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
              <th className="text-right font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="h-6 border-t border-border/60">
                <td>{fmtIstTime(s.ts_fired)}</td>
                <td className={s.direction === 'BUY_CE' ? 'text-bull' : 'text-bear'}>
                  {s.strike} {s.direction === 'BUY_CE' ? 'CE' : 'PE'}
                </td>
                <td className="text-right">{fmtPrice(s.entry_price)}</td>
                <td className="text-right">{fmtPrice(s.target_price)}</td>
                <td className="text-right">{fmtPrice(s.stop_price)}</td>
                <td className="text-right">{s.strength}</td>
                <td className={`text-right ${STATUS_CLS[s.status]}`}>
                  {s.status}
                  {s.status !== 'active' ? (
                    <span className="ml-1 text-fg-muted">{fmtIstTime(s.status_ts)}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
