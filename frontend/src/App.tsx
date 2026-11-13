import { useEffect, useMemo, useState } from 'react'

import { MarketSocket } from './api/ws'
import { BiasMeter } from './components/BiasMeter/BiasMeter'
import { ConfigControl } from './components/ConfigControl/ConfigControl'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { EvidenceTable } from './components/EvidenceTable/EvidenceTable'
import { IndexTabs } from './components/IndexTabs/IndexTabs'
import { IndexTiles } from './components/IndexTiles/IndexTiles'
import { OptionChain } from './components/OptionChain/OptionChain'
import { PriceChart } from './components/PriceChart/PriceChart'
import { SignalCard } from './components/SignalCard/SignalCard'
import { SignalHistory } from './components/SignalHistory/SignalHistory'
import { TopBar } from './components/TopBar/TopBar'
import { useNow } from './lib/useNow'
import { useMarketStore } from './state/store'
import { useTheme } from './theme/useTheme'

const EMPTY: never[] = []

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
  const candles = useMarketStore((s) => s.candles[s.selectedIndex]) ?? EMPTY
  const overlays = useMarketStore((s) => s.overlays[s.selectedIndex]) ?? EMPTY
  const bias = useMarketStore((s) => s.bias[s.selectedIndex])
  const signal = useMarketStore((s) => s.signals[s.selectedIndex])
  const gate = useMarketStore((s) => s.gates[s.selectedIndex])
  const signalHistory = useMarketStore((s) => s.signalHistory)
  const parameters = useMarketStore((s) => s.parameters)
  const parametersEffectiveFrom = useMarketStore((s) => s.parametersEffectiveFrom)
  const applyParameters = useMarketStore((s) => s.applyParameters)

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

  const markers = useMemo(
    () => signalHistory.filter((s) => s.index === selected),
    [signalHistory, selected],
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
        configControl={
          <ConfigControl
            parameters={parameters}
            effectiveFrom={parametersEffectiveFrom}
            onReloaded={applyParameters}
          />
        }
      />
      <main className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4">
          <IndexTabs
            indices={instruments.map((i) => i.index)}
            selected={selected}
            onSelect={selectIndex}
          />
          <IndexTiles instruments={selectedInstruments} prices={prices} />
          <div className="grid gap-3 lg:grid-cols-2">
            <BiasMeter bias={bias} />
            <SignalCard signal={signal} gate={gate} now={now} />
          </div>
          <PriceChart
            candles={candles}
            overlays={overlays}
            signals={markers}
            dataKey={selected}
            theme={theme}
          />
          <EvidenceTable bias={bias} />
          <SignalHistory signals={signalHistory} index={selected} />
        </section>
        <aside className="flex w-[640px] shrink-0 flex-col border-l border-border bg-bg-elev p-4">
          <OptionChain chain={chains[selected]} />
        </aside>
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
