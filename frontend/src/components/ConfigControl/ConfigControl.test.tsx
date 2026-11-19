import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { ConfigRejected } from '../../api/client'
import type { ConfigVersionOut, ParameterField, ParametersOut } from '../../api/types'
import { ConfigControl, type ConfigApi } from './ConfigControl'

const v1: ParametersOut = {
  version: 1,
  tag: 'initial',
  created_ts: 1_794_800_000_000,
  params: {
    bias: { entry_threshold: 0.5, neutral_band: 0.2 },
    signal: { entry_mode: 'minute_close', last_signal_time: '15:00:00' },
    factors: {
      nifty: { ema_cross: 'on', pcr: 'off', gift_nifty: 'on' },
      banknifty: { ema_cross: 'on', pcr: 'on' },
      gold: { ema_cross: 'on', peer_metal: 'on' },
      silver: { ema_cross: 'on', peer_metal: 'on' },
    },
  },
}

function field(
  path: string,
  kind: ParameterField['kind'],
  more: Partial<ParameterField> = {},
): ParameterField {
  const [group = '', ...rest] = path.split('.')
  return {
    path,
    group,
    key: rest.join('.'),
    kind,
    help: `help for ${path}`,
    ge: null,
    gt: null,
    le: null,
    lt: null,
    choices: null,
    ...more,
  }
}

const fields = [
  field('bias.entry_threshold', 'number', { gt: 0, le: 1 }),
  field('bias.neutral_band', 'number'),
  field('signal.entry_mode', 'choice', { choices: ['minute_close', 'trigger'] }),
  field('signal.last_signal_time', 'time'),
]

const history: ConfigVersionOut[] = [
  {
    version: 2,
    tag: 'higher bar',
    created_ts: 1_794_810_000_000,
    source: 'edit',
    reverted_from: null,
    active: true,
  },
  {
    version: 1,
    tag: 'initial',
    created_ts: 1_794_800_000_000,
    source: 'seed',
    reverted_from: null,
    active: false,
  },
]

function setup(over: Partial<ConfigApi> = {}, parameters: ParametersOut = v1) {
  const api: ConfigApi = {
    schema: vi.fn().mockResolvedValue(fields),
    save: vi.fn().mockResolvedValue({ ...v1, version: 2, tag: 'higher bar' }),
    versions: vi.fn().mockResolvedValue(history),
    revert: vi.fn().mockResolvedValue({ ...v1, version: 3, tag: 'Revert to v1' }),
    setFactor: vi.fn().mockResolvedValue({ ...v1, version: 2, tag: 'Factor NIFTY.ema_cross: off' }),
    ...over,
  }
  const onSaved = vi.fn()
  const view = render(
    <ConfigControl parameters={parameters} effectiveFrom={null} onSaved={onSaved} api={api} />,
  )
  return { api, onSaved, ...view }
}

async function openEditor() {
  fireEvent.click(screen.getByRole('button', { name: /^Config/ }))
  return screen.findByLabelText('bias.entry_threshold')
}

describe('ConfigControl', () => {
  it('shows the version and tag in force', () => {
    setup()
    const button = screen.getByRole('button', { name: /^Config/ })
    expect(button).toHaveTextContent('v1')
    expect(button).toHaveTextContent('initial')
    expect(screen.queryByTestId('config-panel')).not.toBeInTheDocument()
  })

  it('lists every field with its value, help and limits', async () => {
    setup()
    const entry = await openEditor()
    expect(entry).toHaveValue('0.5')
    expect(
      screen.getByText(/help for bias.entry_threshold \(more than 0, at most 1\)/),
    ).toBeVisible()
    expect(screen.getByLabelText('signal.entry_mode')).toHaveValue('minute_close')
    expect(screen.getByLabelText('signal.last_signal_time')).toHaveValue('15:00')
    expect(screen.getByRole('button', { name: 'Save as v2' })).toBeDisabled()
  })

  it('saves changed values under a tag and reports the new version', async () => {
    const { api, onSaved } = setup()
    const entry = await openEditor()
    fireEvent.change(entry, { target: { value: '0.6' } })
    expect(screen.getByText('was 0.5')).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Save as v2' })
    expect(save).toBeDisabled() // no tag yet
    fireEvent.change(screen.getByLabelText('Tag for this version'), {
      target: { value: ' higher bar ' },
    })
    expect(save).toBeEnabled()
    fireEvent.click(save)

    await vi.waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(api.save).toHaveBeenCalledWith('higher bar', {
      bias: { entry_threshold: 0.6, neutral_band: 0.2 },
      signal: { entry_mode: 'minute_close', last_signal_time: '15:00' },
      factors: v1.params.factors, // the switches in force go along untouched
    })
    const [saved, from] = onSaved.mock.calls[0] as [ParametersOut, number]
    expect(saved.version).toBe(2)
    expect(from % 60_000).toBe(0)
    expect(screen.getByRole('status')).toHaveTextContent('applies from')
  })

  it('shows what the server refused beside the field or its group, and keeps the draft', async () => {
    const save = vi.fn().mockRejectedValue(
      new ConfigRejected([
        { field: 'bias.entry_threshold', message: 'Input should be less than or equal to 1' },
        { field: 'bias', message: 'neutral_band must be below entry_threshold' },
      ]),
    )
    const { onSaved } = setup({ save })
    const entry = await openEditor()
    fireEvent.change(entry, { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('Tag for this version'), { target: { value: 't' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save as v2' }))

    expect(await screen.findByText('Input should be less than or equal to 1')).toBeInTheDocument()
    expect(screen.getByText('neutral_band must be below entry_threshold')).toBeInTheDocument()
    expect(entry).toHaveAttribute('aria-invalid', 'true')
    expect(entry).toHaveValue('7')
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('discard puts the values in force back', async () => {
    setup()
    const entry = await openEditor()
    fireEvent.change(entry, { target: { value: '0.9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(entry).toHaveValue('0.5')
  })

  it('starts the form again from a new version', async () => {
    const { rerender, api } = setup()
    const entry = await openEditor()
    fireEvent.change(entry, { target: { value: '0.9' } })
    rerender(
      <ConfigControl
        parameters={{
          ...v1,
          version: 2,
          params: { ...v1.params, bias: { entry_threshold: 0.6, neutral_band: 0.2 } },
        }}
        effectiveFrom={null}
        onSaved={vi.fn()}
        api={api}
      />,
    )
    expect(screen.getByLabelText('bias.entry_threshold')).toHaveValue('0.6')
    expect(screen.getByRole('button', { name: 'Save as v3' })).toBeDisabled()
  })

  it('history lists the versions and reverts to an old one under a tag', async () => {
    const { api, onSaved } = setup({}, { ...v1, version: 2, tag: 'higher bar' })
    fireEvent.click(screen.getByRole('button', { name: /^Config/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'History' }))

    const newest = await screen.findByTestId('config-version-2')
    expect(newest).toHaveTextContent('higher bar')
    expect(newest).toHaveTextContent('in force')
    expect(within(newest).queryByRole('button')).not.toBeInTheDocument()
    const oldest = screen.getByTestId('config-version-1')
    expect(oldest).toHaveTextContent('from params.toml')

    fireEvent.click(within(oldest).getByRole('button', { name: 'Revert to version 1' }))
    const tag = screen.getByLabelText('Tag for the reverted version')
    expect(tag).toHaveValue('Revert to v1')
    fireEvent.change(tag, { target: { value: 'back to the start' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm revert' }))

    await vi.waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
    expect(api.revert).toHaveBeenCalledWith(1, 'back to the start')
  })

  describe('factors (E16)', () => {
    async function openFactors() {
      fireEvent.click(screen.getByRole('button', { name: /^Config/ }))
      fireEvent.click(await screen.findByRole('tab', { name: 'Factors · 1 off' }))
      return screen.getByTestId('factors-tab')
    }

    it('has no factor fields in the typed form', async () => {
      setup()
      await openEditor()
      expect(screen.queryByRole('switch')).toBeNull()
    })

    it('lists each index and metal with its switches as in force', async () => {
      setup()
      const tab = await openFactors()
      expect(within(tab).getByText('BANK NIFTY')).toBeInTheDocument()
      expect(within(tab).getByRole('switch', { name: 'NIFTY: Put-call ratio' })).toHaveAttribute(
        'aria-checked',
        'false',
      )
      expect(within(tab).getByRole('switch', { name: 'NIFTY: GIFT Nifty gap' })).toHaveAttribute(
        'aria-checked',
        'true',
      )
      expect(within(tab).getByRole('switch', { name: 'GOLD: Other metal’s trend' })).toBeEnabled()
      expect(within(tab).getByText('1 off')).toBeInTheDocument()
    })

    it('saves a flip at once as a version, waiting for the server', async () => {
      let done: (p: ParametersOut) => void = () => undefined
      const pending = new Promise<ParametersOut>((resolve) => {
        done = resolve
      })
      const { api, onSaved } = setup({ setFactor: vi.fn().mockReturnValue(pending) })
      const tab = await openFactors()
      const ema = within(tab).getByRole('switch', { name: 'NIFTY: EMA crossover' })
      fireEvent.click(ema)
      expect(api.setFactor).toHaveBeenCalledWith('NIFTY', 'ema_cross', false)
      expect(ema).toBeDisabled()
      expect(within(tab).getByText('saving…')).toBeInTheDocument()
      done({ ...v1, version: 2, tag: 'Factor NIFTY.ema_cross: off' })
      await waitFor(() => {
        expect(onSaved).toHaveBeenCalledTimes(1)
      })
      expect(api.save).not.toHaveBeenCalled() // no typed tag: the server names the version
    })

    it('turns a factor back on', async () => {
      const { api } = setup()
      const tab = await openFactors()
      fireEvent.click(within(tab).getByRole('switch', { name: 'NIFTY: Put-call ratio' }))
      expect(api.setFactor).toHaveBeenCalledWith('NIFTY', 'pcr', true)
    })

    it('shows why a flip was refused and saves nothing', async () => {
      const refused = new ConfigRejected([
        { field: 'factors', message: 'NIFTY has no factor nope' },
      ])
      const { onSaved } = setup({ setFactor: vi.fn().mockRejectedValue(refused) })
      const tab = await openFactors()
      fireEvent.click(within(tab).getByRole('switch', { name: 'NIFTY: EMA crossover' }))
      expect(await within(tab).findByRole('alert')).toHaveTextContent('NIFTY has no factor nope')
      expect(onSaved).not.toHaveBeenCalled()
    })
  })
})
