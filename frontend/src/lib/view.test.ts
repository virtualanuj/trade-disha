import { hashFor, viewFromHash } from './view'

describe('view hash', () => {
  it.each([
    ['', 'dashboard'],
    ['#', 'dashboard'],
    ['#journal', 'journal'],
    ['#trades', 'trades'],
    ['#dashboard', 'dashboard'],
    ['#bogus', 'dashboard'],
  ] as const)('%s is the %s', (hash, view) => {
    expect(viewFromHash(hash)).toBe(view)
  })

  it('round-trips every page', () => {
    for (const v of ['dashboard', 'journal', 'trades'] as const) {
      expect(viewFromHash(`#${hashFor(v)}`)).toBe(v)
    }
  })
})
