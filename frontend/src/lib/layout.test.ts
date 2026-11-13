import { fmtDate } from './format'
import { clampLayout, DEFAULT_LAYOUT, parseLayout } from './layout'

describe('fmtDate', () => {
  it('shows ISO dates as DD/MM/YYYY', () => {
    expect(fmtDate('2026-11-17')).toBe('17/11/2026')
    expect(fmtDate('2026-01-05T09:15:00+05:30')).toBe('05/01/2026')
  })

  it('shows a moment as its IST day, even when UTC is still on the day before', () => {
    expect(fmtDate(Date.UTC(2026, 10, 12, 20, 0))).toBe('13/11/2026') // 01:30 IST on the 13th
    expect(fmtDate(Date.UTC(2026, 10, 13, 6, 0))).toBe('13/11/2026')
  })

  it('shows a dash for nothing and leaves unknown text alone', () => {
    expect(fmtDate(null)).toBe('—')
    expect(fmtDate('')).toBe('—')
    expect(fmtDate('soon')).toBe('soon')
  })
})

describe('layout', () => {
  it('keeps sizes within their limits', () => {
    expect(clampLayout({ chainWidth: 100, chartHeight: 50 }, 1920)).toEqual({
      chainWidth: 420,
      chartHeight: 200,
    })
    expect(clampLayout({ chainWidth: 5000, chartHeight: 5000 }, 1920)).toEqual({
      chainWidth: 900,
      chartHeight: 700,
    })
  })

  it('never lets the option chain take more than 60% of the window', () => {
    expect(clampLayout({ chainWidth: 900, chartHeight: 320 }, 1280).chainWidth).toBe(768)
  })

  it('still shows the chain at its minimum on a very narrow window', () => {
    expect(clampLayout({ chainWidth: 640, chartHeight: 320 }, 600).chainWidth).toBe(420)
  })

  it('reads a stored layout and falls back to the default for anything else', () => {
    expect(parseLayout({ chainWidth: 700, chartHeight: 400 })).toEqual({
      chainWidth: 700,
      chartHeight: 400,
    })
    for (const bad of [
      undefined,
      null,
      'x',
      { chainWidth: 'wide' },
      { chainWidth: NaN, chartHeight: 1 },
    ]) {
      expect(parseLayout(bad)).toEqual(DEFAULT_LAYOUT)
    }
  })
})
