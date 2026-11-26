import { act, render, screen } from '@testing-library/react'

import type { MetricsResponse } from '../../api/types'

const metrics: MetricsResponse = {
  last_1m: [
    { hop: 'in_to_out', n: 120, p50: 3, p95: 12.4, p99: 20, max: 31 },
    { hop: 'recv_to_paint', n: 120, p50: 6, p95: 22.5, p99: 30, max: 40 },
    { hop: 'loop_lag', n: 0, p50: 0, p95: 0, p99: 0, max: 0 },
  ],
  last_15m: [],
}
vi.mock('../../api/client', () => ({
  fetchMetrics: vi.fn(() => Promise.resolve(metrics)),
}))

const { LatencyPeek } = await import('./DebugOverlay')

describe('LatencyPeek (E27)', () => {
  it('shows p95 per hop against its budget, over budget in red', async () => {
    render(<LatencyPeek />)
    await act(async () => {
      await Promise.resolve()
    })
    const peek = screen.getByTestId('latency-peek')
    expect(peek).toHaveTextContent('app ingest → WS sent12.4/ 50')
    const paint = screen.getByText('browser recv → painted').closest('tr')
    expect(paint).toHaveClass('text-bear') // 22.5 over the 16 ms budget
    const lag = screen.getByText('backend event-loop lag').closest('tr')
    expect(lag).toHaveTextContent('—') // no samples yet
    expect(lag).not.toHaveClass('text-bear')
  })
})
