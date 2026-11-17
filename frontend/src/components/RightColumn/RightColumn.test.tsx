import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'

import { RightColumn } from './RightColumn'

type Props = ComponentProps<typeof RightColumn>

function setup(over: Partial<Props> = {}) {
  const props: Props = {
    chain: <div>chain rows</div>,
    chainMinimised: false,
    news: <div>headline rows</div>,
    newsMinimised: false,
    newsHidden: false,
    onExpandAll: vi.fn(),
    width: 640,
    onWidth: vi.fn(),
    newsHeight: 280,
    onNewsHeight: vi.fn(),
    ...over,
  }
  render(<RightColumn {...props} />)
  return props
}

const slot = (name: 'chain' | 'news') => screen.getByTestId(`right-${name}`)

describe('RightColumn', () => {
  it('both expanded: chain fills, headlines below at their height, with both dividers', () => {
    setup()
    expect(screen.getByText('chain rows')).toBeInTheDocument()
    expect(screen.getByText('headline rows')).toBeInTheDocument()
    expect(slot('chain')).toHaveAttribute('data-fill', 'true')
    expect(slot('news')).not.toHaveAttribute('data-fill')
    expect(slot('news')).toHaveStyle({ height: '280px' })
    expect(screen.getByRole('separator', { name: 'Headlines height' })).toBeInTheDocument()
    expect(screen.getByRole('separator', { name: 'Option chain width' })).toBeInTheDocument()
    expect(screen.getByRole('complementary')).toHaveStyle({ width: '640px' })
  })

  it('dragging the headlines divider down makes the headlines shorter', () => {
    const props = setup()
    const sep = screen.getByRole('separator', { name: 'Headlines height' })
    fireEvent.keyDown(sep, { key: 'ArrowDown' })
    expect(props.onNewsHeight).toHaveBeenCalledWith(expect.any(Number))
    const [h] = (props.onNewsHeight as ReturnType<typeof vi.fn>).mock.calls[0] as [number]
    expect(h).toBeLessThan(280)
  })

  it('chain minimised: headlines fill under the chain title bar, no height divider', () => {
    setup({ chainMinimised: true })
    expect(slot('chain')).not.toHaveAttribute('data-fill')
    expect(slot('news')).toHaveAttribute('data-fill', 'true')
    expect(screen.queryByRole('separator', { name: 'Headlines height' })).toBeNull()
  })

  it('headlines minimised: the chain fills, headlines keep their title bar', () => {
    setup({ newsMinimised: true })
    expect(slot('chain')).toHaveAttribute('data-fill', 'true')
    expect(slot('news')).not.toHaveAttribute('data-fill')
    expect(screen.getByText('headline rows')).toBeInTheDocument()
    expect(screen.queryByRole('separator', { name: 'Headlines height' })).toBeNull()
  })

  it('headlines hidden: the chain alone, as before E10', () => {
    setup({ newsHidden: true })
    expect(screen.queryByText('headline rows')).toBeNull()
    expect(slot('chain')).toHaveAttribute('data-fill', 'true')
    expect(screen.queryByRole('separator', { name: 'Headlines height' })).toBeNull()
  })

  it.each<[string, Partial<Props>, string]>([
    ['both minimised', { chainMinimised: true, newsMinimised: true }, 'option chain and headlines'],
    [
      'chain minimised, headlines hidden',
      { chainMinimised: true, newsHidden: true },
      'option chain',
    ],
    ['no chain, headlines minimised', { chain: null, newsMinimised: true }, 'headlines'],
  ])('nothing expanded (%s): a strip that expands everything', (_, over, name) => {
    const props = setup(over)
    expect(screen.queryByText('chain rows')).toBeNull()
    expect(screen.queryByText('headline rows')).toBeNull()
    expect(screen.queryByRole('separator')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: `Show ${name}` }))
    expect(props.onExpandAll).toHaveBeenCalledTimes(1)
  })

  it('no chain (BULLION): headlines alone, filling the column', () => {
    setup({ chain: null })
    expect(screen.queryByTestId('right-chain')).toBeNull()
    expect(slot('news')).toHaveAttribute('data-fill', 'true')
    expect(screen.getByRole('separator', { name: 'Option chain width' })).toBeInTheDocument()
  })

  it('no chain and headlines hidden: no column at all', () => {
    const { container } = render(
      <RightColumn
        chain={null}
        chainMinimised={false}
        news={<div>headline rows</div>}
        newsMinimised={false}
        newsHidden
        onExpandAll={vi.fn()}
        width={640}
        onWidth={vi.fn()}
        newsHeight={280}
        onNewsHeight={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
