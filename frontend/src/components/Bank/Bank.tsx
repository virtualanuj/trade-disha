import type { BankOut, PaperTradeOut } from '../../api/types'
import { fmtDate, fmtMoney, fmtRupees, pnlColour } from '../../lib/format'

interface Props {
  bank: BankOut | null
  /** every open trade, any market: their live P&L is the unrealised figure */
  openTrades?: PaperTradeOut[]
}

/**
 * The paper bank that funds paper trades (spec §10.5): one account for every market. Its
 * statement, every cash move, is the Journal page.
 */
export function Bank({ bank, openTrades }: Props) {
  if (bank === null) {
    return (
      <div className="text-xs text-fg-muted" data-testid="bank">
        Paper bank: waiting for the server
      </div>
    )
  }
  const unrealised = openTrades?.length
    ? openTrades.reduce((n, t) => n + (t.live_net ?? 0), 0)
    : null
  const empty = bank.available <= 0
  return (
    <div
      className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs"
      data-testid="bank"
      title={`Cash in: ${fmtRupees(bank.opening_balance)} (change it in Config: more is a deposit, less a withdrawal). A trade blocks its premium (options) or margin (futures) plus cost, and settles its net P&L when it closes.`}
    >
      <span className="text-[10px] uppercase tracking-wide text-fg-muted">Paper bank</span>
      <span>
        <span className="text-fg-muted">Balance </span>
        <span className="font-mono" data-testid="bank-balance">
          {fmtRupees(bank.balance)}
        </span>
      </span>
      <span>
        <span className="text-fg-muted">Blocked </span>
        <span className="font-mono" data-testid="bank-blocked">
          {fmtRupees(bank.blocked)}
        </span>
      </span>
      <span>
        <span className="text-fg-muted">Available </span>
        <span
          className={`font-mono ${empty ? 'text-bear' : ''}`}
          data-testid="bank-available"
          title={empty ? 'Nothing left to trade with: no paper trade can open.' : undefined}
        >
          {fmtRupees(bank.available)}
        </span>
      </span>
      {unrealised !== null ? (
        <span>
          <span className="text-fg-muted">Unrealised </span>
          <span className={`font-mono ${pnlColour(unrealised)}`} data-testid="bank-unrealised">
            {fmtMoney(unrealised)}
          </span>
        </span>
      ) : null}
      <span>
        <span className="text-fg-muted">P&amp;L since {fmtDate(bank.opened_ts)} </span>
        <span className={`font-mono ${pnlColour(bank.realised)}`} data-testid="bank-realised">
          {fmtMoney(bank.realised)}
        </span>
      </span>
    </div>
  )
}
