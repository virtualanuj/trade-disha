import { render, screen } from '@testing-library/react'

import type { BankOut } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { Bank } from './Bank'

const opened = Date.UTC(2026, 10, 20, 4, 0) // 20/11/2026 09:30 IST
const bank: BankOut = {
  opening_balance: 2_500_000,
  opened_ts: opened,
  deposited: 500_000,
  withdrawn: 0,
  realised: 12_500,
  balance: 2_512_500,
  blocked: 1_353_300,
  available: 1_159_200,
  open_trades: 1,
  ledger: [
    {
      id: 1,
      ts: opened,
      kind: 'OPEN',
      amount: 2_000_000,
      opening_balance: 2_000_000,
      config_version: 1,
    },
    {
      id: 2,
      ts: opened + 3_600_000,
      kind: 'DEPOSIT',
      amount: 500_000,
      opening_balance: 2_500_000,
      config_version: 4,
    },
  ],
}

describe('Bank', () => {
  it('shows balance, blocked, available and P&L since the bank opened', () => {
    render(<Bank bank={bank} openTrades={[trade, { ...trade, id: 't9', live_net: -90 }]} />)
    expect(screen.getByTestId('bank-balance')).toHaveTextContent('₹25,12,500')
    expect(screen.getByTestId('bank-blocked')).toHaveTextContent('₹13,53,300')
    expect(screen.getByTestId('bank-available')).toHaveTextContent('₹11,59,200')
    expect(screen.getByTestId('bank-unrealised')).toHaveTextContent('+₹500')
    expect(screen.getByTestId('bank-realised')).toHaveTextContent('+₹12,500')
    expect(screen.getByTestId('bank')).toHaveTextContent('since 20/11/2026')
    expect(screen.getByTestId('bank-available')).not.toHaveClass('text-bear')
  })

  it('marks the available money red when nothing is left to trade with', () => {
    render(<Bank bank={{ ...bank, balance: -40_000, available: -40_000, blocked: 0 }} />)
    expect(screen.getByTestId('bank-available')).toHaveTextContent('−₹40,000')
    expect(screen.getByTestId('bank-available')).toHaveClass('text-bear')
    expect(screen.queryByTestId('bank-unrealised')).toBeNull()
  })

  it('says so before the first hello', () => {
    render(<Bank bank={null} />)
    expect(screen.getByTestId('bank')).toHaveTextContent('Paper bank: waiting for the server')
  })

  it('lists the cash moves when asked, and only then', () => {
    const { rerender } = render(<Bank bank={bank} />)
    expect(screen.queryByTestId('bank-ledger')).toBeNull()
    rerender(<Bank bank={bank} showLedger />)
    const rows = screen.getAllByTestId('bank-ledger-entry')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('20/11/2026 09:30')
    expect(rows[0]).toHaveTextContent('Opening deposit')
    expect(rows[0]).toHaveTextContent('₹20,00,000')
    expect(rows[1]).toHaveTextContent('10:30')
    expect(rows[1]).toHaveTextContent('Deposit')
    expect(rows[1]).toHaveTextContent('+₹5,00,000')
  })

  it('shows a withdrawal as money out', () => {
    const out = {
      ...bank,
      ledger: [
        ...bank.ledger,
        {
          id: 3,
          ts: opened + 7_200_000,
          kind: 'WITHDRAW' as const,
          amount: 300_000,
          opening_balance: 2_200_000,
          config_version: 5,
        },
      ],
    }
    render(<Bank bank={out} showLedger />)
    const rows = screen.getAllByTestId('bank-ledger-entry')
    expect(rows[2]).toHaveTextContent('Withdrawal')
    expect(rows[2]).toHaveTextContent('−₹3,00,000')
  })
})
