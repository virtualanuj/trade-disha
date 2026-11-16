import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { openPaperTrade } from './api/client'
import type { SignalOut } from './api/types'
import { MarketSocket } from './api/ws'
import { BiasMeter } from './components/BiasMeter/BiasMeter'
import { BullionCards, MetalSwitch } from './components/BullionView/BullionView'
import { ConfigControl } from './components/ConfigControl/ConfigControl'
import { DataPanel } from './components/DataPanel/DataPanel'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { Divider } from './components/Divider/Divider'
import { EvidenceTable } from './components/EvidenceTable/EvidenceTable'
import { FlowLine } from './components/FlowLine/FlowLine'
import { IndexTabs } from './components/IndexTabs/IndexTabs'
import { IndexTiles } from './components/IndexTiles/IndexTiles'
import { Journal } from './components/Journal/Journal'
import { OpenTrades } from './components/OpenTrades/OpenTrades'
import { OptionChain } from './components/OptionChain/OptionChain'
import { PanelFrame } from './components/PanelFrame/PanelFrame'
import { PriceChart } from './components/PriceChart/PriceChart'
import { SignalCard } from './components/SignalCard/SignalCard'
import { SidePanel } from './components/SidePanel/SidePanel'
import { SignalHistory } from './components/SignalHistory/SignalHistory'
import { currentBanner } from './components/StatusBanner/banner'
import { StatusBanner } from './components/StatusBanner/StatusBanner'
import { TopBar } from './components/TopBar/TopBar'
import { clampLayout, DEFAULT_LAYOUT, LIMITS, parseLayout } from './lib/layout'
import type { Layout } from './lib/layout'
import { unitOf, useOpenOnNew, usePanels } from './lib/panels'
import type { PanelId, UnitId } from './lib/panels'
import {
  biasSummary,
  chainSummary,
  chartSummary,
  evidenceSummary,
  historySummary,
  signalSummary,
  tilesSummary,
  bullionSummary,
  tradesSummary,
} from './lib/panelSummary'
import { useNow } from './lib/useNow'
import { isLong } from './lib/direction'
import { useBullionMetal } from './lib/useBullionMetal'
import { usePref } from './lib/usePref'
import { BULLION_TAB, useMarketStore } from './state/store'
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
  const panels = usePanels()
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
  const indexCandles = useMarketStore((s) => s.candles[s.selectedIndex]) ?? EMPTY
  const indexOverlays = useMarketStore((s) => s.overlays[s.selectedIndex]) ?? EMPTY
  const indexFutCandles = useMarketStore((s) => s.futCandles[s.selectedIndex]) ?? EMPTY
  const flow = useMarketStore((s) => s.flow[s.selectedIndex])
  const signalHistory = useMarketStore((s) => s.signalHistory)
  const biasByIndex = useMarketStore((s) => s.bias)
  const signalByIndex = useMarketStore((s) => s.signals)
  const gateByIndex = useMarketStore((s) => s.gates)
  const parameters = useMarketStore((s) => s.parameters)
  const parametersEffectiveFrom = useMarketStore((s) => s.parametersEffectiveFrom)
  const applyParameters = useMarketStore((s) => s.applyParameters)
  const trades = useMarketStore((s) => s.trades)
  const stats = useMarketStore((s) => s.stats)
  const bullion = useMarketStore((s) => s.bullion)
  const bullionCandles = useMarketStore((s) => s.bullionCandles)
  const bullionOverlays = useMarketStore((s) => s.bullionOverlays)
  const onBullion = selected === BULLION_TAB
  const metalNames = useMemo(() => (bullion?.metals ?? []).map((m) => m.metal), [bullion])
  const [metal, setMetal] = useBullionMetal(metalNames)
  /** what the panels show: the selected index, or on BULLION the selected metal (spec §9a) */
  const focus = onBullion ? metal : selected
  const candles = onBullion ? (bullionCandles[metal] ?? EMPTY) : indexCandles
  const overlays = onBullion ? (bullionOverlays[metal] ?? EMPTY) : indexOverlays
  /** net volume comes from a traded future: the index's, or the metal itself */
  const netVolume = onBullion ? candles : indexFutCandles
  const bias = biasByIndex[focus]
  const signal = signalByIndex[focus]
  const gate = gateByIndex[focus]
  const tabs = useMemo(() => {
    const indices = instruments.map((i) => i.index)
    return bullion?.metals.length ? [...indices, BULLION_TAB] : indices
  }, [instruments, bullion])
  const applyTrades = useMarketStore((s) => s.applyTrades)

  const openTrades = useMemo(() => trades.filter((t) => t.status === 'open'), [trades])
  const openOnIndex = useMemo(
    () => openTrades.filter((t) => t.index === focus),
    [openTrades, focus],
  )
  /** changes whenever a trade opens or closes, so the journal refetches */
  const journalRevision = useMemo(
    () => trades.reduce((n, t) => n + (t.status === 'closed' ? 2 : 1), 0),
    [trades],
  )
  const feedLive = ws === 'open' && health?.feed_live === true
  const banner = useMemo(() => currentBanner(health, ws, onBullion), [health, ws, onBullion])
  /** last-known data is dimmed so it is never mistaken for live */
  const staleCls = banner?.stale ? 'opacity-60' : ''
  const paperTrade = useCallback(
    async (s: SignalOut) => {
      applyTrades([await openPaperTrade(s.id)])
    },
    [applyTrades],
  )

  /** bullion trades on MCX prices and hours, not the index feed (spec §9a) */
  const bullionLive = ws === 'open' && health?.bullion?.status === 'live'
  const tradeLive = onBullion ? bullionLive : feedLive
  const notLive = onBullion
    ? 'Bullion prices not live: no price to trade at'
    : 'Feed not live: no price to trade at'

  const { open: openPanel } = panels
  /** the props that give a panel its minimise control and, in the left column, its move buttons */
  const frame = (id: PanelId) => {
    const step = (dir: -1 | 1) =>
      panels.canMove(id, dir)
        ? () => {
            panels.move(id, dir)
          }
        : null
    return {
      id,
      minimised: panels.minimised[id],
      onToggle: () => {
        panels.toggleMinimise(id)
      },
      move: unitOf(id) ? { up: step(-1), down: step(1) } : undefined,
      moveLabel: unitOf(id) === 'view' ? 'market view and signal' : undefined,
    }
  }
  // a new signal or a newly opened trade brings its minimised panel back, once
  const openSignalPanel = useCallback(() => {
    openPanel('signal')
  }, [openPanel])
  const openTradesPanel = useCallback(() => {
    openPanel('trades')
  }, [openPanel])
  const signalIds = useMemo(() => (signal?.status === 'active' ? [signal.id] : []), [signal])
  const openTradeIds = useMemo(() => openOnIndex.map((t) => t.id), [openOnIndex])
  useOpenOnNew(signalIds, openSignalPanel)
  useOpenOnNew(openTradeIds, openTradesPanel)

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
  /** on the BULLION tab the feed pill measures MCX ticks, which run to 23:30 */
  const lastBullionTs = useMemo(() => {
    const stamps = (bullion?.metals ?? []).map((m) => m.updated_ts).filter((t) => t != null)
    return stamps.length ? Math.max(...stamps) : null
  }, [bullion])

  const selectedInstruments = useMemo(
    () => instruments.filter((i) => i.index === selected),
    [instruments, selected],
  )

  const markers = useMemo(
    () => signalHistory.filter((s) => s.index === focus && !s.shadow),
    [signalHistory, focus],
  )

  /** the left column's units; drawn in the order the trader has put them in */
  const units: Record<UnitId, ReactNode> = {
    tiles: onBullion ? (
      <PanelFrame {...frame('tiles')} title="Bullion" summary={bullionSummary(bullion)}>
        <BullionCards bullion={bullion} />
      </PanelFrame>
    ) : (
      <PanelFrame
        {...frame('tiles')}
        title="Index"
        summary={tilesSummary(prices[selected], stats[selected])}
      >
        <IndexTiles instruments={selectedInstruments} prices={prices} stats={stats} />
      </PanelFrame>
    ),
    view: (
      <div
        className={`grid gap-3 ${
          panels.minimised.bias || panels.minimised.signal ? '' : 'lg:grid-cols-2'
        }`}
      >
        <PanelFrame {...frame('bias')} title="Market view" summary={biasSummary(bias)}>
          <BiasMeter bias={bias} />
        </PanelFrame>
        <PanelFrame
          {...frame('signal')}
          title="Signal"
          summary={signalSummary(signal, now)}
          border={
            signal
              ? isLong(signal.direction)
                ? 'border-bull/60'
                : 'border-bear/60'
              : 'border-dashed border-border'
          }
        >
          <SignalCard
            signal={signal}
            gate={gate}
            now={now}
            openTrades={openOnIndex}
            blocked={tradeLive ? undefined : notLive}
            onPaperTrade={paperTrade}
          />
        </PanelFrame>
      </div>
    ),
    chart: (
      <>
        <PanelFrame
          {...frame('chart')}
          title="Price chart"
          summary={chartSummary(candles)}
          keepMounted
          bodyClassName=""
        >
          <PriceChart
            candles={candles}
            overlays={overlays}
            signals={markers}
            netVolume={netVolume}
            dataKey={onBullion ? `bullion-${metal}` : selected}
            theme={theme}
            height={layout.chartHeight}
          />
        </PanelFrame>
        {panels.minimised.chart ? null : (
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
        )}
      </>
    ),
    evidence: (
      <PanelFrame {...frame('evidence')} title="Evidence" summary={evidenceSummary(bias)}>
        <EvidenceTable bias={bias} />
        {onBullion ? null : <FlowLine flow={flow} />}
      </PanelFrame>
    ),
    trades: (
      <PanelFrame
        {...frame('trades')}
        title="Open paper trades"
        summary={tradesSummary(openOnIndex)}
        border={openOnIndex.length > 0 ? 'border-accent/50' : 'border-border'}
      >
        <OpenTrades trades={openOnIndex} now={now} canClose={tradeLive} />
      </PanelFrame>
    ),
    history: (
      <PanelFrame
        {...frame('history')}
        title="Signals today"
        summary={historySummary(signalHistory, focus)}
      >
        <SignalHistory signals={signalHistory} index={focus} />
      </PanelFrame>
    ),
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar
        health={health}
        ws={ws}
        now={now}
        lastTickTs={onBullion ? lastBullionTs : lastTickTs}
        bullionTab={onBullion}
        theme={theme}
        onToggleTheme={toggleTheme}
        debug={debug}
        onToggleDebug={toggleDebug}
        view={view}
        onToggleView={toggleView}
        openTradeCount={openTrades.length}
        panelsChanged={panels.changed}
        onRestorePanels={panels.restoreAll}
        dataControl={<DataPanel />}
        configControl={
          <ConfigControl
            parameters={parameters}
            effectiveFrom={parametersEffectiveFrom}
            onSaved={applyParameters}
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
              <IndexTabs indices={tabs} selected={selected} onSelect={selectIndex} />
              {onBullion && metalNames.length > 0 ? (
                <MetalSwitch names={metalNames} metal={metal} onSelect={setMetal} />
              ) : null}
              {panels.order.map((unit) => (
                <Fragment key={unit}>{units[unit]}</Fragment>
              ))}
            </section>
            {onBullion || panels.minimised.chain ? null : (
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
            )}
            {onBullion ? null : (
              <SidePanel
                name="option chain"
                open={!panels.minimised.chain}
                onToggle={() => {
                  panels.toggleMinimise('chain')
                }}
                width={layout.chainWidth}
                className={staleCls}
              >
                <PanelFrame
                  {...frame('chain')}
                  title="Option chain"
                  summary={chainSummary(chains[selected])}
                  fill
                >
                  <OptionChain chain={chains[selected]} />
                </PanelFrame>
              </SidePanel>
            )}
          </>
        )}
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
