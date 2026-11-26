import { useCallback, useMemo, useState } from 'react'
import type { ComponentProps } from 'react'

import type { NewsOut, PaperTradeOut, SignalOut, TicketTarget } from '../../api/types'
import { isLong } from '../../lib/direction'
import { factorSwitches } from '../../lib/factors'
import { newestBullionTs, newestIndexTickTs, openTradeCount } from '../../lib/marketViews'
import { newsSummary } from '../../lib/news'
import {
  biasSummary,
  bullionSummary,
  chainSummary,
  historySummary,
  signalSummary,
  tilesSummary,
  tradesSummary,
} from '../../lib/panelSummary'
import { useMarketNow } from '../../lib/marketClock'
import { chainTicket } from '../../lib/ticket'
import { useNow } from '../../lib/useNow'
import { useMarketStore } from '../../state/store'
import { Bank } from '../Bank/Bank'
import { BiasMeter } from '../BiasMeter/BiasMeter'
import { stripRates } from '../../lib/rates'
import { BullionCards } from '../BullionView/BullionView'
import { RatesStrip } from '../RatesStrip/RatesStrip'
import { EvidenceTable } from '../EvidenceTable/EvidenceTable'
import { FlowLine } from '../FlowLine/FlowLine'
import { Headlines } from '../Headlines/Headlines'
import { IndexTiles } from '../IndexTiles/IndexTiles'
import { OpenTrades } from '../OpenTrades/OpenTrades'
import { OptionChain } from '../OptionChain/OptionChain'
import { PanelFrame } from '../PanelFrame/PanelFrame'
import { SignalCard } from '../SignalCard/SignalCard'
import { SignalHistory } from '../SignalHistory/SignalHistory'
import { TopBar } from '../TopBar/TopBar'
import { TradeLog } from '../TradeLog/TradeLog'
import { TradeTicket } from '../TradeTicket/TradeTicket'

/*
 * The page's live pieces, each reading the store itself.
 *
 * A frame replaces one slice of the store (a tick the prices, a chain frame one chain).
 * Read in `App`, every frame re-rendered the whole page; read here, it re-renders only the
 * piece that shows that slice. Each one renders exactly what `App` rendered in its place.
 */

/** what `App` gives a panel: its minimise control and, in the left column, move buttons */
export type FrameProps = Pick<
  ComponentProps<typeof PanelFrame>,
  'id' | 'minimised' | 'onToggle' | 'move'
>

function useOpenTrades() {
  const trades = useMarketStore((s) => s.trades)
  return useMemo(() => trades.filter((t) => t.status === 'open'), [trades])
}

/** The top bar's clock, feed age and open-trade count move here, not in `App`. */
export function LiveTopBar(
  props: Omit<ComponentProps<typeof TopBar>, 'now' | 'lastTickTs' | 'openTradeCount'>,
) {
  const now = useMarketNow(500)
  const bullionTab = props.bullionTab ?? false
  const lastTickTs = useMarketStore((s) =>
    bullionTab ? newestBullionTs(s.bullion) : newestIndexTickTs(s.prices),
  )
  const count = useMarketStore((s) => openTradeCount(s.trades))
  return <TopBar {...props} now={now} lastTickTs={lastTickTs} openTradeCount={count} />
}

/** The rates strip (E22), reading its own prices so their frames re-render only it. */
export function LiveRatesStrip({
  tabs,
  onOpen,
}: {
  tabs: readonly string[]
  onOpen: (tab: string, metal: string | null) => void
}) {
  const nifty = useMarketStore((s) => s.prices.NIFTY)
  const niftyStats = useMarketStore((s) => s.stats.NIFTY)
  const quotes = useMarketStore((s) => s.quotes)
  const bullion = useMarketStore((s) => s.bullion)
  const rates = useMemo(
    () => stripRates(nifty, niftyStats, quotes, bullion, tabs),
    [nifty, niftyStats, quotes, bullion, tabs],
  )
  return <RatesStrip rates={rates} onOpen={onOpen} />
}

export function IndexTilesPanel({ frame, index }: { frame: FrameProps; index: string }) {
  const instruments = useMarketStore((s) => s.instruments)
  const prices = useMarketStore((s) => s.prices)
  const stats = useMarketStore((s) => s.stats)
  const shown = useMemo(() => instruments.filter((i) => i.index === index), [instruments, index])
  return (
    <PanelFrame {...frame} title="Index" summary={tilesSummary(prices[index], stats[index])}>
      <IndexTiles instruments={shown} prices={prices} stats={stats} />
    </PanelFrame>
  )
}

/** The ticket for a trade opened by hand (E23), and the trade it opens put in the store. */
function useTicket() {
  const [ticket, setTicket] = useState<TicketTarget | null>(null)
  const applyTrades = useMarketStore((s) => s.applyTrades)
  const close = useCallback(() => {
    setTicket(null)
  }, [])
  const opened = useCallback(
    (t: PaperTradeOut) => {
      applyTrades([t])
    },
    [applyTrades],
  )
  return { ticket, setTicket, close, opened }
}

export function BullionTilesPanel({ frame }: { frame: FrameProps }) {
  const bullion = useMarketStore((s) => s.bullion)
  const nseStatus = useMarketStore((s) => s.health?.market_status ?? null)
  const { ticket, setTicket, close, opened } = useTicket()
  const ltp = ticket ? (bullion?.metals.find((m) => m.metal === ticket.index)?.ltp ?? null) : null
  return (
    <PanelFrame {...frame} title="Bullion" summary={bullionSummary(bullion)}>
      <BullionCards bullion={bullion} nseStatus={nseStatus} onTrade={setTicket} />
      {ticket ? <TradeTicket target={ticket} ltp={ltp} onClose={close} onOpened={opened} /> : null}
    </PanelFrame>
  )
}

export function SignalPanel({
  frame,
  focus,
  blocked,
  onPaperTrade,
}: {
  frame: FrameProps
  focus: string
  blocked: string | undefined
  onPaperTrade: (s: SignalOut) => Promise<unknown>
}) {
  const now = useMarketNow(500)
  const signal = useMarketStore((s) => s.signals[focus])
  const gate = useMarketStore((s) => s.gates[focus])
  const open = useOpenTrades()
  const openOnIndex = useMemo(() => open.filter((t) => t.index === focus), [open, focus])
  return (
    <PanelFrame
      {...frame}
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
        blocked={blocked}
        onPaperTrade={onPaperTrade}
      />
    </PanelFrame>
  )
}

/** The view and the evidence that produced it, in one full-width panel (E9). */
export function BiasPanel({
  frame,
  focus,
  flowIndex,
}: {
  frame: FrameProps
  focus: string
  /** the index whose order flow is shown under the evidence; null on BULLION */
  flowIndex: string | null
}) {
  const bias = useMarketStore((s) => s.bias[focus])
  const params = useMarketStore((s) => s.parameters?.params)
  const switches = useMemo(() => factorSwitches(params, focus), [params, focus])
  return (
    <PanelFrame {...frame} title="Market view" summary={biasSummary(bias)}>
      <div className="flex flex-col gap-3">
        <BiasMeter bias={bias} />
        <div className="border-t border-border pt-3">
          <EvidenceTable bias={bias} switches={switches} />
          {flowIndex === null ? null : <LiveFlowLine index={flowIndex} />}
        </div>
      </div>
    </PanelFrame>
  )
}

/** about one reading a second: only this line re-renders for it */
function LiveFlowLine({ index }: { index: string }) {
  const flow = useMarketStore((s) => s.flow[index])
  return <FlowLine flow={flow} />
}

export function TradesPanel({
  frame,
  focus,
  canClose,
}: {
  frame: FrameProps
  focus: string
  canClose: boolean
}) {
  const now = useMarketNow(500)
  const bank = useMarketStore((s) => s.bank)
  const open = useOpenTrades()
  const openOnIndex = useMemo(() => open.filter((t) => t.index === focus), [open, focus])
  return (
    <PanelFrame
      {...frame}
      title="Open paper trades"
      summary={tradesSummary(openOnIndex)}
      border={openOnIndex.length > 0 ? 'border-accent/50' : 'border-border'}
    >
      <div className="flex flex-col gap-2">
        <Bank bank={bank} openTrades={open} />
        <OpenTrades trades={openOnIndex} now={now} canClose={canClose} />
      </div>
    </PanelFrame>
  )
}

export function HistoryPanel({ frame, focus }: { frame: FrameProps; focus: string }) {
  const signals = useMarketStore((s) => s.signalHistory)
  return (
    <PanelFrame {...frame} title="Signals today" summary={historySummary(signals, focus)}>
      <SignalHistory signals={signals} index={focus} />
    </PanelFrame>
  )
}

export function ChainPanel({ frame, index }: { frame: FrameProps; index: string }) {
  const chain = useMarketStore((s) => s.chains[index])
  const { ticket, setTicket, close, opened } = useTicket()
  const onTrade = useCallback(
    (strike: number, side: 'ce' | 'pe') => {
      setTicket(chainTicket(index, strike, side))
    },
    [index, setTicket],
  )
  const row = ticket ? chain?.rows.find((r) => r.strike === ticket.strike) : undefined
  const ltp = row ? (ticket?.direction === 'BUY_CE' ? row.ce.ltp : row.pe.ltp) : null
  return (
    <PanelFrame {...frame} title="Option chain" summary={chainSummary(chain)} fill>
      <OptionChain chain={chain} onTrade={onTrade} />
      {ticket ? <TradeTicket target={ticket} ltp={ltp} onClose={close} onOpened={opened} /> : null}
    </PanelFrame>
  )
}

export function NewsPanel({
  frame,
  news,
  seenTs,
  onClose,
}: {
  frame: FrameProps
  news: NewsOut | null
  seenTs: number | null
  onClose: () => void
}) {
  const now = useNow(500)
  return (
    <PanelFrame
      {...frame}
      title="Headlines"
      summary={newsSummary(news, seenTs, now)}
      onClose={onClose}
      fill
      bodyClassName=""
    >
      <Headlines news={news} seenTs={seenTs} now={now} />
    </PanelFrame>
  )
}

/** The paper bank with the open trades' live P&L, for the Journal page. */
export function LiveBank({ showLedger = false }: { showLedger?: boolean }) {
  const bank = useMarketStore((s) => s.bank)
  const open = useOpenTrades()
  return <Bank bank={bank} openTrades={open} showLedger={showLedger} />
}

/** The Trades page, with the socket's trades and the clock for open trades' time held. */
export function LiveTradeLog(props: Omit<ComponentProps<typeof TradeLog>, 'latest' | 'now'>) {
  const now = useMarketNow(500)
  const trades = useMarketStore((s) => s.trades)
  return <TradeLog {...props} latest={trades} now={now} />
}
