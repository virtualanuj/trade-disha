import type { FlowOut } from '../../api/types'
import { fmtSigned } from '../../lib/format'

const HELP =
  'Order flow, from -1 (selling) to +1 (buying), over the last few seconds. ' +
  'Futures book: resting bid quantity against ask quantity. ' +
  'Futures trades: volume traded at the ask against volume at the bid. ' +
  'Options: flow in the ATM call minus flow in the ATM put.'

function colour(v: number | null): string {
  if (v == null || v === 0) return 'text-fg-muted'
  return v > 0 ? 'text-bull' : 'text-bear'
}

/** One line under the evidence table: the order-flow score and its three parts. */
export function FlowLine({ flow }: { flow: FlowOut | undefined }) {
  if (flow?.score == null) {
    return (
      <div className="mt-2 text-xs text-fg-muted" data-testid="flow-line">
        Order flow: no data yet
      </div>
    )
  }
  return (
    <div className="mt-2 flex flex-wrap gap-x-3 text-xs text-fg-muted" data-testid="flow-line">
      <span title={HELP}>
        Order flow{' '}
        <span className={`font-mono font-medium ${colour(flow.score)}`}>
          {fmtSigned(flow.score, 2)}
        </span>
      </span>
      <span>futures book {fmtSigned(flow.fut_book, 2)}</span>
      <span>futures trades {fmtSigned(flow.fut_trades, 2)}</span>
      <span>options {fmtSigned(flow.options, 2)}</span>
      {flow.live ? null : (
        <span className="text-warn">recorded only, not used for signals yet</span>
      )}
    </div>
  )
}
