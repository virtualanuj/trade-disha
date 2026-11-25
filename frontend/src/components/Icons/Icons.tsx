import type { ReactNode } from 'react'

/** 14px line icons for the top bar; decorative, so screen readers skip them. */
function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      {children}
    </svg>
  )
}

export function DataIcon() {
  return (
    <Svg>
      <ellipse cx="8" cy="3.5" rx="5" ry="2" />
      <path d="M3 3.5v9c0 1.1 2.2 2 5 2s5-.9 5-2v-9" />
      <path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" />
    </Svg>
  )
}

export function ConfigIcon() {
  return (
    <Svg>
      <path d="M2 4h7M13 4h1M2 12h1M7 12h7M2 8h3M9 8h5" />
      <circle cx="11" cy="4" r="1.6" />
      <circle cx="5" cy="12" r="1.6" />
      <circle cx="7" cy="8" r="1.6" />
    </Svg>
  )
}

export function LatencyIcon() {
  return (
    <Svg>
      <path d="M1.5 8.5h3l2-5 3 9 2-4h3" />
    </Svg>
  )
}

export function SunIcon() {
  return (
    <Svg>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1" />
    </Svg>
  )
}

export function MoonIcon() {
  return (
    <Svg>
      <path d="M13.5 9.5A5.5 5.5 0 1 1 6.5 2.5a4.5 4.5 0 0 0 7 7z" />
    </Svg>
  )
}

export function RestoreIcon() {
  return (
    <Svg>
      <path d="M2 6V2h4M14 10v4h-4M2 2l4.5 4.5M14 14l-4.5-4.5" />
    </Svg>
  )
}

export function NewsIcon() {
  return (
    <Svg>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M5 6h6M5 8.5h6M5 11h3.5" />
    </Svg>
  )
}

export function LogoutIcon() {
  return (
    <Svg>
      <path d="M6 2.5H3.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1H6M10.5 11 14 8l-3.5-3M14 8H6" />
    </Svg>
  )
}

export function LoginIcon() {
  return (
    <Svg>
      <path d="M10 2.5h2.5a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H10M6.5 11 10 8 6.5 5M10 8H2" />
    </Svg>
  )
}

export function DashboardIcon() {
  return (
    <Svg>
      <rect x="2" y="2" width="5" height="6" rx="1" />
      <rect x="9" y="2" width="5" height="3.5" rx="1" />
      <rect x="2" y="10" width="5" height="4" rx="1" />
      <rect x="9" y="7.5" width="5" height="6.5" rx="1" />
    </Svg>
  )
}

export function JournalIcon() {
  return (
    <Svg>
      <path d="M3 2.5h8.5a1 1 0 0 1 1 1v10H4a1 1 0 0 1-1-1z" />
      <path d="M3 12.5a1 1 0 0 1 1-1h8.5M6 5.5h4M6 8h3" />
    </Svg>
  )
}

export function TradesIcon() {
  return (
    <Svg>
      <path d="M2 11.5 6 7.5l2.5 2.5L14 4.5" />
      <path d="M10.5 4.5H14V8" />
    </Svg>
  )
}
