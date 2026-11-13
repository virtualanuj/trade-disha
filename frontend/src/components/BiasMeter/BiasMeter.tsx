import type { BiasOut } from '../../api/types'
import { fmtIstTime, labelColour } from '../../lib/format'

export function BiasMeter({ bias }: { bias: BiasOut | undefined }) {
  const value = bias?.bias ?? 0
  const pct = ((value + 1) / 2) * 100
  const colour = labelColour(bias?.label)
  return (
    <div data-testid="bias-meter">
      <div className="mb-2 flex items-baseline justify-end">
        <span className="font-mono text-xs text-fg-muted">
          {bias ? `as of ${fmtIstTime(bias.minute_ts + 60_000)}` : 'waiting for first minute'}
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-bg-row">
        <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <div
          className="absolute inset-y-0 rounded-full bg-neutral/30"
          style={{
            left: `${String(((1 - (bias ? 0.2 : 0)) / 2) * 100)}%`,
            width: `${String((bias ? 0.2 : 0) * 100)}%`,
          }}
          aria-hidden="true"
        />
        <div
          className={`absolute top-1/2 h-5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded transition-[left] duration-300 ${
            bias?.label === 'Bullish'
              ? 'bg-bull'
              : bias?.label === 'Bearish'
                ? 'bg-bear'
                : 'bg-neutral'
          }`}
          style={{ left: `${String(pct)}%` }}
          role="meter"
          aria-valuemin={-100}
          aria-valuemax={100}
          aria-valuenow={Math.round(value * 100)}
          aria-label="Bias"
        />
      </div>
      <div className="mt-2 flex items-baseline justify-between text-xs">
        <span className="text-bear">Bearish</span>
        <span className={`font-mono text-lg font-semibold ${colour}`}>
          {bias ? `${String(bias.strength)} ${bias.label}` : '—'}
          {bias?.is_expiry_day ? <span className="ml-2 text-xs text-warn">expiry day</span> : null}
        </span>
        <span className="text-bull">Bullish</span>
      </div>
    </div>
  )
}
