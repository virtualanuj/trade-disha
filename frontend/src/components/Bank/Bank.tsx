import type { BankLedgerEntryOut, BankOut, PaperTradeOut } from '../../api/types'
import { fmtDate, fmtIstTime, fmtMoney, fmtRupees, pnlColour } from '../../lib/format'

const KIND_TEXT: Record<BankLedgerEntryOut['kind'], string> = {
  OPEN: 'Opening deposit',
  DEPOSIT: 'Deposit',
  WITHDRAW: 'Withdrawal',
}

interface Props {
  bank: BankOut | null
  /** every open trade, any market: their live P&L is the unrealised figure */
  openTrades?: PaperTradeOut[]
  /** list the cash moves (the opening deposit, then each deposit or withdrawal) */
  showLedger?: boolean
}

/** The paper bank that funds paper trades (spec §10.5): one account for every market. */
export function Bank({ bank, openTrades, showLedger = false }: Props) {
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
  const strip = (
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
  if (!showLedger) return strip
  return (
    <div className="flex flex-col gap-2">
      {strip}
      <table className="self-start font-mono text-xs" data-testid="bank-ledger">
        <tbody>
          {bank.ledger.map((e) => (
            <tr key={e.id} data-testid="bank-ledger-entry">
              <td className="pr-4 text-fg-muted">
                {fmtDate(e.ts)} {fmtIstTime(e.ts)}
              </td>
              <td className="pr-4 font-sans">{KIND_TEXT[e.kind]}</td>
              <td
                className={`pr-4 text-right ${e.kind === 'WITHDRAW' ? 'text-bear' : 'text-bull'}`}
              >
                {e.kind === 'OPEN'
                  ? fmtRupees(e.amount)
                  : fmtMoney(e.kind === 'WITHDRAW' ? -e.amount : e.amount)}
              </td>
              <td className="text-fg-muted">
                <span className="font-sans">cash in </span>
                {fmtRupees(e.opening_balance)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
