import { act, fireEvent, render, screen } from '@testing-library/react'

import type { TicketOut, TicketTarget } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { TradeTicket } from './TradeTicket'

const target: TicketTarget = { index: 'NIFTY', direction: 'BUY_CE', strike: 25050 }
const ticket: TicketOut = {
  index: 'NIFTY',
  direction: 'BUY_CE',
  instrument_key: 'NSE_FO|Y',
  trading_symbol: 'NIFTY 25050 CE 17 NOV 26',
  strike: 25050,
  expiry: '2026-11-17',
  lots: 1,
  qty: 65,
  ltp: 80,
  ltp_ts: 1,
  target: 104,
  stop: 68,
  cost: 60,
  blocked: 5260,
  available: 2_500_000,
  refusal: null,
}

async function show(over: Partial<TicketOut> = {}, ltp: number | null = 81) {
  const load = vi.fn().mockResolvedValue({ ...ticket, ...over })
  const open = vi.fn().mockResolvedValue({ ...trade, manual: true })
  const onClose = vi.fn()
  const onOpened = vi.fn()
  render(
    <TradeTicket
      target={target}
      ltp={ltp}
      onClose={onClose}
      onOpened={onOpened}
      load={load}
      open={open}
    />,
  )
  await screen.findByText('NIFTY 25050 CE 17 NOV 26 · exp 17/11/2026')
  return { load, open, onClose, onOpened }
}

const box = (name: string) => screen.getByRole('spinbutton', { name })

describe('TradeTicket', () => {
  it('shows the contract, the live price, the money and the signal rule levels', async () => {
    const { load } = await show()
    expect(load).toHaveBeenCalledWith(target, expect.any(AbortSignal))
    expect(screen.getByRole('dialog', { name: 'Paper trade NIFTY 25050 CE' })).toBeInTheDocument()
    expect(screen.getByTestId('ticket-ltp')).toHaveTextContent('81.00') // the socket's, not 80
    expect(screen.getByTestId('trade-ticket')).toHaveTextContent('₹5,260')
    expect(box('Target')).toHaveValue(104)
    expect(box('Stop')).toHaveValue(68)
    expect(screen.getByTestId('ticket-levels-note')).toHaveTextContent(
      'worked out again at the fill',
    )
  })

  it('opens with the signal rule left to the server when nothing was typed', async () => {
    const { open, onOpened, onClose } = await show()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
      await Promise.resolve()
    })
    expect(open).toHaveBeenCalledWith(target, { quoted: 81, target: null, stop: null })
    expect(onOpened).toHaveBeenCalledWith(expect.objectContaining({ manual: true }))
    expect(onClose).toHaveBeenCalled()
  })

  it('sends typed levels as typed', async () => {
    const { open } = await show()
    fireEvent.change(box('Target'), { target: { value: '120' } })
    expect(screen.getByTestId('ticket-levels-note')).toHaveTextContent('the other set at the fill')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
      await Promise.resolve()
    })
    expect(open).toHaveBeenCalledWith(target, { quoted: 81, target: 120, stop: null })
  })

  it('shows a refusal and will not open', async () => {
    await show({ refusal: 'no new trades after 15:00' })
    expect(screen.getByTestId('ticket-refusal')).toHaveTextContent(
      'Cannot open now: no new trades after 15:00',
    )
    expect(screen.getByRole('button', { name: 'Open paper trade' })).toBeDisabled()
  })

  it('reports the server refusing the open and stays open', async () => {
    const { open, onClose } = await show()
    open.mockRejectedValueOnce(new Error('the target 70 must be above the price 81'))
    fireEvent.change(box('Target'), { target: { value: '70' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
      await Promise.resolve()
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Not opened: the target 70 must be above the price 81',
    )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('refuses a box that is not a number without asking the server', async () => {
    const { open } = await show()
    fireEvent.change(box('Stop'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
    expect(screen.getByRole('alert')).toHaveTextContent('enter a number')
    expect(open).not.toHaveBeenCalled()
  })

  it('closes on Escape, Cancel and the backdrop', async () => {
    const { onClose } = await show()
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getByTestId('ticket-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it('says why a ticket could not be loaded', async () => {
    const load = vi.fn().mockRejectedValue(new Error('no such contract to trade here'))
    render(
      <TradeTicket target={target} ltp={null} onClose={vi.fn()} onOpened={vi.fn()} load={load} />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('no such contract to trade here')
  })

  it('names a future by its side', async () => {
    const load = vi.fn().mockResolvedValue({ ...ticket, index: 'GOLD', direction: 'SELL_FUT' })
    render(
      <TradeTicket
        target={{ index: 'GOLD', direction: 'SELL_FUT', strike: null }}
        ltp={135_000}
        onClose={vi.fn()}
        onOpened={vi.fn()}
        load={load}
      />,
    )
    expect(
      await screen.findByRole('dialog', { name: 'Paper trade GOLD FUT short' }),
    ).toHaveTextContent('SELL')
    expect(screen.getByRole('spinbutton', { name: 'Target' }).closest('label')).toHaveAttribute(
      'title',
      'below the price',
    )
  })
})

describe('TradeTicket lots for a future (E28)', () => {
  const mini: TicketTarget = {
    index: 'GOLD',
    direction: 'BUY_FUT',
    strike: null,
    contract: 'GOLDM',
  }
  const futureTicket: TicketOut = {
    ...ticket,
    index: 'GOLD',
    direction: 'BUY_FUT',
    trading_symbol: 'GOLDM FUT 04 DEC 26',
    expiry: '2026-12-04',
    strike: 0,
    lots: 3,
    qty: 30,
  }

  async function showFuture() {
    const load = vi.fn((t: TicketTarget) =>
      Promise.resolve({ ...futureTicket, lots: t.lots ?? 3, qty: (t.lots ?? 3) * 10 }),
    )
    const open = vi.fn().mockResolvedValue({ ...trade, manual: true })
    render(
      <TradeTicket
        target={mini}
        ltp={135_000}
        onClose={vi.fn()}
        onOpened={vi.fn()}
        load={load}
        open={open}
      />,
    )
    await screen.findByText('GOLDM FUT 04 DEC 26 · exp 04/12/2026')
    return { load, open }
  }

  it('names the mini and starts from the contract default lots', async () => {
    const { load } = await showFuture()
    expect(screen.getByRole('dialog', { name: 'Paper trade GOLDM FUT long' })).toBeInTheDocument()
    expect(box('Lots')).toHaveValue(3)
    expect(screen.getByText('3 lots · 30')).toBeInTheDocument()
    expect(load).toHaveBeenCalledWith(mini, expect.any(AbortSignal))
  })

  it('asks the server again for typed lots and opens with them', async () => {
    const { load, open } = await showFuture()
    fireEvent.change(box('Lots'), { target: { value: '5' } })
    expect(await screen.findByText('5 lots · 50')).toBeInTheDocument()
    expect(load).toHaveBeenLastCalledWith({ ...mini, lots: 5 }, expect.any(AbortSignal))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
      await Promise.resolve()
    })
    expect(open).toHaveBeenCalledWith({ ...mini, lots: 5 }, expect.anything())
  })

  it('will not open with lots that are not a whole number from 1 to 100', async () => {
    const { load, open } = await showFuture()
    const calls = load.mock.calls.length
    fireEvent.change(box('Lots'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open paper trade' }))
    expect(screen.getByRole('alert')).toHaveTextContent('lots must be a whole number from 1 to 100')
    expect(open).not.toHaveBeenCalled()
    expect(load.mock.calls.length).toBe(calls) // not asked again for a bad number
  })

  it('has no lots box for an option', async () => {
    await show()
    expect(screen.queryByRole('spinbutton', { name: 'Lots' })).not.toBeInTheDocument()
  })
})
