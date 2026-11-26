import { useEffect, useRef, useState, type FocusEvent, type ReactNode } from 'react'

/** a pass of the mouse across the bar should not flash cards */
export const OPEN_DELAY_MS = 250
/** time to move from the button into the card */
export const CLOSE_DELAY_MS = 150

/** Keyboard focus, not the focus a click gives: only the first opens the card. */
function keyboardFocus(el: Element): boolean {
  try {
    return el.matches(':focus-visible')
  } catch {
    return false // a browser (or test DOM) without :focus-visible
  }
}

/**
 * A read-only preview under a top-bar button (E27, spec §13.2): open after a short hover or
 * on keyboard focus, closed on leaving, Esc or a click (the click does the button's own
 * thing). `card` null means there is nothing to preview (its full view is already showing).
 * The card is only mounted while open, so what it reads costs nothing otherwise.
 */
export function HoverCard({
  card,
  label,
  children,
}: {
  card: ReactNode
  /** names the card for assistive tech */
  label: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const later = (next: boolean, ms: number) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      setOpen(next)
    }, ms)
  }
  const shut = () => {
    clearTimeout(timer.current)
    setOpen(false)
  }

  useEffect(
    () => () => {
      clearTimeout(timer.current)
    },
    [],
  )
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const shown = open && card != null
  return (
    <div
      className="relative"
      onMouseEnter={() => {
        later(true, OPEN_DELAY_MS)
      }}
      onMouseLeave={() => {
        later(false, CLOSE_DELAY_MS)
      }}
      onFocus={(e: FocusEvent) => {
        if (keyboardFocus(e.target)) later(true, 0)
      }}
      onBlur={shut}
      onClickCapture={shut}
    >
      {children}
      {shown ? (
        <div
          role="tooltip"
          aria-label={label}
          className="absolute top-full right-0 z-30 mt-1 w-max max-w-[min(32rem,90vw)] rounded border border-border bg-bg-elev p-3 text-xs whitespace-normal shadow-lg"
          data-testid="hover-card"
        >
          {card}
        </div>
      ) : null}
    </div>
  )
}
