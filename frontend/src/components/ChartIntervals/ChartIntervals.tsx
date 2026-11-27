import type { ChartInterval } from '../../api/types'
import { CHART_INTERVALS, INTERVAL_TEXT } from '../../lib/chartIntervals'

interface Props {
  value: ChartInterval
  onChange: (next: ChartInterval) => void
}

/** The chart's bar size (E27): display only; the view and signals stay on 1-minute closes. */
export function ChartIntervals({ value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Chart interval"
      className="inline-flex overflow-hidden rounded border border-border text-[11px]"
      data-testid="chart-intervals"
    >
      {CHART_INTERVALS.map((iv) => (
        <button
          key={iv}
          type="button"
          role="radio"
          aria-checked={iv === value}
          title={`${INTERVAL_TEXT[iv]} bars`}
          className={`px-2 py-0.5 font-mono ${
            iv === value ? 'bg-accent/20 text-fg' : 'text-fg-muted hover:text-fg'
          }`}
          onClick={() => {
            if (iv !== value) onChange(iv)
          }}
        >
          {iv}
        </button>
      ))}
    </div>
  )
}
