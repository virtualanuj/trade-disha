import { fireEvent, render, screen } from '@testing-library/react'

import { asInterval } from '../../lib/chartIntervals'
import { ChartIntervals } from './ChartIntervals'

describe('ChartIntervals', () => {
  it('offers 10s, 30s, 1m and 5m with the current one checked', () => {
    render(<ChartIntervals value="1m" onChange={vi.fn()} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.textContent)).toEqual(['10s', '30s', '1m', '5m'])
    expect(screen.getByRole('radio', { name: '1m' })).toHaveAttribute('aria-checked', 'true')
  })

  it('says when another is picked, and not for the current one', () => {
    const onChange = vi.fn()
    render(<ChartIntervals value="1m" onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: '1m' }))
    fireEvent.click(screen.getByRole('radio', { name: '10s' }))
    expect(onChange.mock.calls).toEqual([['10s']])
  })

  it('reads a stored choice back, falling back to 1m', () => {
    expect(asInterval('5m')).toBe('5m')
    expect(asInterval('2m')).toBe('1m')
    expect(asInterval(undefined)).toBe('1m')
  })
})
