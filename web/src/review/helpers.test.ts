// Parity with the Python helpers (fixtures: python -m ep_model.scripts.export_web_helpers).
import { readFileSync } from 'node:fs'
import { Chess, type Square } from 'chess.js'
import { describe, expect, it } from 'vitest'
import { combine, epMoveWeights, lichessGameAccuracy, moveAccuracyPct, volatilityWeights, winPercent } from './accuracy'
import { loadBook } from './book'
import { gameRatings, moveAccuracy, phaseGrade, phaseOf, playsLike, winProb, type RatingMeta } from './rating'
import { detectPool, fromLichessScale, toLichessScale } from './ratings'
import {
  classifyTimeClass,
  gamePhaseFromHalfMoves,
  parseClockComment,
  parseClockHeader,
  parseTimeControl,
  ratingBandFromAverage,
} from './rowgen'
import {
  bestCaptureGain,
  captureValue,
  findFastMove,
  isBrilliant,
  sacrificeHolds,
  isGreat,
  isMiss,
  materialGiven,
  outcomeBand,
  sacrificePoints,
  sacrificedPiece,
  see,
  takesHangingMaterial,
  thresholdsFor,
} from './special'
import { hangingAfter, materialWon, tacticHint } from './tactics'

const fixture = (name: string) => JSON.parse(readFileSync(new URL(`./__fixtures__/helpers_${name}.json`, import.meta.url), 'utf-8'))
const close = (a: number | null, b: number | null) => {
  if (a === null || b === null) expect(a).toBe(b)
  else expect(Math.abs(a - b)).toBeLessThan(1e-9)
}

describe('special', () => {
  const data = fixture('special')
  it('SEE, best capture and per-move material match python-chess', () => {
    let checked = 0
    for (const pos of data.positions) {
      const board = new Chess(pos.fen)
      for (const [sq, v] of Object.entries(pos.see)) expect([pos.fen, sq, see(board, sq as Square)]).toEqual([pos.fen, sq, v])
      expect([pos.fen, bestCaptureGain(board)]).toEqual([pos.fen, pos.best_capture_gain])
      for (const m of pos.moves) {
        const mv = findFastMove(board, m.uci)!
        const got = {
          uci: m.uci,
          capture_value: captureValue(mv),
          material_given: materialGiven(board, m.uci),
          sacrificed_piece: sacrificedPiece(board, m.uci),
          takes_hanging: takesHangingMaterial(board, m.uci),
          sacrifice_points: m.sacrifice_points === null ? null : sacrificePoints(board, m.uci),
          hanging_after: hangingAfter(board, mv),
          material_won: materialWon(board, mv),
        }
        expect([pos.fen, got]).toEqual([pos.fen, m])
        checked++
      }
      expect(board.fen()).toBe(new Chess(pos.fen).fen()) // helpers leave the board as it was
    }
    expect(checked).toBeGreaterThan(5000)
  }, 300_000)

  it('label rules', () => {
    const r = fixture('rules')
    for (const [a, want] of r.great) expect(isGreat(a[0], a[1], a[2], a[3], a[4], a[5], a[6])).toBe(want)
    for (const [a, want] of r.miss) expect(isMiss(a[0], a[1], a[2], a[3], a[4])).toBe(want)
    for (const [a, want] of r.brilliant) expect(isBrilliant(a[0], a[1], a[2], a[3], a[4])).toBe(want)
    for (const [elo, g] of r.thresholds) close(thresholdsFor(elo).great_gap, g)
    for (const [fen, line, want] of r.holds) expect([fen, line, sacrificeHolds(new Chess(fen), line)]).toEqual([fen, line, want])
    for (const [x, want] of r.bands) expect(outcomeBand(x)).toBe(want)
  })
})

describe('tactics', () => {
  it('hints match', () => {
    for (const c of fixture('tactics')) {
      expect([c, tacticHint(c.fen, c.played, c.best, c.mate_before, c.mate_after)]).toEqual([c, c.hint])
    }
  }, 120_000)
})

describe('book', () => {
  it('keys and moves match python-chess', () => {
    const bin = readFileSync(new URL('../../public/data/book.bin', import.meta.url))
    const book = loadBook(
      bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength) as ArrayBuffer,
      JSON.parse(readFileSync(new URL('../../public/data/polyglot.json', import.meta.url), 'utf-8')),
    )
    const cases = fixture('book')
    let hits = 0
    for (const c of cases) {
      expect([c.fen, book.key(c.fen).toString(16).padStart(16, '0')]).toEqual([c.fen, c.key])
      expect([c.fen, book.movesFor(c.fen)]).toEqual([c.fen, c.moves])
      hits += c.moves.length > 0 ? 1 : 0
    }
    expect(hits).toBeGreaterThan(100)
  }, 120_000)
})

describe('rowgen and ratings', () => {
  const r = fixture('rowgen')
  it('rowgen', () => {
    for (const [tc, want] of r.time_control) expect(parseTimeControl(tc)).toEqual(want)
    for (const [x, want] of r.time_class) expect(classifyTimeClass(x)).toBe(want)
    for (const [x, want] of r.rating_band) expect(ratingBandFromAverage(x)).toBe(want)
    for (const [x, want] of r.phase) expect(gamePhaseFromHalfMoves(x)).toBe(want)
    for (const [c, want] of r.clock_comment) expect(parseClockComment(c)).toBe(want)
    for (const [h, want] of r.clock_header) expect(parseClockHeader(h)).toBe(want)
  })
  it('ratings', () => {
    const q = fixture('ratings')
    for (const [elo, pool, tc, want] of q.to) expect([elo, pool, tc, toLichessScale(elo, pool, tc)]).toEqual([elo, pool, tc, want])
    for (const [elo, pool, tc, want] of q.from) expect([elo, pool, tc, fromLichessScale(elo, pool, tc)]).toEqual([elo, pool, tc, want])
    for (const [h, want] of q.pool) expect(detectPool(h)).toBe(want)
  })
})

describe('accuracy', () => {
  const a = fixture('accuracy')
  it('formulas', () => {
    for (const [c, want] of a.win_percent) close(winPercent(c), want)
    for (const [d, b, want] of a.move_accuracy) close(moveAccuracyPct(d, b), want)
    for (const v of a.volatility) volatilityWeights(v.win).forEach((w, i) => close(w, v.weights[i]))
    for (const c of a.combine) close(combine(c.accs, c.weights), c.result)
    for (const e of a.ep_weights) epMoveWeights(e.ep).forEach((w, i) => close(w, e.weights[i]))
    for (const g of a.games) {
      const got = lichessGameAccuracy(g.cps, g.white_starts)
      close(got.white, g.result.white)
      close(got.black, g.result.black)
    }
  })
})

describe('rating estimate and phases', () => {
  const r = fixture('rating')
  const meta = JSON.parse(readFileSync(new URL('../../public/data/models/rating.json', import.meta.url), 'utf-8')) as RatingMeta
  it('curves', () => {
    for (const [c, want] of r.win_prob) close(winProb(c), want)
    for (const [x, want] of r.move_accuracy) close(moveAccuracy(x), want)
    for (const [tc, acc, want] of r.plays_like) close(playsLike(acc, tc, meta), want)
  })
  it('game ratings', () => {
    for (const e of r.estimates) {
      const got = gameRatings(meta, e.accuracy, e.ratings, e.moves, e.time_class)
      for (const side of ['white', 'black'] as const) {
        if (e.result[side] === null) expect(got[side]).toBeNull()
        else close(got[side]!.plays_like, e.result[side].plays_like)
      }
    }
  })
  it('phase of and phase grade', () => {
    for (const [fen, ply, inBook, want] of r.phase_of) expect(phaseOf(new Chess(fen), ply, inBook)).toBe(want)
    for (const g of r.phase_grade) {
      const got = phaseGrade(g.moves)
      if (g.result === null) expect(got).toBeNull()
      else {
        expect(got!.grade).toBe(g.result.grade)
        expect(got!.moves).toBe(g.result.moves)
        close(got!.accuracy, g.result.accuracy)
      }
    }
  })
})
