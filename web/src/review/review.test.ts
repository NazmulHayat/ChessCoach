// Parity: the TypeScript review must reproduce Python's reviews of benchmark games, given the same engine fields
// (fixture: python -m ep_model.scripts.export_web_reviews).
import { afterEach, describe, expect, it } from 'vitest'
import { loadBook } from './book'
import { loadTreeModel, type TreeModelJson } from './lgbm'
import type { RatingMeta } from './rating'
import { reviewGame, type Models } from './review'
import type { EngineFields } from './types'

const fs = (await import(/* @vite-ignore */ 'node:fs' as string)) as {
  readFileSync(p: URL, enc?: string): string | { buffer: ArrayBuffer; byteOffset: number; byteLength: number }
}
const readJson = <T,>(rel: string): T => JSON.parse(fs.readFileSync(new URL(rel, import.meta.url), 'utf8') as string) as T

interface Fixture {
  name: string
  pgn: string
  use_book: boolean
  engine: Record<string, EngineFields>
  expected: {
    moves: Record<string, unknown>[]
    summary: Record<string, Record<string, unknown>>
    white_ep_by_ply: number[]
    key_moments: number[]
    [k: string]: unknown
  }
}

const fixtures = readJson<Fixture[]>('./__fixtures__/reviews.json')
const bin = fs.readFileSync(new URL('../../public/data/book.bin', import.meta.url)) as { buffer: ArrayBuffer; byteOffset: number; byteLength: number }
const models: Models = {
  board: loadTreeModel(readJson<TreeModelJson>('../../public/data/models/board.json')),
  chances: loadTreeModel(readJson<TreeModelJson>('../../public/data/models/chances.json')),
  rating: readJson<RatingMeta>('../../public/data/models/rating.json'),
  book: loadBook(bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength), readJson<string[]>('../../public/data/polyglot.json')),
}

const EXACT = ['san', 'uci', 'mover', 'best_uci', 'best_san', 'best_line_san', 'second_san', 'ep_label', 'base_label', 'lichess_label',
  'tactic', 'sacrifice', 'sacrifice_piece', 'capture', 'phase', 'clock_sec']
const CLOSE = ['ep_best', 'ep_after', 'ep_loss', 'ep_second', 'lichess_loss', 'accuracy', 'weight', 'cp_before']

function close(got: unknown, want: unknown, what: string) {
  if (want === null || want === undefined) expect(got ?? null, what).toBeNull()
  else expect(Math.abs((got as number) - (want as number)), what).toBeLessThan(1e-7)
}

describe('review matches Python', () => {
  // Each review is synchronous and CPU-heavy; yield to the event loop between them so Vitest's worker can
  // answer the runner's RPC calls (otherwise it reports "Timeout calling onTaskUpdate").
  afterEach(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
  for (const fx of fixtures) {
    it(fx.name, async () => {
      const analyse = async (fens: string[]) => fens.map((f) => fx.engine[f])
      const r = await reviewGame(fx.pgn, models, analyse, { depth: 17, useBook: fx.use_book })
      const want = fx.expected
      expect(r.moves.length).toBe(want.moves.length)
      r.moves.forEach((m, i) => {
        const w = want.moves[i]
        const rec = m as unknown as Record<string, unknown>
        for (const k of EXACT) expect(rec[k], `${fx.name} ply ${i + 1} ${k}`).toEqual(w[k])
        for (const k of CLOSE) close(rec[k], w[k], `${fx.name} ply ${i + 1} ${k}`)
      })
      r.white_ep_by_ply.forEach((v, i) => close(v, want.white_ep_by_ply[i], `white_ep ${i}`))
      for (const side of ['white', 'black'] as const) {
        const s = r.summary[side]
        const ws = want.summary[side]
        close(s.accuracy, ws.accuracy, `${side} accuracy`)
        expect(s.labels, `${side} labels`).toEqual(ws.labels)
        expect(s.estimated_rating, `${side} rating`).toEqual(ws.estimated_rating)
        for (const ph of ['opening', 'middlegame', 'endgame'] as const) {
          const a = s.phases[ph]
          const b = (ws.phases as Record<string, { accuracy: number; grade: string; moves: number } | null>)[ph]
          if (!b) expect(a).toBeNull()
          else {
            close(a?.accuracy, b.accuracy, `${side} ${ph} accuracy`)
            expect(a?.grade).toBe(b.grade)
          }
        }
      }
      expect(r.key_moments).toEqual(want.key_moments)
    }, 120_000)
  }
})
