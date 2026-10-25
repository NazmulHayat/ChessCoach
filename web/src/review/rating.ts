// Game rating ("played like") and phase grades: port of ep_model/phase_d/rating_estimate.py.
import type { Chess } from 'chess.js'
import { combine } from './accuracy'
import { pyRound } from './ratings'
import type { TreeModel } from './types'

export const TIME_CLASSES: Record<string, number> = { bullet: 0, blitz: 1, rapid: 2, classical: 3 }
export const BALANCED_CP = 300
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

/** Inverse tables and spread per time class, shipped inside rating.json next to the trees. */
export interface RatingMeta {
  inverse: Record<string, { score: number[]; rating: number[]; k: number }>
  posterior_sd: Record<string, number>
}

export interface RatingEstimate {
  rating: number
  low: number
  high: number
  plays_like: number
}

export function winProb(cpMover: number): number {
  const cp = Math.max(-1000, Math.min(1000, cpMover))
  return 1 / (1 + Math.exp(-0.00368208 * cp))
}

export function moveAccuracy(loss: number): number {
  return Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * loss * 100) - 3.1669))
}

/** Rating-free features of one player's moves: raw win% drop per move and |eval| (cp) before it. */
export function features(losses: number[], absCpBefore: number[], timeClass: string): number[] {
  const n = Math.max(1, losses.length)
  const acc = losses.map(moveAccuracy)
  const cps = absCpBefore.map((c) => Math.min(Math.abs(c), 1000))
  const bal = acc.filter((_, i) => i < cps.length && cps[i] < BALANCED_CP)
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)
  const meanAcc = sum(acc) / n
  return [
    meanAcc,
    losses.filter((x) => x >= 0.2).length / n,
    losses.filter((x) => x >= 0.1 && x < 0.2).length / n,
    losses.filter((x) => x >= 0.05 && x < 0.1).length / n,
    losses.filter((x) => x < 0.01).length / n,
    Math.log(n),
    sum(cps) / Math.max(1, cps.length),
    bal.length ? sum(bal) / bal.length : meanAcc,
    bal.length / n,
    TIME_CLASSES[timeClass] ?? 1,
  ]
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

/** Game rating on the Lichess scale; null with too few moves. */
export function estimateRating(
  model: TreeModel,
  meta: RatingMeta,
  losses: number[],
  absCpBefore: number[],
  timeClass: string,
  playerRating: number,
): RatingEstimate | null {
  if (losses.length < MIN_MOVES) return null
  const score = model.predictVectors([features(losses, absCpBefore, timeClass)])[0]
  const table = meta.inverse[timeClass] ?? meta.inverse.blitz
  const playsLike = interp(score, table.score, table.rating)
  const r = playerRating + table.k * (playsLike - playerRating)
  const sd = meta.posterior_sd[timeClass] ?? meta.posterior_sd.blitz
  return {
    rating: pyRound(r, -1),
    low: pyRound(r - sd, -1),
    high: pyRound(r + sd, -1),
    // FIDE's single-game performance bound (see MAX_SWING in rating_estimate.py).
    plays_like: pyRound(playerRating + Math.max(-MAX_SWING, Math.min(MAX_SWING, playsLike - playerRating)), -2),
  }
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
