/** Sizes of the two resizable panels, in pixels. */
export interface Layout {
  /** width of the option-chain panel */
  chainWidth: number
  /** height of the price chart */
  chartHeight: number
}

export const DEFAULT_LAYOUT: Layout = { chainWidth: 640, chartHeight: 320 }

export const LIMITS = {
  chainMin: 420,
  chainMax: 900,
  /** the chain panel never takes more than this share of the window */
  chainShare: 0.6,
  chartMin: 200,
  chartMax: 700,
} as const

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), Math.max(lo, hi))
}

/**
 * A layout that fits the window. Applied on load, on every drag and on window resize, so
 * sizes saved on a large screen cannot hide a panel on a small one.
 */
export function clampLayout(l: Layout, windowWidth: number): Layout {
  const chainMax = Math.min(LIMITS.chainMax, Math.floor(windowWidth * LIMITS.chainShare))
  return {
    chainWidth: Math.round(clamp(l.chainWidth, LIMITS.chainMin, chainMax)),
    chartHeight: Math.round(clamp(l.chartHeight, LIMITS.chartMin, LIMITS.chartMax)),
  }
}

/** A stored layout, if it is one; anything else falls back to the default. */
export function parseLayout(v: unknown): Layout {
  if (typeof v === 'object' && v !== null) {
    const { chainWidth, chartHeight } = v as Record<string, unknown>
    if (
      typeof chainWidth === 'number' &&
      typeof chartHeight === 'number' &&
      Number.isFinite(chainWidth) &&
      Number.isFinite(chartHeight)
    ) {
      return { chainWidth, chartHeight }
    }
  }
  return DEFAULT_LAYOUT
}
