import type { ParameterField } from '../api/types'
import { changedPaths, flatten, toValues } from './config'

const params = {
  bias: { entry_threshold: 0.5, neutral_band: 0.2 },
  signal: {
    entry_mode: 'minute_close',
    last_signal_time: '15:00:00',
    expiry_points: { NIFTY: { target: 40, stop: 20 } },
  },
}

function field(path: string, kind: ParameterField['kind']): ParameterField {
  const [group = '', ...rest] = path.split('.')
  return {
    path,
    group,
    key: rest.join('.'),
    kind,
    help: '',
    ge: null,
    gt: null,
    le: null,
    lt: null,
    choices: null,
  }
}

describe('flatten', () => {
  it('gives one text value per path, however deep', () => {
    expect(flatten(params)).toEqual({
      'bias.entry_threshold': '0.5',
      'bias.neutral_band': '0.2',
      'signal.entry_mode': 'minute_close',
      'signal.last_signal_time': '15:00',
      'signal.expiry_points.NIFTY.target': '40',
      'signal.expiry_points.NIFTY.stop': '20',
    })
  })
})

describe('changedPaths', () => {
  it('lists the paths whose text differs, ignoring spaces and number spelling', () => {
    const base = flatten(params)
    expect(changedPaths(base, { ...base })).toEqual([])
    expect(changedPaths(base, { ...base, 'bias.entry_threshold': ' 0.50 ' })).toEqual([])
    expect(
      changedPaths(base, {
        ...base,
        'bias.entry_threshold': '0.6',
        'signal.entry_mode': 'trigger',
      }),
    ).toEqual(['bias.entry_threshold', 'signal.entry_mode'])
  })

  it('counts a path that only one side has', () => {
    expect(changedPaths({ 'a.b': '1' }, { 'a.c': '1' })).toEqual(['a.b', 'a.c'])
  })
})

describe('toValues', () => {
  const fields = [
    field('bias.entry_threshold', 'number'),
    field('signal.entry_mode', 'choice'),
    field('signal.last_signal_time', 'time'),
    field('signal.expiry_points.NIFTY.target', 'number'),
  ]

  it('puts the draft back into the nested shape, numbers as numbers', () => {
    const draft = {
      ...flatten(params),
      'bias.entry_threshold': '0.6',
      'signal.entry_mode': 'trigger',
      'signal.last_signal_time': '14:30',
      'signal.expiry_points.NIFTY.target': '45',
    }
    const out = toValues(params, fields, draft)
    expect(out).toEqual({
      bias: { entry_threshold: 0.6, neutral_band: 0.2 },
      signal: {
        entry_mode: 'trigger',
        last_signal_time: '14:30',
        expiry_points: { NIFTY: { target: 45, stop: 20 } },
      },
    })
    // the values it started from are untouched
    expect(params.bias.entry_threshold).toBe(0.5)
  })

  it('leaves text that is not a number as typed, for the server to refuse', () => {
    const out = toValues(params, fields, { ...flatten(params), 'bias.entry_threshold': 'abc' })
    expect(out.bias?.entry_threshold).toBe('abc')
    const empty = toValues(params, fields, { ...flatten(params), 'bias.entry_threshold': ' ' })
    expect(empty.bias?.entry_threshold).toBe('')
  })
})
