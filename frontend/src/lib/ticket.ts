import type { TicketTarget } from '../api/types'

/** A number typed by the trader, or null when the box does not hold one. */
export function parseLevel(text: string): number | null {
  const v = Number(text.trim())
  return text.trim() === '' || !Number.isFinite(v) ? null : v
}

/** The ticket an option-chain cell opens: a call or a put at that strike (E23). */
export function chainTicket(index: string, strike: number, side: 'ce' | 'pe'): TicketTarget {
  return { index, direction: side === 'ce' ? 'BUY_CE' : 'BUY_PE', strike }
}
