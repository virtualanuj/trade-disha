interface Props {
  on: boolean
  /** the accessible name, e.g. "NIFTY: Put-call ratio" */
  label: string
  /** a working switch; without it only the state is shown, as a flat ON/OFF label */
  onChange?: (on: boolean) => void
  busy?: boolean
  title?: string
}

const TRACK = 'relative inline-flex h-3.5 w-6 shrink-0 rounded-full transition-colors'
const KNOB = 'absolute top-0.5 h-2.5 w-2.5 rounded-full bg-bg transition-[left]'
const LABEL =
  'inline-flex w-7 shrink-0 cursor-default select-none justify-center rounded-sm border font-mono text-[9px] uppercase leading-[13px] tracking-wide'

/** A factor's on/off switch: on means it counts in the bias (E15, in Config since E16). */
export function FactorSwitch({ on, label, onChange, busy = false, title }: Props) {
  if (!onChange) {
    // Read only: a flat ON/OFF label, not a track and knob, so it does not look clickable.
    return (
      <span
        role="switch"
        aria-checked={on}
        aria-readonly="true"
        aria-disabled="true"
        aria-label={label}
        title={title}
        data-readonly="true"
        className={`${LABEL} ${on ? 'border-bull/50 bg-bull/10 text-bull' : 'border-border text-fg-muted'}`}
      >
        {on ? 'on' : 'off'}
      </span>
    )
  }
  const look = `${TRACK} ${on ? 'bg-accent/80' : 'bg-border'}`
  const knob = <span className={`${KNOB} ${on ? 'left-3' : 'left-0.5'}`} />
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      title={title}
      disabled={busy}
      onClick={() => {
        onChange(!on)
      }}
      className={`${look} disabled:opacity-50`}
    >
      {knob}
    </button>
  )
}
