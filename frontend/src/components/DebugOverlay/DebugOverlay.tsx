import { useEffect, useState } from 'react'

import { fetchMetrics } from '../../api/client'
import type { HopOut, MetricsResponse } from '../../api/types'
import { fmtMs } from '../../lib/format'
import { clientLatency } from '../../lib/latency'

const HOP_LABEL: Record<string, string> = {
  src_to_in: 'exchange → app (not budgeted)',
  in_to_out: 'app ingest → WS sent',
  out_to_recv: 'WS sent → browser recv',
  recv_to_paint: 'browser recv → painted',
  loop_lag: 'backend event-loop lag',
}

const BUDGET_P95: Record<string, number> = {
  in_to_out: 50,
  out_to_recv: 20,
  recv_to_paint: 16,
  loop_lag: 20,
}

function Row({ h }: { h: HopOut }) {
  const budget = BUDGET_P95[h.hop]
  const over = budget !== undefined && h.n > 0 && h.p95 > budget
  return (
    <tr className={over ? 'text-bear' : ''}>
      <td className="pr-3 text-left text-fg-muted">{HOP_LABEL[h.hop] ?? h.hop}</td>
      <td className="pr-3 text-right font-mono">{h.n}</td>
      <td className="pr-3 text-right font-mono">{fmtMs(h.p50)}</td>
      <td className="pr-3 text-right font-mono">{fmtMs(h.p95)}</td>
      <td className="pr-3 text-right font-mono">{fmtMs(h.p99)}</td>
      <td className="text-right font-mono text-fg-muted">{budget ?? '—'}</td>
    </tr>
  )
}

export function DebugOverlay() {
  const [m, setM] = useState<MetricsResponse | null>(null)
  const [, tick] = useState(0)

  useEffect(() => {
    const ctrl = new AbortController()
    const load = () => {
      fetchMetrics(ctrl.signal)
        .then(setM)
        .catch(() => undefined)
      tick((n) => n + 1)
    }
    load()
    const id = setInterval(load, 2000)
    return () => {
      clearInterval(id)
      ctrl.abort()
    }
  }, [])

  return (
    <div className="fixed right-4 bottom-4 z-10 rounded border border-border bg-bg-elev p-3 text-xs shadow-lg">
      <div className="mb-2 flex items-baseline justify-between gap-6">
        <span className="font-semibold">Latency, last 1 min (ms)</span>
        <span className="font-mono text-fg-muted">
          live: recv {fmtMs(clientLatency.latest.out_to_recv)} · paint{' '}
          {fmtMs(clientLatency.latest.recv_to_paint)}
        </span>
      </div>
      <table>
        <thead className="text-fg-muted">
          <tr>
            <th className="pr-3 text-left font-normal">hop</th>
            <th className="pr-3 text-right font-normal">n</th>
            <th className="pr-3 text-right font-normal">p50</th>
            <th className="pr-3 text-right font-normal">p95</th>
            <th className="pr-3 text-right font-normal">p99</th>
            <th className="text-right font-normal">budget</th>
          </tr>
        </thead>
        <tbody>{m ? m.last_1m.map((h) => <Row key={h.hop} h={h} />) : null}</tbody>
      </table>
    </div>
  )
}
