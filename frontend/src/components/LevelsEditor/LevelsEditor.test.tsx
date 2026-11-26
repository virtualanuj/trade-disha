import { act, fireEvent, render, screen } from '@testing-library/react'

import { trade } from '../OpenTrades/fixtures'
import { LevelsEditor } from './LevelsEditor'

const box = (name: string) => screen.getByRole('spinbutton', { name })

describe('LevelsEditor', () => {
  it('starts from the trade levels and saves the new ones', async () => {
    const save = vi.fn().mockResolvedValue(trade)
    const onDone = vi.fn()
    render(<LevelsEditor trade={trade} onDone={onDone} save={save} />)
    expect(box('Target')).toHaveValue(130)
    expect(box('Stop')).toHaveValue(85)
    fireEvent.change(box('Target'), { target: { value: '140' } })
    fireEvent.change(box('Stop'), { target: { value: '95.5' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      await Promise.resolve()
    })
    expect(save).toHaveBeenCalledWith('t1', 140, 95.5)
    expect(onDone).toHaveBeenCalled()
  })

  it('shows the refusal and stays open', async () => {
    const save = vi.fn().mockRejectedValue(new Error('the stop 120 must be below the price 111'))
    const onDone = vi.fn()
    render(<LevelsEditor trade={trade} onDone={onDone} save={save} />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      await Promise.resolve()
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Not changed: the stop 120 must be below the price 111',
    )
    expect(onDone).not.toHaveBeenCalled()
  })

  it('needs both numbers', () => {
    const save = vi.fn()
    render(<LevelsEditor trade={trade} onDone={vi.fn()} save={save} />)
    fireEvent.change(box('Stop'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('alert')).toHaveTextContent('enter a number for both')
    expect(save).not.toHaveBeenCalled()
  })

  it('cancels without saving', () => {
    const save = vi.fn()
    const onDone = vi.fn()
    render(<LevelsEditor trade={trade} onDone={onDone} save={save} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onDone).toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
  })
})

it('steps the boxes in whole rupees', () => {
  render(<LevelsEditor trade={trade} onDone={vi.fn()} save={vi.fn()} />)
  expect(screen.getByRole('spinbutton', { name: 'Target' })).toHaveAttribute('step', '1')
})
