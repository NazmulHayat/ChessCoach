// UCI protocol handling for Stockfish, shared by the browser worker pool and node tests. Builds the same
// fields as the Python reference (ep_model/review/engine_pool.analysis_fields): per multipv line, every
// "info" line is merged into the previous one, as python-chess does, so the last score / pv / depth win.

import type { EngineFields } from '../review/types'

export const PV_LEN = 8

/** One multipv line after merging all its info lines. */
export interface PvLine {
  depth: number | null
  kind: 'cp' | 'mate' | null
  value: number | null
  pv: string[] | null
}

/** Parsed fields of one "info" line (only what we use). null when the line isn't an info line. */
export interface InfoLine {
  multipv: number
  depth?: number
  kind?: 'cp' | 'mate'
  value?: number
  pv?: string[]
}

const noNegZero = (x: number): number => (x === 0 ? 0 : x)

export function parseInfo(line: string): InfoLine | null {
  if (!line.startsWith('info ')) return null
  const t = line.split(/\s+/)
  const out: InfoLine = { multipv: 1 }
  for (let i = 1; i < t.length; i++) {
    const tok = t[i]
    if (tok === 'string') break // free text to end of line
    if (tok === 'depth') out.depth = parseInt(t[++i], 10)
    else if (tok === 'multipv') out.multipv = parseInt(t[++i], 10)
    else if (tok === 'score') {
      const kind = t[++i]
      const value = parseInt(t[++i], 10)
      if ((kind === 'cp' || kind === 'mate') && !Number.isNaN(value)) {
        out.kind = kind
        out.value = value
      }
      if (t[i + 1] === 'lowerbound' || t[i + 1] === 'upperbound') i++
    } else if (tok === 'pv') {
      out.pv = t.slice(i + 1).filter((m) => m.length > 0)
      break
    }
  }
  return out
}

/** Collects one search's output; feed() returns true once "bestmove" arrives. */
export class SearchAccumulator {
  lines: PvLine[] = []

  feed(line: string): boolean {
    if (line.startsWith('bestmove')) return true
    const info = parseInfo(line)
    if (!info) return false
    const k = info.multipv - 1
    while (this.lines.length <= k) this.lines.push({ depth: null, kind: null, value: null, pv: null })
    const cur = this.lines[k]
    if (info.depth !== undefined) cur.depth = info.depth
    if (info.kind !== undefined) {
      cur.kind = info.kind
      cur.value = info.value ?? null
    }
    if (info.pv !== undefined) cur.pv = info.pv
    return false
  }
}

function stmScore(line: PvLine | undefined): { cp: number | null; mate: number | null } {
  if (!line || line.kind === null || line.value === null) return { cp: null, mate: null }
  return line.kind === 'cp' ? { cp: noNegZero(line.value), mate: null } : { cp: null, mate: noNegZero(line.value) }
}

/** EngineFields for `fen` from a finished search (same rules as analysis_fields + extract_eval_fields). */
export function fieldsFromSearch(fen: string, acc: SearchAccumulator): EngineFields {
  const sign = fen.split(' ')[1] === 'b' ? -1 : 1
  const top = acc.lines[0]
  const s = stmScore(top)
  const pv = top?.pv ?? []
  const second = acc.lines[1]
  const hasSecond = !!(second && second.pv && second.pv.length > 0)
  const s2 = hasSecond ? stmScore(second) : { cp: null, mate: null }
  return {
    eval_cp_white: s.cp === null ? null : noNegZero(sign * s.cp),
    mate_white: s.mate === null ? null : noNegZero(sign * s.mate),
    eval_cp_stm: s.cp,
    mate_stm: s.mate,
    eval_depth: top?.depth ?? null,
    best_uci: pv.length ? pv[0] : null,
    pv_uci: pv.slice(0, PV_LEN),
    second_uci: hasSecond ? second!.pv![0] : null,
    second_cp_stm: s2.cp,
    second_mate_stm: s2.mate,
  }
}

/** Minimal transport to one engine instance (a Web Worker, or the node loader in tests). */
export interface EngineTransport {
  send(cmd: string): void
  onLine(fn: (line: string) => void): void
}

/** Drives one engine: init once, then one search at a time. */
export class UciEngine {
  private waiter: ((line: string) => boolean) | null = null
  private transport: EngineTransport

  constructor(transport: EngineTransport) {
    this.transport = transport
    transport.onLine((line) => {
      if (this.waiter && this.waiter(line)) this.waiter = null
    })
  }

  private until(cmds: string[], done: (line: string) => boolean): Promise<void> {
    return new Promise((resolve) => {
      this.waiter = (line) => {
        if (done(line)) {
          resolve()
          return true
        }
        return false
      }
      for (const c of cmds) this.transport.send(c)
    })
  }

  async init(hashMb = 32, multipv = 2): Promise<void> {
    await this.until(['uci'], (l) => l === 'uciok')
    this.transport.send(`setoption name Hash value ${hashMb}`)
    this.transport.send(`setoption name MultiPV value ${multipv}`)
    await this.until(['isready'], (l) => l === 'readyok')
  }

  /** Cleared engine per position (ucinewgame), so the result depends only on (fen, depth). */
  async analyse(fen: string, depth: number): Promise<EngineFields> {
    const acc = new SearchAccumulator()
    await this.until(['ucinewgame', 'isready'], (l) => l === 'readyok')
    await this.until([`position fen ${fen}`, `go depth ${depth}`], (l) => acc.feed(l))
    return fieldsFromSearch(fen, acc)
  }
}
