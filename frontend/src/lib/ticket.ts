import type { TicketTarget } from '../api/types'

/** A number typed by the trader, or null when the box does not hold one. */
export function parseLevel(text: string): number | null {
  const v = Number(text.trim())
  return text.trim() === '' || !Number.isFinite(v) ? null : v
}

/** Lots typed on a ticket: a whole number from 1 to 100, or null when the box holds none. */
export function parseLots(text: string): number | null {
  const v = Number(text.trim())
  return Number.isInteger(v) && v >= 1 && v <= 100 ? v : null
}

/** The ticket an option-chain cell opens: a call or a put at that strike (E23). */
export function chainTicket(index: string, strike: number, side: 'ce' | 'pe'): TicketTarget {
  return { index, direction: side === 'ce' ? 'BUY_CE' : 'BUY_PE', strike }
}
