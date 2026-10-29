// Game rating ("played like") and phase grades: port of ep_model/review/rating_estimate.py.
import type { Chess } from 'chess.js'
import { combine } from './accuracy'

export const MIN_MOVES = 10
export const MAX_SWING = 400
export const OPENING_PLIES = 20
export const ENDGAME_MAX_PIECES = 6
export const PHASE_GRADES: [number, string][] = [
  [95, 'best'],
  [85, 'excellent'],
  [75, 'good'],
  [60, 'inaccuracy'],
  [45, 'mistake'],
]

/** Accuracy curves per time class and our accuracy offset (rating.json, from rating_estimate.json). */
export interface RatingMeta {
  curves: Record<string, { accuracy: number[]; rating: number[] }>
  offset: Record<string, number>
  spread: Record<string, number>
}

export interface RatingEstimate {
  plays_like: number
}

export function winProb(cpMover: number): number {
  const cp = Math.max(-1000, Math.min(1000, cpMover))
  return 1 / (1 + Math.exp(-0.00368208 * cp))
}

export function moveAccuracy(loss: number): number {
  return Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * loss * 100) - 3.1669))
}

/** numpy.interp: linear interpolation on increasing xp, clamped to the end values. */
export function interp(x: number, xp: number[], fp: number[]): number {
  const n = xp.length
  if (x <= xp[0]) return fp[0]
  if (x >= xp[n - 1]) return fp[n - 1]
  let lo = 0
  let hi = n - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (xp[mid] <= x) lo = mid
    else hi = mid
  }
  if (x === xp[lo]) return fp[lo]
  const slope = (fp[lo + 1] - fp[lo]) / (xp[lo + 1] - xp[lo])
  return slope * (x - xp[lo]) + fp[lo]
}

export const EDGE_BINS = 3

/** Rating whose typical game in this time class is played at `accuracy` (our accuracy scale). */
export function playsLike(accuracy: number, timeClass: string, meta: RatingMeta): number {
  const curve = meta.curves[timeClass] ?? meta.curves.blitz
  const offset = meta.offset[timeClass] ?? meta.offset.blitz
  const { accuracy: acc, rating } = curve
  const a = accuracy - offset
  const k = Math.min(EDGE_BINS, acc.length - 1)
  const n = acc.length - 1
  // Beyond the curve's ends, continue along the slope of its last bins (see rating_estimate.py).
  if (a < acc[0]) return rating[0] + ((a - acc[0]) * (rating[k] - rating[0])) / (acc[k] - acc[0])
  if (a > acc[n]) return rating[n] + ((a - acc[n]) * (rating[n] - rating[n - k])) / (acc[n] - acc[n - k])
  return interp(a, acc, rating)
}

/**
 * Game rating per side on the Lichess scale, unrounded; null with too few moves. Both sides are anchored on
 * the game's average rating, so the more accurate player never gets the lower game rating.
 */
export function gameRatings(
  meta: RatingMeta,
  accuracy: Record<'white' | 'black', number>,
  ratings: Record<'white' | 'black', number>,
  moves: Record<'white' | 'black', number>,
  timeClass: string,
): Record<'white' | 'black', RatingEstimate | null> {
  const anchor = (ratings.white + ratings.black) / 2
  const one = (side: 'white' | 'black'): RatingEstimate | null => {
    if (moves[side] < MIN_MOVES) return null
    const x = playsLike(accuracy[side], timeClass, meta)
    const spread = meta.spread[timeClass] ?? meta.spread.blitz
    return { plays_like: anchor + MAX_SWING * Math.tanh((x - anchor) / spread) }
  }
  return { white: one('white'), black: one('black') }
}

/** Phase of the position (before the move at 1-based `ply`). */
export function phaseOf(board: Chess, ply: number, inBook: boolean): string {
  let pieces = 0
  for (const row of board.board()) for (const p of row) if (p && 'qrbn'.includes(p.type)) pieces++
  if (pieces <= ENDGAME_MAX_PIECES) return 'endgame'
  if (ply <= OPENING_PLIES || inBook) return 'opening'
  return 'middlegame'
}

export interface PhaseGrade {
  accuracy: number
  grade: string
  moves: number
}

/** Accuracy and grade for one player's moves in one phase; null if they made no moves there. */
export function phaseGrade(moves: { accuracy: number; weight?: number; ep_label: string }[]): PhaseGrade | null {
  if (moves.length === 0) return null
  const acc = combine(
    moves.map((m) => m.accuracy),
    moves.map((m) => m.weight ?? 1),
  )!
  const grade = moves.every((m) => m.ep_label === 'book') ? 'book' : (PHASE_GRADES.find(([limit]) => acc >= limit)?.[1] ?? 'blunder')
  return { accuracy: acc, grade, moves: moves.length }
}
