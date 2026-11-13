import { fireEvent, render, screen } from '@testing-library/react'

import { Divider } from './Divider'

function setup(orientation: 'vertical' | 'horizontal' = 'vertical') {
  const onDrag = vi.fn()
  const onReset = vi.fn()
  render(
    <Divider
      orientation={orientation}
      label="Option chain width"
      value={640}
      min={420}
      max={900}
      onDrag={onDrag}
      onReset={onReset}
    />,
  )
  return { onDrag, onReset, bar: screen.getByRole('separator', { name: 'Option chain width' }) }
}

describe('Divider', () => {
  it('describes itself to assistive technology', () => {
    const { bar } = setup()
    expect(bar).toHaveAttribute('aria-orientation', 'vertical')
    expect(bar).toHaveAttribute('aria-valuenow', '640')
    expect(bar).toHaveAttribute('aria-valuemin', '420')
    expect(bar).toHaveAttribute('aria-valuemax', '900')
  })

  it('moves with the arrow keys along its own axis', () => {
    const { bar, onDrag } = setup()
    fireEvent.keyDown(bar, { key: 'ArrowLeft' })
    fireEvent.keyDown(bar, { key: 'ArrowRight' })
    fireEvent.keyDown(bar, { key: 'ArrowUp' }) // not this divider's axis
    expect(onDrag.mock.calls).toEqual([[-16], [16]])
  })

  it('uses up and down when it separates top from bottom', () => {
    const { bar, onDrag } = setup('horizontal')
    fireEvent.keyDown(bar, { key: 'ArrowDown' })
    expect(onDrag).toHaveBeenCalledWith(16)
  })

  it('resets on double-click and on Home', () => {
    const { bar, onReset } = setup()
    fireEvent.doubleClick(bar)
    fireEvent.keyDown(bar, { key: 'Home' })
    expect(onReset).toHaveBeenCalledTimes(2)
  })
})
