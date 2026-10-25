// A pool of Stockfish 18 lite (single-threaded WASM) Web Workers implementing AnalyseFn. One worker per
// engine, positions queued across them, results in input order, identical FENs analysed once, and a cache
// by (fen, depth) so re-reviews and retry checks are free.

import type { AnalyseFn, EngineFields, ProgressFn } from '../review/types'
import { UciEngine, type EngineTransport } from './uci'

export interface EnginePoolOptions {
  size?: number
  depth: number
  hashMb?: number
  url?: string
}

export interface EnginePool {
  analyse: AnalyseFn
  close(): void
}

const ENGINE_FILE = 'engine/stockfish-18-lite-single.js'

function defaultSize(): number {
  const cores = typeof navigator !== 'undefined' && navigator.hardwareConcurrency ? navigator.hardwareConcurrency : 2
  return Math.min(8, Math.max(1, cores - 1))
}

interface Slot {
  worker: Worker
  engine: UciEngine
  ready: Promise<void>
  failed: boolean // worker error during the current job
  onError: ((e: unknown) => void) | null
  restarted: boolean
}

interface Job {
  fen: string
  resolve: (f: EngineFields) => void
  reject: (e: unknown) => void
  retried: boolean
}

export function createEnginePool(opts: EnginePoolOptions): EnginePool {
  const size = opts.size ?? defaultSize()
  const hashMb = opts.hashMb ?? 16
  const url = opts.url ?? `${import.meta.env.BASE_URL}${ENGINE_FILE}`
  const cache = new Map<string, EngineFields>() // key: depth|fen
  const pending = new Map<string, Promise<EngineFields>>()
  const queue: Job[] = []
  const idle: Slot[] = []
  const slots: Slot[] = []
  let closed = false

  function spawn(): Slot {
    const worker = new Worker(url)
    const listeners: ((line: string) => void)[] = []
    const transport: EngineTransport = {
      send: (cmd) => worker.postMessage(cmd),
      onLine: (fn) => listeners.push(fn),
    }
    worker.onmessage = (e: MessageEvent) => {
      const data = typeof e.data === 'string' ? e.data : String(e.data)
      for (const line of data.split('\n')) for (const fn of listeners) fn(line)
    }
    const engine = new UciEngine(transport)
    const slot: Slot = { worker, engine, ready: Promise.resolve(), failed: false, onError: null, restarted: false }
    worker.onerror = (e) => {
      slot.failed = true
      slot.onError?.(e)
    }
    slot.ready = engine.init(hashMb, 2)
    return slot
  }

  function replace(slot: Slot): Slot {
    slot.worker.terminate()
    const fresh = spawn()
    fresh.restarted = true
    slots[slots.indexOf(slot)] = fresh
    return fresh
  }

  function pump(): void {
    while (!closed && idle.length && queue.length) run(idle.pop()!, queue.shift()!)
  }

  async function run(slot: Slot, job: Job): Promise<void> {
    try {
      await slot.ready
      const result = await new Promise<EngineFields>((resolve, reject) => {
        slot.onError = reject
        slot.engine.analyse(job.fen, opts.depth).then(resolve, reject)
      })
      slot.onError = null
      job.resolve(result)
      idle.push(slot)
    } catch (e) {
      slot.onError = null
      // A crashed worker gets one restart; the position gets one retry.
      const next = !slot.restarted ? replace(slot) : null
      if (!job.retried) {
        job.retried = true
        queue.unshift(job)
      } else {
        job.reject(e)
      }
      if (next) idle.push(next)
    }
    pump()
  }

  function analyseOne(fen: string): Promise<EngineFields> {
    const key = `${opts.depth}|${fen}`
    const hit = cache.get(key)
    if (hit) return Promise.resolve(hit)
    const inflight = pending.get(key)
    if (inflight) return inflight
    const p = new Promise<EngineFields>((resolve, reject) => {
      queue.push({ fen, resolve, reject, retried: false })
      pump()
    }).then(
      (f) => {
        cache.set(key, f)
        pending.delete(key)
        return f
      },
      (e) => {
        pending.delete(key)
        throw e
      },
    )
    pending.set(key, p)
    return p
  }

  for (let i = 0; i < size; i++) {
    const s = spawn()
    slots.push(s)
    idle.push(s)
  }

  const analyse: AnalyseFn = async (fens: string[], progress?: ProgressFn) => {
    if (closed) throw new Error('engine pool closed')
    const unique = [...new Set(fens)]
    let done = 0
    const byFen = new Map<string, EngineFields>()
    progress?.(0, fens.length)
    const counts = new Map<string, number>()
    for (const f of fens) counts.set(f, (counts.get(f) ?? 0) + 1)
    await Promise.all(
      unique.map((fen) =>
        analyseOne(fen).then((f) => {
          byFen.set(fen, f)
          done += counts.get(fen)!
          progress?.(done, fens.length)
        }),
      ),
    )
    return fens.map((f) => byFen.get(f)!)
  }

  return {
    analyse,
    close() {
      closed = true
      for (const s of slots) s.worker.terminate()
      for (const j of queue.splice(0)) j.reject(new Error('engine pool closed'))
    },
  }
}
