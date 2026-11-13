import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { CandleOut, OverlayOut, SignalOut } from '../../api/types'
import type { Theme } from '../../theme/useTheme'

const IST_OFFSET_S = 5.5 * 3600

/** lightweight-charts renders times as UTC; shift so the axis reads IST. */
function toTime(ms: number): UTCTimestamp {
  return (Math.floor(ms / 1000) + IST_OFFSET_S) as UTCTimestamp
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function toCandle(c: CandleOut): CandlestickData {
  return { time: toTime(c.t), open: c.o, high: c.h, low: c.l, close: c.c }
}

function line(points: OverlayOut[], pick: (o: OverlayOut) => number | null): LineData[] {
  const out: LineData[] = []
  for (const o of points) {
    const v = pick(o)
    if (v != null) out.push({ time: toTime(o.t), value: v })
  }
  return out
}

interface Props {
  candles: CandleOut[]
  overlays: OverlayOut[]
  signals?: SignalOut[]
  /** identifies the series; changing it resets the chart data */
  dataKey: string
  theme: Theme
  /** pixels; the chart follows its container when this changes */
  height?: number
}

const STATUS_SHAPE: Record<SignalOut['status'], string> = {
  active: '',
  traded: ' (traded)',
  lapsed: ' (lapsed)',
  reversed: ' (reversed)',
}

function toMarker(s: SignalOut): SeriesMarker<Time> {
  const call = s.direction === 'BUY_CE'
  return {
    time: toTime(s.minute_ts),
    position: call ? 'belowBar' : 'aboveBar',
    shape: call ? 'arrowUp' : 'arrowDown',
    color: call ? cssVar('--bull') : cssVar('--bear'),
    text: `${call ? 'CE' : 'PE'} ${String(s.strike)}${STATUS_SHAPE[s.status]}`,
  }
}

interface Series {
  candles: ISeriesApi<'Candlestick'>
  emaFast: ISeriesApi<'Line'>
  emaSlow: ISeriesApi<'Line'>
  vwap: ISeriesApi<'Line'>
  supertrend: ISeriesApi<'Line'>
  markers: ISeriesMarkersPluginApi<Time>
}

export function PriceChart({
  candles,
  overlays,
  signals = [],
  dataKey,
  theme,
  height = 320,
}: Props) {
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<Series | null>(null)
  const lastCount = useRef({ candles: 0, overlays: 0, key: '' })

  // create / destroy
  useEffect(() => {
    if (!host.current) return
    const el = host.current
    const c = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: cssVar('--fg-muted'),
      },
      grid: { vertLines: { color: cssVar('--border') }, horzLines: { color: cssVar('--border') } },
      rightPriceScale: { borderColor: cssVar('--border') },
      timeScale: { borderColor: cssVar('--border'), timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    })
    const bull = cssVar('--bull')
    const bear = cssVar('--bear')
    const s: Series = {
      candles: c.addSeries(CandlestickSeries, {
        upColor: bull,
        downColor: bear,
        borderUpColor: bull,
        borderDownColor: bear,
        wickUpColor: bull,
        wickDownColor: bear,
      }),
      emaFast: c.addSeries(LineSeries, {
        color: '#f5b942',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      emaSlow: c.addSeries(LineSeries, {
        color: '#5b9cff',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      vwap: c.addSeries(LineSeries, {
        color: '#a78bfa',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      supertrend: c.addSeries(LineSeries, {
        color: cssVar('--neutral'),
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      markers: undefined as unknown as ISeriesMarkersPluginApi<Time>,
    }
    s.markers = createSeriesMarkers(s.candles, [])
    chart.current = c
    series.current = s
    lastCount.current = { candles: 0, overlays: 0, key: '' }
    return () => {
      c.remove()
      chart.current = null
      series.current = null
    }
  }, [theme])

  // data: full set on (re)mount or when history shrinks/replaces; incremental otherwise
  useEffect(() => {
    const s = series.current
    if (!s) return
    const prev = lastCount.current
    const reset = prev.key !== dataKey
    if (
      reset ||
      candles.length < prev.candles ||
      prev.candles === 0 ||
      candles.length - prev.candles > 1
    ) {
      s.candles.setData(candles.map(toCandle))
    } else {
      const last = candles[candles.length - 1]
      if (last) s.candles.update(toCandle(last))
    }
    if (
      reset ||
      overlays.length < prev.overlays ||
      prev.overlays === 0 ||
      overlays.length - prev.overlays > 1
    ) {
      s.emaFast.setData(line(overlays, (o) => o.ema_fast))
      s.emaSlow.setData(line(overlays, (o) => o.ema_slow))
      s.vwap.setData(line(overlays, (o) => o.vwap))
      s.supertrend.setData(line(overlays, (o) => o.supertrend))
    } else {
      const o = overlays[overlays.length - 1]
      if (o) {
        const t = toTime(o.t)
        if (o.ema_fast != null) s.emaFast.update({ time: t, value: o.ema_fast })
        if (o.ema_slow != null) s.emaSlow.update({ time: t, value: o.ema_slow })
        if (o.vwap != null) s.vwap.update({ time: t, value: o.vwap })
        if (o.supertrend != null) s.supertrend.update({ time: t, value: o.supertrend })
      }
    }
    if ((reset || prev.candles === 0) && candles.length) chart.current?.timeScale().fitContent()
    lastCount.current = { candles: candles.length, overlays: overlays.length, key: dataKey }
  }, [candles, overlays, dataKey, theme])

  useEffect(() => {
    const s = series.current
    if (!s) return
    const sorted = [...signals].sort((a, b) => a.minute_ts - b.minute_ts)
    s.markers.setMarkers(sorted.map(toMarker))
  }, [signals, theme])

  return (
    <div
      className="relative w-full shrink-0 rounded border border-border bg-bg-elev"
      style={{ height }}
    >
      <div ref={host} className="h-full w-full" data-testid="price-chart" />
      <div className="pointer-events-none absolute top-2 left-2 flex gap-3 text-[10px] text-fg-muted">
        <span style={{ color: '#f5b942' }}>EMA fast</span>
        <span style={{ color: '#5b9cff' }}>EMA slow</span>
        <span style={{ color: '#a78bfa' }}>VWAP</span>
        <span>Supertrend</span>
      </div>
      {candles.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-fg-muted">
          Waiting for the first closed minute…
        </div>
      ) : null}
    </div>
  )
}
