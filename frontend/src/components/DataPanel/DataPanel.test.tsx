import { fireEvent, render, screen } from '@testing-library/react'

import type { UsageOut } from '../../api/types'
import { DataPanel } from './DataPanel'

const held: UsageOut = {
  db_bytes: 157_286_400,
  tick_rows: 2_100_000,
  tick_days: 3,
  oldest: '2026-11-11',
  newest: '2026-11-13',
  prune_rows: 0,
  prune_days: 0,
  prune_bytes_estimate: 0,
}
const preview: UsageOut = {
  ...held,
  prune_rows: 1_400_000,
  prune_days: 2,
  prune_bytes_estimate: 104_857_600,
}

describe('DataPanel', () => {
  it('previews, requires the date to be typed, then deletes', async () => {
    const usage = vi.fn((until?: string) => Promise.resolve(until ? preview : held))
    const prune = vi.fn().mockResolvedValue({
      until_date: '2026-11-12',
      rows_deleted: 1_400_000,
      bytes_freed: 99_614_720,
    })
    render(<DataPanel usage={usage} prune={prune} />)

    fireEvent.click(screen.getByRole('button', { name: 'Data' }))
    const panel = await screen.findByTestId('data-panel')
    expect(await screen.findByText('150 MB')).toBeInTheDocument()
    expect(panel).toHaveTextContent('11/11/2026')
    expect(panel).toHaveTextContent('13/11/2026')

    fireEvent.change(screen.getByLabelText('Up to and including'), {
      target: { value: '2026-11-12' },
    })
    const line = await screen.findByTestId('prune-preview')
    expect(line).toHaveTextContent('2 days, 14,00,000 ticks, about 100 MB')

    const del = screen.getByRole('button', { name: 'Delete ticks' })
    expect(del).toBeDisabled()
    const confirm = screen.getByLabelText('Type 12/11/2026 to confirm')
    fireEvent.change(confirm, { target: { value: '2026-11-12' } })
    expect(del).toBeDisabled() // the date must be typed as it is shown
    fireEvent.change(confirm, { target: { value: '12/11/2026' } })
    expect(del).toBeEnabled()
    fireEvent.click(del)

    expect(prune).toHaveBeenCalledWith('2026-11-12')
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Deleted 14,00,000 ticks up to 12/11/2026',
    )
  })

  it('offers nothing to delete when no ticks fall in range', async () => {
    const usage = vi.fn().mockResolvedValue(held)
    render(<DataPanel usage={usage} prune={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Data' }))
    await screen.findByTestId('data-panel')
    fireEvent.change(screen.getByLabelText('Up to and including'), {
      target: { value: '2026-11-01' },
    })
    expect(await screen.findByTestId('prune-preview')).toHaveTextContent(
      'No ticks on or before 01/11/2026',
    )
    expect(screen.queryByRole('button', { name: 'Delete ticks' })).not.toBeInTheDocument()
  })
})
