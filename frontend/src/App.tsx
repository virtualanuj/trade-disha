import { useEffect, useMemo, useState } from 'react'

import { MarketSocket } from './api/ws'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { IndexTabs } from './components/IndexTabs/IndexTabs'
import { IndexTiles } from './components/IndexTiles/IndexTiles'
import { OptionChain } from './components/OptionChain/OptionChain'
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
  const chains = useMarketStore((s) => s.chains)
  const selected = useMarketStore((s) => s.selectedIndex)
  const selectIndex = useMarketStore((s) => s.selectIndex)

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

  const selectedInstruments = useMemo(
    () => instruments.filter((i) => i.index === selected),
    [instruments, selected],
  )

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
      <main className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col gap-4 p-4">
          <IndexTabs
            indices={instruments.map((i) => i.index)}
            selected={selected}
            onSelect={selectIndex}
          />
          <IndexTiles instruments={selectedInstruments} prices={prices} />
          <p className="text-fg-muted">
            Milestone 2: option chain. Chart, market view and signals follow in Milestones 3 and 4.
          </p>
        </section>
        <aside className="flex w-[640px] shrink-0 flex-col border-l border-border bg-bg-elev p-4">
          <OptionChain chain={chains[selected]} />
        </aside>
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
