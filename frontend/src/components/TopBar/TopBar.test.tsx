import { render, screen } from '@testing-library/react'

import { TopBar } from './TopBar'

describe('TopBar', () => {
  it('shows the backend version when up', () => {
    render(
      <TopBar
        backend={{ kind: 'up', version: '0.1.0', milestone: 0 }}
        theme="dark"
        onToggleTheme={() => undefined}
      />,
    )
    expect(screen.getByText(/Backend: up/)).toBeInTheDocument()
    expect(screen.getByText('v0.1.0')).toBeInTheDocument()
  })

  it('shows down state with the error as a tooltip', () => {
    render(
      <TopBar
        backend={{ kind: 'down', error: 'health 503' }}
        theme="dark"
        onToggleTheme={() => undefined}
      />,
    )
    expect(screen.getByTitle('health 503')).toHaveTextContent('Backend: down')
  })
})
