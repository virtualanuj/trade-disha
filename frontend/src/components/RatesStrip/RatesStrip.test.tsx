import { fireEvent, render, screen } from '@testing-library/react'

import type { Rate } from '../../lib/rates'
import { RatesStrip } from './RatesStrip'

const rates: Rate[] = [
  { name: 'NIFTY', ltp: 24_512.3, changePct: 0.42, metal: null, tab: 'NIFTY' },
  { name: 'SENSEX', ltp: 80_911.05, changePct: -0.38, metal: null, tab: null },
  { name: 'GOLD', ltp: null, changePct: null, metal: 'GOLD', tab: 'BULLION' },
  { name: 'GOLDBEES', ltp: 108.42, changePct: 0, metal: 'GOLD', tab: 'BULLION' },
]

describe('RatesStrip', () => {
  it('shows each rate with its price and day change %, coloured by side', () => {
    render(<RatesStrip rates={rates} onOpen={vi.fn()} />)
    expect(screen.getByTestId('rate-NIFTY')).toHaveTextContent('NIFTY24,512.30+0.42%')
    expect(screen.getByText('+0.42%')).toHaveClass('text-bull')
    expect(screen.getByText('-0.38%')).toHaveClass('text-bear')
    expect(screen.getByText('0.00%')).toHaveClass('text-fg-muted')
    expect(screen.getByTestId('rate-GOLD')).toHaveTextContent('GOLD—')
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
  })

  it('opens the tab, and the metal on BULLION; SENSEX has nowhere to go', () => {
    const onOpen = vi.fn()
    render(<RatesStrip rates={rates} onOpen={onOpen} />)
    fireEvent.click(screen.getByTestId('rate-NIFTY'))
    fireEvent.click(screen.getByTestId('rate-GOLDBEES'))
    expect(onOpen.mock.calls).toEqual([
      ['NIFTY', null],
      ['BULLION', 'GOLD'],
    ])
    expect(screen.getByTestId('rate-SENSEX').tagName).toBe('SPAN')
  })
})
