import { useCallback, useEffect, useMemo, useState } from 'react'

import { openPaperTrade } from './api/client'
import type { SignalOut } from './api/types'
import { MarketSocket } from './api/ws'
import { BiasMeter } from './components/BiasMeter/BiasMeter'
import { ConfigControl } from './components/ConfigControl/ConfigControl'
import { DataPanel } from './components/DataPanel/DataPanel'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { Divider } from './components/Divider/Divider'
import { EvidenceTable } from './components/EvidenceTable/EvidenceTable'
import { IndexTabs } from './components/IndexTabs/IndexTabs'
import { IndexTiles } from './components/IndexTiles/IndexTiles'
import { Journal } from './components/Journal/Journal'
import { OpenTrades } from './components/OpenTrades/OpenTrades'
import { OptionChain } from './components/OptionChain/OptionChain'
import { PriceChart } from './components/PriceChart/PriceChart'
import { SignalCard } from './components/SignalCard/SignalCard'
import { SidePanel } from './components/SidePanel/SidePanel'
import { SignalHistory } from './components/SignalHistory/SignalHistory'
import { currentBanner } from './components/StatusBanner/banner'
import { StatusBanner } from './components/StatusBanner/StatusBanner'
import { TopBar } from './components/TopBar/TopBar'
import { clampLayout, DEFAULT_LAYOUT, LIMITS, parseLayout } from './lib/layout'
import type { Layout } from './lib/layout'
import { useNow } from './lib/useNow'
import { usePref } from './lib/usePref'
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

type View = 'dashboard' | 'journal'

const LAYOUT_KEY = 'tradedisha.layout'
const CHAIN_OPEN_KEY = 'tradedisha.chainOpen'
/** shown unless the trader has hidden it */
const notFalse = (v: unknown): boolean => v !== false

function useWindowWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth)
  useEffect(() => {
    const sync = () => {
      setWidth(window.innerWidth)
    }
    window.addEventListener('resize', sync)
    return () => {
      window.removeEventListener('resize', sync)
    }
  }, [])
  return width
}

/** Panel sizes: remembered in this browser, and always clamped to fit the window. */
function useLayout(): [Layout, (change: Partial<Layout>) => void] {
  const [stored, store] = usePref(LAYOUT_KEY, parseLayout)
  const width = useWindowWidth()
  const layout = useMemo(() => clampLayout(stored, width), [stored, width])
  const update = useCallback(
    (change: Partial<Layout>) => {
      store(clampLayout({ ...layout, ...change }, width))
    },
    [layout, store, width],
  )
  return [layout, update]
}

function viewFromHash(): View {
  return location.hash === '#journal' ? 'journal' : 'dashboard'
}

/** The page shown, kept in the URL hash so reload and the back button work. */
function useView(): [View, () => void] {
  const [view, setView] = useState<View>(viewFromHash)
  useEffect(() => {
    const sync = () => {
      setView(viewFromHash())
    }
    window.addEventListener('hashchange', sync)
    return () => {
      window.removeEventListener('hashchange', sync)
    }
  }, [])
  return [
    view,
    () => {
      location.hash = view === 'journal' ? '' : 'journal'
    },
  ]
}

export default function App() {
  const [view, toggleView] = useView()
  const [layout, setLayout] = useLayout()
  const [chainOpen, setChainOpen] = usePref(CHAIN_OPEN_KEY, notFalse)
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
  const trades = useMarketStore((s) => s.trades)
  const stats = useMarketStore((s) => s.stats)
  const applyTrades = useMarketStore((s) => s.applyTrades)

  const openTrades = useMemo(() => trades.filter((t) => t.status === 'open'), [trades])
  const openOnIndex = useMemo(
    () => openTrades.filter((t) => t.index === selected),
    [openTrades, selected],
  )
  /** changes whenever a trade opens or closes, so the journal refetches */
  const journalRevision = useMemo(
    () => trades.reduce((n, t) => n + (t.status === 'closed' ? 2 : 1), 0),
    [trades],
  )
  const feedLive = ws === 'open' && health?.feed_live === true
  const banner = useMemo(() => currentBanner(health, ws), [health, ws])
  /** last-known data is dimmed so it is never mistaken for live */
  const staleCls = banner?.stale ? 'opacity-60' : ''
  const paperTrade = useCallback(
    async (s: SignalOut) => {
      applyTrades([await openPaperTrade(s.id)])
    },
    [applyTrades],
  )

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
        view={view}
        onToggleView={toggleView}
        openTradeCount={openTrades.length}
        dataControl={<DataPanel />}
        configControl={
          <ConfigControl
            parameters={parameters}
            effectiveFrom={parametersEffectiveFrom}
            onReloaded={applyParameters}
          />
        }
      />
      <StatusBanner banner={banner} />
      <main className="flex min-h-0 flex-1">
        {view === 'journal' ? (
          <Journal indices={instruments.map((i) => i.index)} revision={journalRevision} />
        ) : (
          <>
            <section
              className={`flex min-w-0 flex-1 flex-col gap-3 overflow-auto p-4 ${staleCls}`}
              data-stale={banner?.stale ? 'true' : undefined}
            >
              <IndexTabs
                indices={instruments.map((i) => i.index)}
                selected={selected}
                onSelect={selectIndex}
              />
              <IndexTiles instruments={selectedInstruments} prices={prices} stats={stats} />
              <div className="grid gap-3 lg:grid-cols-2">
                <BiasMeter bias={bias} />
                <SignalCard
                  signal={signal}
                  gate={gate}
                  now={now}
                  openTrades={openOnIndex}
                  blocked={feedLive ? undefined : 'Feed not live: no price to trade at'}
                  onPaperTrade={paperTrade}
                />
              </div>
              <OpenTrades trades={openOnIndex} now={now} canClose={feedLive} />
              <PriceChart
                candles={candles}
                overlays={overlays}
                signals={markers}
                dataKey={selected}
                theme={theme}
                height={layout.chartHeight}
              />
              <Divider
                orientation="horizontal"
                label="Chart height"
                value={layout.chartHeight}
                min={LIMITS.chartMin}
                max={LIMITS.chartMax}
                onDrag={(d) => {
                  setLayout({ chartHeight: layout.chartHeight + d })
                }}
                onReset={() => {
                  setLayout({ chartHeight: DEFAULT_LAYOUT.chartHeight })
                }}
              />
              <EvidenceTable bias={bias} />
              <SignalHistory signals={signalHistory} index={selected} />
            </section>
            {chainOpen ? (
              <Divider
                orientation="vertical"
                label="Option chain width"
                value={layout.chainWidth}
                min={LIMITS.chainMin}
                max={LIMITS.chainMax}
                onDrag={(d) => {
                  setLayout({ chainWidth: layout.chainWidth - d })
                }}
                onReset={() => {
                  setLayout({ chainWidth: DEFAULT_LAYOUT.chainWidth })
                }}
              />
            ) : null}
            <SidePanel
              name="option chain"
              open={chainOpen}
              onToggle={() => {
                setChainOpen(!chainOpen)
              }}
              width={layout.chainWidth}
              className={staleCls}
            >
              <OptionChain chain={chains[selected]} />
            </SidePanel>
          </>
        )}
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
