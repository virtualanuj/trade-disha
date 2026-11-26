import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'

import { logout, openPaperTrade } from './api/client'
import type { PaperTradeOut, SignalOut } from './api/types'
import { MarketSocket } from './api/ws'
import { MetalSwitch } from './components/BullionView/BullionView'
import { ConfigControl } from './components/ConfigControl/ConfigControl'
import { DataPanel } from './components/DataPanel/DataPanel'
import { DebugOverlay } from './components/DebugOverlay/DebugOverlay'
import { Divider } from './components/Divider/Divider'
import { IndexTabs } from './components/IndexTabs/IndexTabs'
import { Journal } from './components/Journal/Journal'
import {
  BiasPanel,
  BullionTilesPanel,
  ChainPanel,
  HistoryPanel,
  IndexTilesPanel,
  LiveBank,
  LiveRatesStrip,
  LiveTopBar,
  LiveTradeLog,
  NewsPanel,
  SignalPanel,
  TradesPanel,
} from './components/Live/Live'
import { PanelFrame } from './components/PanelFrame/PanelFrame'
import { PriceChart } from './components/PriceChart/PriceChart'
import { RightColumn } from './components/RightColumn/RightColumn'
import { currentBanner } from './components/StatusBanner/banner'
import { StatusBanner } from './components/StatusBanner/StatusBanner'
import { clampLayout, DEFAULT_LAYOUT, LIMITS, parseLayout } from './lib/layout'
import type { Layout } from './lib/layout'
import { tradeRevision } from './lib/marketViews'
import { unitOf, useOpenOnNew, usePanels } from './lib/panels'
import type { PanelId, UnitId } from './lib/panels'
import { chartSummary } from './lib/panelSummary'
import { useBullionMetal } from './lib/useBullionMetal'
import { useNewsSeen } from './lib/useNewsSeen'
import { usePref } from './lib/usePref'
import { hashFor, viewFromHash, type View } from './lib/view'
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

/** bullion trades are kept for these metals (`engine/paper.py:METALS`), loaded or not */
const METALS = ['GOLD', 'SILVER']

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

/** The page shown, kept in the URL hash so reload and the back button work. */
function useView(): [View, (view: View) => void] {
  const [view, setView] = useState<View>(() => viewFromHash(location.hash))
  useEffect(() => {
    const sync = () => {
      setView(viewFromHash(location.hash))
    }
    window.addEventListener('hashchange', sync)
    return () => {
      window.removeEventListener('hashchange', sync)
    }
  }, [])
  return [
    view,
    (next: View) => {
      location.hash = hashFor(next)
    },
  ]
}

/**
 * The page. It holds the layout, the panels' state and the slow-moving data; the panels
 * that show fast-moving data (prices, chains, bullion, flow, the clock) read it themselves
 * (`components/Live/`), so a frame re-renders the piece that shows it, not the whole page.
 */
export default function App() {
  const [view, showView] = useView()
  const [layout, setLayout] = useLayout()
  const panels = usePanels()
  const [theme, toggleTheme] = useTheme()
  const [debug, toggleDebug] = useDebugFlag()

  const ws = useMarketStore((s) => s.ws)
  const health = useMarketStore((s) => s.health)
  const instruments = useMarketStore((s) => s.instruments)
  const selected = useMarketStore((s) => s.selectedIndex)
  const selectIndex = useMarketStore((s) => s.selectIndex)
  const indexCandles = useMarketStore((s) => s.candles[s.selectedIndex]) ?? EMPTY
  const indexOverlays = useMarketStore((s) => s.overlays[s.selectedIndex]) ?? EMPTY
  const indexFutCandles = useMarketStore((s) => s.futCandles[s.selectedIndex]) ?? EMPTY
  const signalHistory = useMarketStore((s) => s.signalHistory)
  const parameters = useMarketStore((s) => s.parameters)
  const parametersEffectiveFrom = useMarketStore((s) => s.parametersEffectiveFrom)
  const applyParameters = useMarketStore((s) => s.applyParameters)
  const bullionCandles = useMarketStore((s) => s.bullionCandles)
  const bullionOverlays = useMarketStore((s) => s.bullionOverlays)
  const news = useMarketStore((s) => s.news)
  /** the metals' names only: the bullion snapshot itself changes with every MCX frame */
  const metalNames = useMarketStore(
    useShallow((s) => (s.bullion?.metals ?? []).map((m) => m.metal)),
  )
  /** changes whenever a trade opens or closes, so the journal refetches */
  const journalRevision = useMarketStore((s) => tradeRevision(s.trades))
  /** the headlines list is on screen: dots stay, and the newest is recorded as seen */
  const newsVisible = view === 'dashboard' && !panels.newsHidden && !panels.minimised.news
  const newsSeenTs = useNewsSeen(news, newsVisible)
  const onBullion = selected === BULLION_TAB
  const [metal, setMetal] = useBullionMetal(metalNames)
  /** what the Trades page filters by: every index, and the metals even before bullion loads */
  const tradeMarkets = useMemo(
    () => [...new Set([...instruments.map((i) => i.index), ...METALS, ...metalNames])],
    [instruments, metalNames],
  )
  /** what the panels show: the selected index, or on BULLION the selected metal (spec §9a) */
  const focus = onBullion ? metal : selected
  const candles = onBullion ? (bullionCandles[metal] ?? EMPTY) : indexCandles
  const overlays = onBullion ? (bullionOverlays[metal] ?? EMPTY) : indexOverlays
  /** net volume comes from a traded future: the index's, or the metal itself */
  const netVolume = onBullion ? candles : indexFutCandles
  const tabs = useMemo(() => {
    const indices = instruments.map((i) => i.index)
    return metalNames.length ? [...indices, BULLION_TAB] : indices
  }, [instruments, metalNames])
  const applyTrades = useMarketStore((s) => s.applyTrades)
  /** a click on the rates strip: that tab (and metal) on the dashboard */
  const openRate = useCallback(
    (tab: string, rateMetal: string | null) => {
      selectIndex(tab)
      if (rateMetal) setMetal(rateMetal)
      if (view !== 'dashboard') showView('dashboard')
    },
    [selectIndex, setMetal, view, showView],
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

  /** on the Trades page each open trade is judged by its own market's prices */
  const closeBlock = useCallback(
    (t: PaperTradeOut) =>
      METALS.includes(t.index)
        ? bullionLive
          ? null
          : 'Bullion prices not live: no price to close at'
        : feedLive
          ? null
          : 'Feed not live: no price to close at',
    [bullionLive, feedLive],
  )
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
    }
  }
  // a new signal or a newly opened trade brings its minimised panel back, once
  const openSignalPanel = useCallback(() => {
    openPanel('signal')
  }, [openPanel])
  const openTradesPanel = useCallback(() => {
    openPanel('trades')
  }, [openPanel])
  /** ids only: the signal and the trades themselves change every second while live */
  const activeSignalId = useMarketStore((s) => {
    const sig = s.signals[focus]
    return sig?.status === 'active' ? sig.id : null
  })
  const openTradeIds = useMarketStore(
    useShallow((s) =>
      s.trades.filter((t) => t.status === 'open' && t.index === focus).map((t) => t.id),
    ),
  )
  const signalIds = useMemo(() => (activeSignalId ? [activeSignalId] : []), [activeSignalId])
  useOpenOnNew(signalIds, openSignalPanel)
  useOpenOnNew(openTradeIds, openTradesPanel)

  useEffect(() => {
    const socket = new MarketSocket()
    socket.start()
    return () => {
      socket.stop()
    }
  }, [])

  const markers = useMemo(
    () => signalHistory.filter((s) => s.index === focus && !s.shadow),
    [signalHistory, focus],
  )

  /** the left column's units; drawn in the order the trader has put them in */
  const units: Record<UnitId, ReactNode> = {
    tiles: onBullion ? (
      <BullionTilesPanel frame={frame('tiles')} />
    ) : (
      <IndexTilesPanel frame={frame('tiles')} index={selected} />
    ),
    signal: (
      <SignalPanel
        frame={frame('signal')}
        focus={focus}
        blocked={tradeLive ? undefined : notLive}
        onPaperTrade={paperTrade}
      />
    ),
    // the view and the evidence that produced it, in one full-width panel (E9)
    bias: <BiasPanel frame={frame('bias')} focus={focus} flowIndex={onBullion ? null : selected} />,
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
    trades: <TradesPanel frame={frame('trades')} focus={focus} canClose={tradeLive} />,
    history: <HistoryPanel frame={frame('history')} focus={focus} />,
  }

  return (
    <div className="flex h-full flex-col">
      <LiveTopBar
        health={health}
        ws={ws}
        bullionTab={onBullion}
        theme={theme}
        onToggleTheme={toggleTheme}
        debug={debug}
        onToggleDebug={toggleDebug}
        view={view}
        onView={showView}
        panelsChanged={panels.changed}
        onRestorePanels={panels.restoreAll}
        newsHidden={!panels.newsShown}
        onToggleNews={() => {
          panels.showNews(!panels.newsShown)
        }}
        onLogout={logout}
        dataControl={<DataPanel />}
        configControl={
          <ConfigControl
            parameters={parameters}
            effectiveFrom={parametersEffectiveFrom}
            onSaved={applyParameters}
          />
        }
      />
      <LiveRatesStrip tabs={tabs} onOpen={openRate} />
      <StatusBanner banner={banner} />
      <main className="flex min-h-0 flex-1">
        {view === 'journal' ? (
          <Journal
            indices={instruments.map((i) => i.index)}
            revision={journalRevision}
            bank={<LiveBank showLedger />}
          />
        ) : view === 'trades' ? (
          <LiveTradeLog markets={tradeMarkets} revision={journalRevision} closeBlock={closeBlock} />
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
            <RightColumn
              chain={onBullion ? null : <ChainPanel frame={frame('chain')} index={selected} />}
              chainMinimised={panels.minimised.chain}
              news={
                <NewsPanel
                  frame={frame('news')}
                  news={news}
                  seenTs={newsSeenTs}
                  onClose={() => {
                    panels.setNewsHidden(true)
                  }}
                />
              }
              newsMinimised={panels.minimised.news}
              newsHidden={panels.newsHidden}
              onExpandAll={() => {
                panels.open('chain')
                panels.open('news')
                panels.setNewsHidden(false)
              }}
              width={layout.chainWidth}
              onWidth={(chainWidth) => {
                setLayout({ chainWidth })
              }}
              newsHeight={layout.newsHeight}
              onNewsHeight={(newsHeight) => {
                setLayout({ newsHeight })
              }}
              chainClassName={staleCls}
            />
          </>
        )}
      </main>
      {debug ? <DebugOverlay /> : null}
    </div>
  )
}
