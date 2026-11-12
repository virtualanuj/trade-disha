import { useEffect, useMemo, useState } from 'react'

import { MarketSocket } from './api/ws'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { IndexTiles } from './components/IndexTiles/IndexTiles'
import { TopBar } from './components/TopBar/TopBar'
import { useNow } from './lib/useNow'
import { useMarketStore } from './state/store'
import { useTheme } from './theme/useTheme'

function useDebugFlag(): [boolean, () => void] {
  const [debug, setDebug] = useState(() => new URLSearchParams(location.search).has('debug'))
  return [
    debug,
    () => {
      setDebug((d) => !d)
    },
  ]
}

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [debug, toggleDebug] = useDebugFlag()
  const now = useNow(500)

  const ws = useMarketStore((s) => s.ws)
  const health = useMarketStore((s) => s.health)
  const instruments = useMarketStore((s) => s.instruments)
  const prices = useMarketStore((s) => s.prices)

  useEffect(() => {
    const socket = new MarketSocket()
    socket.start()
    return () => {
      socket.stop()
    }
  }, [])

  const lastTickTs = useMemo(() => {
    let latest: number | null = null
    for (const p of Object.values(prices)) {
      for (const ts of [p.spot_ts, p.fut_ts]) {
        if (ts != null && (latest == null || ts > latest)) latest = ts
      }
    }
    return latest
  }, [prices])

  return (
    <div className="flex h-full flex-col">
      <TopBar
        health={health}
        ws={ws}
        now={now}
        lastTickTs={lastTickTs}
        theme={theme}
        onToggleTheme={toggleTheme}
        debug={debug}
        onToggleDebug={toggleDebug}
      />
      <main className="flex flex-1">
        <section className="flex flex-1 flex-col gap-4 p-4">
          <IndexTiles instruments={instruments} prices={prices} />
          <p className="text-fg-muted">
            Milestone 1: live feed. Chart, market view and signals follow in Milestones 3 and 4.
          </p>
        </section>
        <aside className="w-[420px] border-l border-border bg-bg-elev p-4">
          <h2 className="text-sm font-semibold text-fg-muted">Option chain</h2>
          <p className="mt-2 text-fg-muted">Arrives in Milestone 2.</p>
        </aside>
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
