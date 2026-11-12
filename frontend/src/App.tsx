import { useEffect, useState } from 'react'

import { fetchHealth } from './api/client'
import { TopBar, type BackendState } from './components/TopBar/TopBar'
import { useTheme } from './theme/useTheme'

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [backend, setBackend] = useState<BackendState>({ kind: 'checking' })

  useEffect(() => {
    const ctrl = new AbortController()
    fetchHealth(ctrl.signal)
      .then((h) => {
        setBackend({ kind: 'up', version: h.version, milestone: h.milestone })
      })
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) {
          setBackend({ kind: 'down', error: e instanceof Error ? e.message : String(e) })
        }
      })
    return () => {
      ctrl.abort()
    }
  }, [])

  return (
    <div className="flex h-full flex-col">
      <TopBar backend={backend} theme={theme} onToggleTheme={toggleTheme} />
      <main className="flex flex-1">
        <section className="flex flex-1 flex-col gap-4 p-4">
          <h1 className="text-lg font-semibold">Dashboard</h1>
          <p className="text-fg-muted">
            Milestone 0 skeleton. Market view, chart, signals and evidence will appear here.
          </p>
        </section>
        <aside className="w-[420px] border-l border-border bg-bg-elev p-4">
          <h2 className="text-sm font-semibold text-fg-muted">Option chain</h2>
          <p className="mt-2 text-fg-muted">Arrives in Milestone 2.</p>
        </aside>
      </main>
    </div>
  )
}
