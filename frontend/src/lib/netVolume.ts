import type { CandleOut } from '../api/types'

/** One minute's net volume: buyer- minus seller-initiated (spec §7.1, Milestone E8). */
export interface NetVolumeBar {
  /** the minute's start, epoch ms */
  time: number
  value: number
  buy: number
  sell: number
  /** traded volume no side could be given to */
  unclassified: number
}

/** A bar for each candle that has side information; minutes without it are left out. */
export function netVolumeBars(candles: CandleOut[]): NetVolumeBar[] {
  const out: NetVolumeBar[] = []
  for (const c of candles) {
    if (c.bv == null || c.sv == null) continue
    out.push({
      time: c.t,
      value: c.bv - c.sv,
      buy: c.bv,
      sell: c.sv,
      unclassified: Math.max(0, c.v - c.bv - c.sv),
    })
  }
  return out
}

/** The bar for the minute `time` (under the crosshair), or the latest when `time` is null. */
export function netVolumeAt(bars: NetVolumeBar[], time: number | null): NetVolumeBar | undefined {
  if (time == null) return bars.at(-1)
  return bars.find((b) => b.time === time)
}
