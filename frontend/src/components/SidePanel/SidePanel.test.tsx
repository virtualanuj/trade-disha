import { fireEvent, render, screen } from '@testing-library/react'

import { SidePanel } from './SidePanel'

describe('SidePanel', () => {
  it('shows its contents at the given width; hiding is left to the panel frame inside', () => {
    render(
      <SidePanel name="option chain" open onToggle={vi.fn()} width={640}>
        <div>chain rows</div>
      </SidePanel>,
    )
    expect(screen.getByText('chain rows')).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toHaveStyle({ width: '640px' })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('hidden, renders no contents and offers to show them again', () => {
    const onToggle = vi.fn()
    render(
      <SidePanel name="option chain" open={false} onToggle={onToggle} width={640}>
        <div>chain rows</div>
      </SidePanel>,
    )
    expect(screen.queryByText('chain rows')).not.toBeInTheDocument()
    const show = screen.getByRole('button', { name: 'Show option chain' })
    expect(show).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(show)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
