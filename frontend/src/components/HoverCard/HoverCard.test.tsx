import { act, fireEvent, render, screen } from '@testing-library/react'

import { CLOSE_DELAY_MS, HoverCard, OPEN_DELAY_MS } from './HoverCard'

function show(card: string | null = 'preview') {
  return render(
    <HoverCard card={card} label="Preview">
      <button type="button">Tool</button>
    </HoverCard>,
  )
}

const wait = (ms: number) => {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

describe('HoverCard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens after a short hover, not on a pass across', () => {
    show()
    const tool = screen.getByRole('button', { name: 'Tool' })
    fireEvent.mouseEnter(tool)
    wait(OPEN_DELAY_MS - 50)
    fireEvent.mouseLeave(tool)
    wait(OPEN_DELAY_MS)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseEnter(tool)
    wait(OPEN_DELAY_MS)
    expect(screen.getByRole('tooltip', { name: 'Preview' })).toHaveTextContent('preview')
  })

  it('stays open while the mouse moves into the card, and closes after leaving', () => {
    show()
    const tool = screen.getByRole('button', { name: 'Tool' })
    fireEvent.mouseEnter(tool)
    wait(OPEN_DELAY_MS)
    fireEvent.mouseLeave(tool)
    wait(CLOSE_DELAY_MS - 50)
    fireEvent.mouseEnter(screen.getByRole('tooltip'))
    wait(CLOSE_DELAY_MS)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.mouseLeave(screen.getByRole('tooltip'))
    wait(CLOSE_DELAY_MS)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('closes on Esc and on a click', () => {
    show()
    const tool = screen.getByRole('button', { name: 'Tool' })
    fireEvent.mouseEnter(tool)
    wait(OPEN_DELAY_MS)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseLeave(tool)
    fireEvent.mouseEnter(tool)
    wait(OPEN_DELAY_MS)
    fireEvent.click(tool)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows nothing when there is nothing to preview', () => {
    show(null)
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Tool' }))
    wait(OPEN_DELAY_MS)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
