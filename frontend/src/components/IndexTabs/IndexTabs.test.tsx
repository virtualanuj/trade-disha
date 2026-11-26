import { fireEvent, render, screen } from '@testing-library/react'

import { tabGroups } from '../../lib/tabs'
import { ETF_TAB } from '../../state/store'
import { IndexTabs } from './IndexTabs'

describe('IndexTabs (E32)', () => {
  const groups = tabGroups(['NIFTY', 'BANKNIFTY'], true, ['GOLD', 'SILVER'])

  it('labels each exchange and names each tab by its exchange', () => {
    render(<IndexTabs groups={groups} selected="GOLD" onSelect={vi.fn()} />)
    expect(screen.getByRole('tablist')).toHaveTextContent('NSENIFTYBANKNIFTYBULLIONMCXGOLDSILVER')
    expect(screen.getByRole('tab', { name: 'MCX GOLD' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'NSE BULLION' })).toHaveAttribute(
      'aria-selected',
      'false',
    )
  })

  it('selects a tab by its id', () => {
    const onSelect = vi.fn()
    render(<IndexTabs groups={groups} selected="NIFTY" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('tab', { name: 'NSE BULLION' }))
    fireEvent.click(screen.getByRole('tab', { name: 'MCX SILVER' }))
    expect(onSelect.mock.calls).toEqual([[ETF_TAB], ['SILVER']])
  })
})
