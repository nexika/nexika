// mizan's mod under `claude plugin test`: the band draws what the core says, only the fixed
// helper runs, the proof question, and the context-full flow that never clears by itself.

import { expect, mock, test } from 'claude-code/testing'
import type { On, RenderPropsOf } from 'claude-code'

const LABELS = {
  full_saved: 'Context full: your work is saved. Press Enter to start fresh.',
  full_type: 'Context full: your work is saved. Type /clear and press Enter to start fresh.',
  full_nosave: 'Context full. Press Enter to start fresh (install hafiz to keep a handoff note).',
  full_type_nosave: 'Context full. Type /clear and press Enter to start fresh (install hafiz to keep a handoff note).',
  proof_ask: 'Done. Show me the proof?',
  yes: 'Yes',
  no: 'No',
  close: 'Close',
  details: 'Details',
  proof_missing: 'No proof yet. Press Enter to have Claude make one with /itqan:proof.',
  proof_title: 'Proof',
}
const BAND: RenderPropsOf['AbovePrompt'] = {
  hasSurvey: false,
  isWorking: false,
  maxRows: 10,
  bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 10 },
  view: {},
}
const PANE: RenderPropsOf['Pane'] = {
  title: 'mizan',
  isFocused: false,
  bodyColumns: 80,
  placement: 'dock',
  scroll: { offset: 0, bodyRows: 30 },
} as RenderPropsOf['Pane']
const SUBCOMMANDS = ['status', 'handoff', 'proof']

type World = { level: string; draft?: string; proof?: boolean; saved?: boolean }
type Calls = { runs: { argv: readonly string[]; stdin: string }[]; fills: string[]; opened: string[]; compacts: number }

function snapshot(level: string) {
  return {
    band: [
      [
        { text: '⎇ feat/x (Loai)', tone: 'info' },
        { text: 'PRs Loai(7) Jean(3)', tone: 'plain' },
        { text: 'CI failed: test (py3.10)', tone: 'bad' },
        { text: 'RAM 64%', tone: 'dim' },
      ],
      [{ text: `Context ${level} 80%`, tone: 'bad' }, { text: 'Task 2/2: Writing b', tone: 'plain' }],
    ],
    detail: [{ title: 'Branch', lines: [{ text: 'feat/x, started by Loai', tone: 'info' }] }],
    labels: LABELS,
    context: { level, percent: 80 },
    alerts: [],
    proof: { available: false },
  }
}

function world(on: On, w: World): Calls {
  const calls: Calls = { runs: [], fills: [], opened: [], compacts: 0 }
  on('session.usage', () => ({
    value: { startedAt: 0, context: { window: 200_000, percent: 80, tokens: 160_000 }, rateLimits: [], cost: { usd: 1.5 } },
  }))
  on('agent.list', () => ({ value: [] }))
  on('session.id', () => ({ value: 'test-session' }))
  on('session.cwd', () => ({ value: '/work/repo' }))
  on('prompt.read', () => ({ value: { text: w.draft ?? '', cursor: 0 } }))
  on('prompt.fill', ($, e) => {
    calls.fills.push(e.text)
    return { isFilled: true }
  })
  on('ui.open', ($, e) => {
    calls.opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('ui.render', ($, e) => $.ui.resolve(e).Box({})) // the engine's own drawing: an empty box
  on('classic.Stop', () => ({}))
  on('session.compact', () => {
    calls.compacts += 1
    throw new Error('mizan must never compact')
  })
  on('process.run', ($, e) => {
    calls.runs.push({ argv: e.argv, stdin: e.init?.stdin ?? '' })
    const sub = e.argv[2]
    const out =
      sub === 'status'
        ? snapshot(w.level)
        : sub === 'handoff'
          ? { saved: w.saved ?? true }
          : { available: w.proof ?? false, sections: [{ title: 'Proof', lines: [{ text: 'All checks passed', tone: 'ok' }] }] }
    return {
      value: { exitCode: 0, stdout: JSON.stringify(out), stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    }
  })
  on('tool.call', () => ({ result: { oldTodos: [], newTodos: [] } }))
  return calls
}

const TODOS_HALF = [
  { content: 'a', status: 'completed', activeForm: 'Doing a' },
  { content: 'b', status: 'in_progress', activeForm: 'Writing b' },
] as const
const TODOS_DONE = [
  { content: 'a', status: 'completed', activeForm: 'Doing a' },
  { content: 'b', status: 'completed', activeForm: 'Writing b' },
] as const

function onlyTheHelper(calls: Calls): void {
  expect(calls.runs.length).toBeGreaterThan(0)
  for (const run of calls.runs) {
    expect(run.argv[0]).toBe('python3')
    expect(String(run.argv[1]).endsWith('/bin/mizan')).toBe(true)
    expect(SUBCOMMANDS.includes(String(run.argv[2]))).toBe(true)
  }
}

test('the band draws the core lines and the task list reaches the core', async ($, on) => {
  const clock = mock.clock(on)
  const calls = world(on, { level: 'mid' })
  await $.tool.call({ tool: 'TodoWrite', todos: [...TODOS_HALF] })
  await clock.settle()
  const status = calls.runs.find(run => run.argv[2] === 'status')
  expect(status?.argv.slice(2)).toEqual(['status', '--json', '--stdin', '--publish'])
  const sent = JSON.parse(status?.stdin ?? '{}')
  expect(sent.tasks.items).toHaveLength(2)
  expect(sent.source).toBe('mod')
  expect(sent.cost.usd).toBe(1.5)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'mizan', surface, component: 'AbovePrompt', props: BAND })
    expect(await ui.find({ type: 'Text', text: 'PRs Loai(7) Jean(3)' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'CI failed: test (py3.10)' })).toBeDefined()
    expect(await ui.find({ key: 'proof-yes' })).toBeUndefined()
    await ui.unmount()
  }
  onlyTheHelper(calls)
})

test('all tasks done asks for the proof and Yes opens it in the pane', async ($, on) => {
  const clock = mock.clock(on)
  const calls = world(on, { level: 'fresh', proof: true })
  await $.tool.call({ tool: 'TodoWrite', todos: [...TODOS_HALF] })
  await $.tool.call({ tool: 'TodoWrite', todos: [...TODOS_DONE] })
  await clock.settle()
  const ui = await $.ui.mount({ plugin: 'mizan', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  expect(await ui.find({ type: 'Text', text: 'Done. Show me the proof?' })).toBeDefined()
  await ui.press({ key: 'proof-yes' })
  expect(calls.opened).toContain('mizan')
  expect(calls.runs.some(run => run.argv[2] === 'proof')).toBe(true)
  expect(await ui.find({ key: 'proof-yes' })).toBeUndefined()
  await ui.unmount()
  const pane = await $.ui.mount({ plugin: 'mizan', surface: 'terminal', component: 'Pane', props: PANE, requestId: 'mizan' })
  expect(await pane.find({ type: 'Text', text: 'All checks passed' })).toBeDefined()
  await pane.unmount()
  onlyTheHelper(calls)
})

test('no proof yet: Yes offers /itqan:proof for the person to send', async ($, on) => {
  const clock = mock.clock(on)
  const calls = world(on, { level: 'fresh', proof: false })
  await $.tool.call({ tool: 'TodoWrite', todos: [...TODOS_HALF] })
  await $.tool.call({ tool: 'TodoWrite', todos: [...TODOS_DONE] })
  await clock.settle()
  const ui = await $.ui.mount({ plugin: 'mizan', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  await ui.press({ key: 'proof-yes' })
  expect(calls.fills).toEqual(['/itqan:proof'])
  expect(await ui.find({ type: 'Text', text: /No proof yet/ })).toBeDefined()
  await ui.unmount()
})

test('full context: saves the handoff, puts /clear in the box, never clears or compacts', async ($, on) => {
  const clock = mock.clock(on)
  const calls = world(on, { level: 'full' })
  await $.classic.Stop({ stop_hook_active: false })
  await clock.settle()
  expect(calls.runs.some(run => run.argv[2] === 'handoff')).toBe(true)
  expect(calls.fills).toEqual(['/clear'])
  expect(calls.compacts).toBe(0)
  const ui = await $.ui.mount({ plugin: 'mizan', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  expect(await ui.find({ type: 'Text', text: /your work is saved\. Press Enter/ })).toBeDefined()
  await ui.unmount()
  await $.classic.Stop({ stop_hook_active: false })
  await clock.settle()
  expect(calls.fills).toEqual(['/clear']) // once per crossing
  onlyTheHelper(calls)
})

test('full context with a draft in the box: the draft stays, the band says to type /clear', async ($, on) => {
  const clock = mock.clock(on)
  const calls = world(on, { level: 'full', draft: 'half-typed question' })
  await $.classic.Stop({ stop_hook_active: false })
  await clock.settle()
  expect(calls.fills).toEqual([])
  const ui = await $.ui.mount({ plugin: 'mizan', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  expect(await ui.find({ type: 'Text', text: /Type \/clear and press Enter/ })).toBeDefined()
  await ui.unmount()
})
