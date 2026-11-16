import { fireEvent, render, screen } from '@testing-library/react'

import { PanelFrame } from './PanelFrame'

function setup(minimised: boolean, keepMounted = false) {
  const onToggle = vi.fn()
  render(
    <PanelFrame
      id="chart"
      title="Price chart"
      summary="last 24,801.50"
      minimised={minimised}
      onToggle={onToggle}
      keepMounted={keepMounted}
    >
      <div>candles</div>
    </PanelFrame>,
  )
  return onToggle
}

describe('PanelFrame', () => {
  it('shows the title and contents, with a button to minimise', () => {
    const onToggle = setup(false)
    expect(screen.getByText('Price chart')).toBeInTheDocument()
    expect(screen.getByText('candles')).toBeVisible()
    expect(screen.queryByText('last 24,801.50')).not.toBeInTheDocument()
    expect(screen.getByTestId('panel-chart')).toHaveAttribute('data-state', 'normal')

    const min = screen.getByRole('button', { name: 'Minimise price chart' })
    expect(min).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(min)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('minimised: shows only the title bar with the summary, and offers to expand', () => {
    const onToggle = setup(true)
    expect(screen.queryByText('candles')).not.toBeInTheDocument()
    expect(screen.getByText('last 24,801.50')).toBeInTheDocument()
    expect(screen.getByTestId('panel-chart')).toHaveAttribute('data-state', 'minimised')

    const expand = screen.getByRole('button', { name: 'Expand price chart' })
    expect(expand).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(expand)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('minimised with keepMounted: contents stay in the page but hidden', () => {
    setup(true, true)
    expect(screen.getByText('candles')).toBeInTheDocument()
    expect(screen.getByText('candles')).not.toBeVisible()
  })

  it('without move handlers there is one control only', () => {
    setup(false)
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })

  function movable(up: (() => void) | null, down: (() => void) | null, moveLabel?: string) {
    render(
      <PanelFrame
        id="chart"
        title="Price chart"
        minimised={false}
        onToggle={vi.fn()}
        move={{ up, down }}
        moveLabel={moveLabel}
      >
        <div>candles</div>
      </PanelFrame>,
    )
  }

  it('movable: offers to move the panel up and down', () => {
    const up = vi.fn()
    const down = vi.fn()
    movable(up, down)
    fireEvent.click(screen.getByRole('button', { name: 'Move price chart up' }))
    expect(up).toHaveBeenCalledTimes(1)
    expect(down).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Move price chart down' }))
    expect(down).toHaveBeenCalledTimes(1)
  })

  it('movable: a direction with nowhere to go is disabled', () => {
    movable(null, vi.fn())
    expect(screen.getByRole('button', { name: 'Move price chart up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move price chart down' })).toBeEnabled()
  })

  it('movable: a panel that moves with another says so', () => {
    movable(vi.fn(), vi.fn(), 'market view and signal')
    expect(screen.getByRole('button', { name: 'Move market view and signal up' })).toBeEnabled()
  })
})
