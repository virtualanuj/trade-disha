import { useRef } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'

const KEY_STEP = 16

interface Props {
  /** 'vertical' is a bar between left and right panels; 'horizontal' between top and bottom */
  orientation: 'vertical' | 'horizontal'
  label: string
  value: number
  min: number
  max: number
  /** pixels moved since the last call: right or down is positive */
  onDrag: (delta: number) => void
  onReset: () => void
}

/** A draggable border between two panels. Double-click puts it back. */
export function Divider({ orientation, label, value, min, max, onDrag, onReset }: Props) {
  const last = useRef<number | null>(null)
  const pending = useRef(0)
  const frame = useRef<number | null>(null)
  const vertical = orientation === 'vertical'

  const flush = () => {
    frame.current = null
    const delta = pending.current
    pending.current = 0
    if (delta !== 0) onDrag(delta)
  }

  const down = (e: PointerEvent<HTMLDivElement>) => {
    last.current = vertical ? e.clientX : e.clientY
    e.currentTarget.setPointerCapture(e.pointerId)
    e.preventDefault()
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (last.current == null) return
    const pos = vertical ? e.clientX : e.clientY
    pending.current += pos - last.current
    last.current = pos
    // one layout per animation frame, however fast the pointer moves
    frame.current ??= requestAnimationFrame(flush)
  }
  const up = (e: PointerEvent<HTMLDivElement>) => {
    last.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    const back = vertical ? 'ArrowLeft' : 'ArrowUp'
    const forward = vertical ? 'ArrowRight' : 'ArrowDown'
    if (e.key === back) onDrag(-KEY_STEP)
    else if (e.key === forward) onDrag(KEY_STEP)
    else if (e.key === 'Home') onReset()
    else return
    e.preventDefault()
  }

  return (
    // A separator that can be moved is an interactive widget (WAI-ARIA "window splitter"):
    // it takes focus and handles pointer and key events. The lint rules assume a static one.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div
      role="separator"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      aria-orientation={orientation}
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      title={`${label}: drag to resize, double-click to reset`}
      className={`group relative shrink-0 touch-none select-none outline-none ${
        vertical ? 'w-1 cursor-col-resize' : 'h-1 cursor-row-resize'
      }`}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onDoubleClick={onReset}
      onKeyDown={key}
    >
      {/* wider invisible hit area around a thin visible line */}
      <div className={`absolute ${vertical ? '-inset-x-1 inset-y-0' : 'inset-x-0 -inset-y-1'}`} />
      <div
        className={`absolute bg-border transition-colors group-hover:bg-accent group-focus-visible:bg-accent ${
          vertical ? 'inset-y-0 left-0 w-px' : 'inset-x-0 top-0 h-px'
        }`}
      />
    </div>
  )
}
