// mizan's state contract: the values its band and pane draw from.

export type MizanTone = 'ok' | 'warn' | 'bad' | 'info' | 'dim' | 'plain'
export type MizanSegment = { text: string; tone: MizanTone }
export type MizanSection = { title: string; lines: MizanSegment[] }
export type MizanLevel = 'fresh' | 'mid' | 'full' | ''
export type MizanLabels = {
  full_saved: string
  full_type: string
  full_nosave: string
  full_type_nosave: string
  proof_ask: string
  yes: string
  no: string
  close: string
  details: string
  proof_missing: string
  proof_title: string
}
export type MizanAlert = { key: string; text: string }
export type MizanView = {
  band: MizanSegment[][]
  detail: MizanSection[]
  labels: MizanLabels
  level: MizanLevel
  alerts: MizanAlert[]
  proofAvailable: boolean
}
export type MizanAsk = { kind: 'none' | 'proof' | 'full' | 'missing'; text: string }
export type MizanTask = { id: string; text: string; active: string; status: 'pending' | 'in_progress' | 'completed' }
export type MizanFlow = { fullDone: boolean; midTurns: number }

declare module 'claude-code' {
  interface PluginState {
    mizan: {
      view: MizanView | null
      pane: 'detail' | 'proof'
      proof: MizanSection[]
      ask: MizanAsk
      tasks: MizanTask[]
      flow: MizanFlow
    }
  }
}
