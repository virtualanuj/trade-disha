import { ETF_TAB } from '../state/store'

export interface Tab {
  id: string
  label: string
}

/** One exchange's tabs on the dashboard (E32). */
export interface TabGroup {
  exchange: 'NSE' | 'MCX'
  tabs: Tab[]
}

/**
 * NSE: the indices, then BULLION (the gold and silver ETFs) while there are ETFs. MCX: one
 * tab per metal loaded. A group with no tabs is left out.
 */
export function tabGroups(indices: string[], hasEtfs: boolean, metals: string[]): TabGroup[] {
  const nse: Tab[] = indices.map((i) => ({ id: i, label: i }))
  if (hasEtfs) nse.push({ id: ETF_TAB, label: 'BULLION' })
  const mcx: Tab[] = metals.map((m) => ({ id: m, label: m }))
  const groups: TabGroup[] = [
    { exchange: 'NSE', tabs: nse },
    { exchange: 'MCX', tabs: mcx },
  ]
  return groups.filter((g) => g.tabs.length > 0)
}

/** Every tab's id, in order: what the rates strip may open. */
export function tabIds(groups: TabGroup[]): string[] {
  return groups.flatMap((g) => g.tabs.map((t) => t.id))
}
