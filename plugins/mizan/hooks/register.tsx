// mizan's display: the band above the prompt, the /mizan pane, and the context-full flow.
//
// The mod draws and asks; it decides nothing about what to show. Every word and figure comes from
// the Python core, bin/mizan, the one program this module runs, always with one of the fixed
// subcommands in HELPER and the session's figures as JSON on stdin. No model calls.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type {
  MizanAlert,
  MizanAsk,
  MizanLabels,
  MizanLevel,
  MizanSection,
  MizanSegment,
  MizanTask,
  MizanTone,
  MizanView,
} from '../types'

const PANE = 'mizan'
const TICK_MS = 15_000
const MIN_GAP_MS = 3_000
const MID_EVERY = 3

// The fixed command list: python3 <plugin>/bin/mizan <one of these>.
const HELPER = {
  status: ['status', '--json', '--stdin', '--publish'],
  handoff: ['handoff'],
  proof: ['proof', '--json'],
} as const
type Helper = keyof typeof HELPER
type Json = Record<string, unknown>

const NO_ASK: MizanAsk = { kind: 'none', text: '' }
const view = atom({ plugin: 'mizan', key: 'view' } as const, null)
const pane = atom({ plugin: 'mizan', key: 'pane' } as const, 'detail')
const proof = atom({ plugin: 'mizan', key: 'proof' } as const, [])
const ask = atom({ plugin: 'mizan', key: 'ask' } as const, NO_ASK)
const tasks = atom({ plugin: 'mizan', key: 'tasks' } as const, [])
const flow = atom({ plugin: 'mizan', key: 'flow' } as const, { fullDone: false, midTurns: 0 })

const TONE: Record<MizanTone, { color?: string; dimColor?: boolean }> = {
  ok: { color: 'success' },
  warn: { color: 'warning' },
  bad: { color: 'error' },
  info: { color: 'suggestion' },
  dim: { dimColor: true },
  plain: {},
}
const LEVELS: readonly MizanLevel[] = ['fresh', 'mid', 'full']

let busy = false
let lastTick = 0
let transcript = ''
let alerted = new Set<string>()
let wasAllDone: boolean | undefined

async function helper($: EngineInterface, which: Helper, input: Json): Promise<Json | null> {
  const argv = ['python3', `${$.plugin.root}/bin/mizan`, ...HELPER[which]]
  try {
    const ran = await $.process.run(argv, {
      stdin: JSON.stringify(input),
      timeoutMs: which === 'handoff' ? 70_000 : 25_000,
    })
    if (ran.exitCode !== 0) return null
    const parsed: unknown = JSON.parse(ran.stdout)
    return parsed !== null && typeof parsed === 'object' ? (parsed as Json) : null
  } catch {
    return null
  }
}

function toView(out: Json): MizanView | null {
  const { band, detail, labels, alerts } = out
  if (!Array.isArray(band) || !Array.isArray(detail) || labels === null || typeof labels !== 'object') {
    return null
  }
  const level = String((out.context as { level?: string } | undefined)?.level ?? '') as MizanLevel
  return {
    band: band as MizanSegment[][],
    detail: detail as MizanSection[],
    labels: labels as MizanLabels,
    level: LEVELS.includes(level) ? level : '',
    alerts: Array.isArray(alerts) ? (alerts as MizanAlert[]) : [],
    proofAvailable: (out.proof as { available?: boolean } | undefined)?.available === true,
    why: out.why === true,
    fix: out.fix === true,
  }
}

function alert($: EngineInterface, now: MizanView): void {
  for (const one of now.alerts) {
    if (!alerted.has(one.key)) $.ui.toast(one.text, { timeoutMs: 10_000 })
  }
  alerted = new Set(now.alerts.map(one => one.key))
}

async function tick($: EngineInterface): Promise<MizanView | null> {
  if (busy) return read($, view)
  busy = true
  try {
    const usage = await $.session.usage()
    const agents = (await $.agent.list())
      .filter(agent => agent.status === 'running')
      .map(agent => ({ type: agent.type, description: agent.description }))
    const out = await helper($, 'status', {
      session: await $.session.id(),
      cwd: await $.session.cwd(),
      transcript,
      source: 'mod',
      context: {
        percent: usage.context.percent ?? null,
        tokens: usage.context.tokens ?? null,
        window: usage.context.window,
      },
      cost: { usd: usage.cost?.usd ?? null },
      agents,
      tasks: { items: await read($, tasks) },
    })
    const next = out === null ? null : toView(out)
    if (next === null) return read($, view)
    await update($, view, () => next)
    alert($, next)
    return next
  } finally {
    busy = false
    lastTick = await $.clock.now()
  }
}

function soon($: EngineInterface): void {
  $.clock.after(0, () => {
    void tick($)
  })
}

async function saveHandoff($: EngineInterface): Promise<boolean> {
  const out = await helper($, 'handoff', {
    session: await $.session.id(),
    transcript,
    cwd: await $.session.cwd(),
  })
  return out?.saved === true
}

// Puts text in the prompt box for the person to send, never over a draft they are typing.
async function offer($: EngineInterface, text: string): Promise<boolean> {
  if ((await $.prompt.read()).text.trim() !== '') return false
  return (await $.prompt.fill({ text })).isFilled
}

// After each reply: refresh the handoff at mid; at full save it and offer /clear, once.
async function balance($: EngineInterface): Promise<void> {
  const now = await tick($)
  if (now === null) return
  const state = await read($, flow)
  if (now.level === 'mid') {
    const midTurns = state.midTurns + 1
    await update($, flow, () => ({ fullDone: false, midTurns }))
    if (midTurns % MID_EVERY === 0) await saveHandoff($)
  } else if (now.level === 'full' && !state.fullDone) {
    await update($, flow, current => ({ ...current, fullDone: true }))
    const saved = await saveHandoff($)
    const filled = await offer($, '/clear')
    const key = saved ? (filled ? 'full_saved' : 'full_type') : filled ? 'full_nosave' : 'full_type_nosave'
    await update($, ask, () => ({ kind: 'full', text: now.labels[key] }))
  } else if (now.level === 'fresh') {
    await update($, flow, () => ({ fullDone: false, midTurns: 0 }))
  }
}

async function afterTasks($: EngineInterface): Promise<void> {
  const list = await read($, tasks)
  const allDone = list.length > 0 && list.every(task => task.status === 'completed')
  if (allDone && wasAllDone === false) {
    const question: MizanAsk = {
      kind: 'proof',
      text: (await read($, view))?.labels.proof_ask ?? 'Done. Show me the proof?',
    }
    await update($, ask, current => (current.kind === 'full' ? current : question))
  }
  wasAllDone = allDone
  soon($)
}

async function loadProof($: EngineInterface): Promise<boolean> {
  const out = await helper($, 'proof', {})
  if (out === null || !Array.isArray(out.sections)) return false
  await update($, proof, () => out.sections as MizanSection[])
  await update($, pane, () => 'proof')
  return out.available === true
}

async function answerProof($: EngineInterface): Promise<void> {
  await update($, ask, () => NO_ASK)
  if (await loadProof($)) {
    await $.ui.open({ id: PANE, title: 'mizan' })
    return
  }
  const labels = (await read($, view))?.labels
  await offer($, '/itqan:proof')
  await update($, ask, () => ({ kind: 'missing', text: labels?.proof_missing ?? '' }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'mizan',
      description: 'Session balance: branch, PRs, CI, device, context, cost, agents and tasks',
      argumentHint: '[proof]',
    })
    $.clock.every(TICK_MS, () => {
      void tick($)
    })
    soon($)
    return next(e)
  })

  // Observers: a failure here must never hold up the session, so the catch hands the event on.
  on('classic.SessionStart', ($, e, next) => {
    transcript = e.transcript_path || transcript
    return next(e)
  }).catch(($, e, next) => next(e))

  on('classic.Stop', ($, e, next) => {
    transcript = e.transcript_path || transcript
    $.clock.after(0, () => {
      void balance($)
    })
    return next(e)
  }).catch(($, e, next) => next(e))

  on('session.measure', async ($, e, next) => {
    if ((await $.clock.now()) - lastTick > MIN_GAP_MS) soon($)
    return next(e)
  })

  // A conversation ends (/clear, a resume, an exit): the next one starts with a clean band.
  on('session.end', async ($, e, next) => {
    transcript = ''
    wasAllDone = undefined
    await update($, ask, () => NO_ASK)
    await update($, flow, () => ({ fullDone: false, midTurns: 0 }))
    await update($, tasks, () => [])
    $.clock.after(1_000, () => {
      void tick($)
    })
    return next(e)
  })

  // Follows the main loop's task list: TodoWrite, or TaskCreate and TaskUpdate.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (e.agentId !== undefined || ran.deny !== undefined || ran.isError) return ran
    if (e.tool === 'TodoWrite') {
      const list: MizanTask[] = e.todos.map((todo, index) => ({
        id: String(index + 1),
        text: todo.content,
        active: todo.activeForm,
        status: todo.status,
      }))
      await update($, tasks, () => list)
    } else if (e.tool === 'TaskCreate') {
      const id = (ran.result as { task?: { id?: string } } | undefined)?.task?.id ?? ''
      const task: MizanTask = { id, text: e.subject, active: e.activeForm ?? '', status: 'pending' }
      await update($, tasks, list => [...list, task])
    } else if (e.tool === 'TaskUpdate') {
      const { taskId, status, subject, activeForm } = e
      await update($, tasks, list =>
        list.flatMap(task => {
          if (task.id !== taskId) return [task]
          if (status === 'deleted') return []
          return [{ ...task, text: subject ?? task.text, active: activeForm ?? task.active, status: status ?? task.status }]
        }),
      )
    } else {
      return ran
    }
    if (wasAllDone === undefined) wasAllDone = false
    await afterTasks($)
    return ran
  }).catch(($, e, next) => next(e))

  on('command.run', { command: 'mizan' }, async ($, e) => {
    const wantsProof = e.args.trim().toLowerCase() === 'proof'
    if (wantsProof) {
      await loadProof($)
    } else {
      await update($, pane, () => 'detail')
      soon($)
    }
    await $.ui.open({ id: PANE, title: 'mizan' })
    return { text: wantsProof ? 'mizan: the proof is open.' : 'mizan: the details are open.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = await read($, view)
    if (e.props.hasSurvey || now === null) return next(e)
    const question = await read($, ask)
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {now.band.map((line, row) => (
          <Box key={`line-${row}`} flexDirection="row" flexWrap="wrap">
            {line.map((part, index) => (
              <Text key={`seg-${row}-${index}`} wrap="truncate-end" {...TONE[part.tone]}>
                {index > 0 ? ' · ' : ''}
                {part.text}
              </Text>
            ))}
            {row === 0 && now.why && (
              <Button key="tabib-why" label={now.labels.why} plain onPress={() => offer($, '/tabib:diagnose')} />
            )}
            {row === 0 && now.fix && (
              <Button key="lawha-fix" label={now.labels.fix} plain onPress={() => offer($, '/lawha:check --fix')} />
            )}
          </Box>
        ))}
        {question.kind === 'proof' && (
          <Box flexDirection="row">
            <Text bold>{question.text} </Text>
            <Button key="proof-yes" label={now.labels.yes} hotkey="y" variant="primary" onPress={() => answerProof($)} />
            <Button key="proof-no" label={now.labels.no} hotkey="n" onPress={() => update($, ask, () => NO_ASK)} />
          </Box>
        )}
        {(question.kind === 'full' || question.kind === 'missing') && (
          <Box flexDirection="row">
            <Text color="warning" bold>
              {question.text}{' '}
            </Text>
            <Button key="ask-close" label={now.labels.close} role="dismiss" onPress={() => update($, ask, () => NO_ASK)} />
          </Box>
        )}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const which = await read($, pane)
    const now = await read($, view)
    const sections = which === 'proof' ? await read($, proof) : (now?.detail ?? [])
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {which === 'proof' && (
          <Button key="back" label={now?.labels.details ?? 'Details'} onPress={() => update($, pane, () => 'detail')} />
        )}
        {sections.map((section, index) => (
          <Box key={`section-${index}`} flexDirection="column" marginBottom={1}>
            <Text bold>{section.title}</Text>
            {section.lines.map((line, row) => (
              <Text key={`row-${index}-${row}`} {...TONE[line.tone]}>
                {'  '}
                {line.text}
              </Text>
            ))}
          </Box>
        ))}
      </Box>
    )
  })
}
