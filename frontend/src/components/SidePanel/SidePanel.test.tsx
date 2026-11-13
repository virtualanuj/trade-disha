import { fireEvent, render, screen } from '@testing-library/react'

import { SidePanel } from './SidePanel'

describe('SidePanel', () => {
  it('shows its contents at the given width with a way to hide them', () => {
    const onToggle = vi.fn()
    render(
      <SidePanel name="option chain" open onToggle={onToggle} width={640}>
        <div>chain rows</div>
      </SidePanel>,
    )
    expect(screen.getByText('chain rows')).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toHaveStyle({ width: '640px' })
    fireEvent.click(screen.getByRole('button', { name: 'Hide option chain' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
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
