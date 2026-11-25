/** The pages, kept in the URL hash so reload and the back button work. */
export const VIEWS = ['dashboard', 'journal', 'trades'] as const
export type View = (typeof VIEWS)[number]

export const VIEW_LABEL: Record<View, string> = {
  dashboard: 'Dashboard',
  journal: 'Journal',
  trades: 'Trades',
}

/** "#journal" → journal; anything unknown is the dashboard. */
export function viewFromHash(hash: string): View {
  const name = hash.replace(/^#/, '')
  return name !== 'dashboard' && (VIEWS as readonly string[]).includes(name)
    ? (name as View)
    : 'dashboard'
}

/** The hash for a page; the dashboard has none. */
export function hashFor(view: View): string {
  return view === 'dashboard' ? '' : view
}
