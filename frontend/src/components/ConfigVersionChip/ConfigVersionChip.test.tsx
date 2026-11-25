import { act, fireEvent, render, screen, within } from '@testing-library/react'

import type { ConfigVersionDetail } from '../../api/types'
import { useMarketStore } from '../../state/store'
import { ConfigVersionChip } from './ConfigVersionChip'

const v3: ConfigVersionDetail = {
  version: 3,
  tag: 'higher entry bar',
  created_ts: 1_794_800_000_000,
  source: 'edit',
  reverted_from: null,
  active: false,
  params: {
    bias: { entry_threshold: 0.6, neutral_band: 0.2 },
    signal: { entry_mode: 'minute_close', last_signal_time: '15:00:00' },
  },
}

function current(entry: number) {
  useMarketStore.setState({
    parameters: {
      version: 5,
      tag: 'now',
      created_ts: 1_794_900_000_000,
      params: {
        bias: { entry_threshold: entry, neutral_band: 0.2 },
        signal: { entry_mode: 'minute_close', last_signal_time: '15:00:00' },
      },
    },
  })
}

describe('ConfigVersionChip', () => {
  it('draws nothing for a signal with no version', () => {
    const { container } = render(<ConfigVersionChip version={null} load={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the version, and on hover its tag and values', async () => {
    current(0.5)
    const load = vi.fn().mockResolvedValue(v3)
    render(<ConfigVersionChip version={3} load={load} />)
    const chip = screen.getByRole('button', { name: 'Config version 3' })
    expect(chip).toHaveTextContent('v3')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(load).not.toHaveBeenCalled()

    fireEvent.mouseEnter(chip)
    const tip = await screen.findByRole('tooltip')
    expect(load).toHaveBeenCalledWith(3)
    expect(await within(tip).findByText('higher entry bar')).toBeInTheDocument()
    expect(tip).toHaveTextContent('entry_threshold0.6')
    expect(tip).toHaveTextContent('last_signal_time15:00')
    expect(tip).toHaveTextContent('1 value differs from the config in force')
    const row = within(tip).getByText('entry_threshold').parentElement
    expect(row).toHaveAttribute('data-differs', 'true')
    expect(row).toHaveAttribute('title', 'now 0.5')
    expect(within(tip).getByText('neutral_band').parentElement).not.toHaveAttribute('data-differs')
  })

  it('says so when the values are the ones in force', async () => {
    current(0.6)
    render(<ConfigVersionChip version={3} load={vi.fn().mockResolvedValue(v3)} />)
    fireEvent.focus(screen.getByRole('button', { name: 'Config version 3' }))
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'same values as the config in force',
    )
  })

  it('closes shortly after the pointer leaves', async () => {
    current(0.5)
    render(<ConfigVersionChip version={3} load={vi.fn().mockResolvedValue(v3)} />)
    const chip = screen.getByRole('button', { name: 'Config version 3' })
    fireEvent.mouseEnter(chip)
    await screen.findByText('higher entry bar')
    fireEvent.mouseLeave(chip)
    await vi.waitFor(() => {
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    })
  })

  it('says when the version cannot be loaded', async () => {
    render(<ConfigVersionChip version={3} load={vi.fn().mockRejectedValue(new Error('x'))} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Config version 3' }))
    expect(await screen.findByText('Could not load config v3.')).toBeInTheDocument()
  })

  it('loads the new version when the chip is reused for another signal', async () => {
    current(0.5)
    const v4: ConfigVersionDetail = { ...v3, version: 4, tag: 'lower stop' }
    const load = vi.fn((v: number) => Promise.resolve(v === 3 ? v3 : v4))
    const { rerender } = render(<ConfigVersionChip version={3} load={load} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Config version 3' }))
    await screen.findByText('higher entry bar')
    fireEvent.mouseLeave(screen.getByRole('button', { name: 'Config version 3' }))

    // the signal card keeps the same chip when the tab switches to another index
    rerender(<ConfigVersionChip version={4} load={load} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Config version 4' }))
    expect(await screen.findByText('lower stop')).toBeInTheDocument()
    expect(load).toHaveBeenLastCalledWith(4)
    expect(screen.queryByText('higher entry bar')).not.toBeInTheDocument()
  })

  it('ignores a reply for a version the chip no longer shows', async () => {
    current(0.5)
    let answerV3: (d: ConfigVersionDetail) => void = () => undefined
    const v4: ConfigVersionDetail = { ...v3, version: 4, tag: 'lower stop' }
    const load = vi.fn((v: number) =>
      v === 3
        ? new Promise<ConfigVersionDetail>((resolve) => {
            answerV3 = resolve
          })
        : Promise.resolve(v4),
    )
    const { rerender } = render(<ConfigVersionChip version={3} load={load} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Config version 3' }))
    rerender(<ConfigVersionChip version={4} load={load} />)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Config version 4' }))
    expect(await screen.findByText('lower stop')).toBeInTheDocument()
    await act(async () => {
      answerV3(v3) // the slow v3 reply lands last
      await Promise.resolve()
    })
    expect(screen.getByText('lower stop')).toBeInTheDocument()
    expect(screen.queryByText('higher entry bar')).not.toBeInTheDocument()
  })
})
