// Great / Miss / Brilliant rules and material helpers: port of ep_model/phase_d/special.py (see the docstrings
// there). Moves are UCI strings; the board is mutated temporarily (move + undo) and left as it was.
import { Chess, type Move, type PieceSymbol, type Square } from 'chess.js'

export const PIECE_VALUES: Record<PieceSymbol, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }
export const PIECE_NAMES: Record<PieceSymbol, string> = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' }

export const LOSING_BELOW = 0.3
export const WINNING_ABOVE = 0.7
export const GREAT_BAND_MIN_GAP = 0.05
export const SAC_MIN_POINTS = 2
export const BRILLIANT_MIN_EP_AFTER = 0.45
export const BRILLIANT_WINNING_CAP = 0.9
export const MISS_MIN_GIFT = 0.1
export const MISS_GIVE_BACK = 0.5
export const MISS_MIN_LOSS = 0.05
export const MISS_FLOOR_MARGIN = 0.05

export interface Thresholds {
  great_gap: number
  brilliant_max_loss: number
}

function lerpByElo(elo: number, lo: number, hi: number, eloLo = 1000, eloHi = 2200): number {
  const t = Math.min(1, Math.max(0, (elo - eloLo) / (eloHi - eloLo)))
  return lo + t * (hi - lo)
}

export function thresholdsFor(elo: number): Thresholds {
  return { great_gap: lerpByElo(elo, 0.1, 0.15), brilliant_max_loss: lerpByElo(elo, 0.03, 0.01) }
}

export function outcomeBand(ep: number): number {
  return ep < LOSING_BELOW ? 0 : ep > WINNING_ABOVE ? 2 : 1
}

// ---------- board helpers ----------

/** Squares in python-chess order: a1 = 0, b1 = 1, ..., h8 = 63. */
export const SQUARES: Square[] = Array.from({ length: 64 }, (_, i) => `${'abcdefgh'[i % 8]}${Math.floor(i / 8) + 1}` as Square)

export function squareIndex(sq: string): number {
  return sq.charCodeAt(0) - 97 + 8 * (Number(sq[1]) - 1)
}

// chess.js's public moves({ verbose: true }) builds SAN for every move (each needs a full legal-move pass),
// which made exchange evaluation ~50x slower. These helpers use its internal generator instead: same legal
// moves, no SAN. Pinned to chess.js 1.4 and covered by the Python parity tests (helpers.test.ts).

/** A legal move as chess.js generates it internally (0x88 squares, bit flags). */
export interface FastMove {
  color: 'w' | 'b'
  from: number
  to: number
  piece: PieceSymbol
  captured?: PieceSymbol
  promotion?: PieceSymbol
  flags: number
}

interface ChessInternals {
  _moves(opts?: { legal?: boolean; square?: string; piece?: string }): FastMove[]
  _makeMove(m: FastMove): void
  _undoMove(): unknown
}

const FLAG_CAPTURE = 2
const FLAG_EP = 8

const internals = (board: Chess) => board as unknown as ChessInternals

/** 0x88 index -> 'e4'. */
export function algebraic(i: number): Square {
  return `${'abcdefgh'[i & 15]}${8 - (i >> 4)}` as Square
}

export function fastUci(m: FastMove): string {
  return algebraic(m.from) + algebraic(m.to) + (m.promotion ?? '')
}

export function legalMoves(board: Chess, square?: Square): FastMove[] {
  return internals(board)._moves({ legal: true, square })
}

export function findFastMove(board: Chess, uci: string): FastMove | null {
  return legalMoves(board, uci.slice(0, 2) as Square).find((m) => fastUci(m) === uci) ?? null
}

export function makeMove(board: Chess, m: FastMove): void {
  internals(board)._makeMove(m)
}

export function undoMove(board: Chess): void {
  internals(board)._undoMove()
}

export function uciOf(m: Move): string {
  return m.from + m.to + (m.promotion ?? '')
}

/** The legal move for a UCI string, with SAN (null if illegal). */
export function findMove(board: Chess, uci: string): Move | null {
  return board.moves({ square: uci.slice(0, 2) as Square, verbose: true }).find((m) => uciOf(m) === uci) ?? null
}

/** Material won by the move itself: the captured piece plus any promotion gain. */
export function captureValue(m: Move | FastMove): number {
  let value = 0
  if (isEnPassant(m)) value = PIECE_VALUES.p
  else if (m.captured) value = PIECE_VALUES[m.captured]
  if (m.promotion) value += PIECE_VALUES[m.promotion] - PIECE_VALUES.p
  return value
}

function isEnPassant(m: Move | FastMove): boolean {
  return typeof m.flags === 'number' ? (m.flags & FLAG_EP) !== 0 : m.flags.includes('e')
}

export function isCapture(m: Move | FastMove): boolean {
  return typeof m.flags === 'number' ? (m.flags & (FLAG_CAPTURE | FLAG_EP)) !== 0 : m.flags.includes('c') || m.flags.includes('e')
}

/**
 * Static exchange on `square` for the side to move, least valuable attacker first. Ties go to the move
 * python-chess generates first: higher from-square (it scans pieces from h8 down), queen promotion first.
 */
export function see(board: Chess, square: Square): number {
  if (!board.get(square)) return 0
  const attackers = board.attackers(square, board.turn())
  if (attackers.length === 0) return 0
  const target = squareIndex(square)
  let move: FastMove | null = null
  let key: [number, number, number] | null = null
  for (const from of attackers) {
    for (const m of legalMoves(board, from)) {
      if (squareIndex(algebraic(m.to)) !== target) continue
      const k: [number, number, number] = [PIECE_VALUES[m.piece] || 100, -(m.promotion ? PIECE_VALUES[m.promotion] : 0), -squareIndex(from)]
      if (key === null || k[0] < key[0] || (k[0] === key[0] && (k[1] < key[1] || (k[1] === key[1] && k[2] < key[2])))) {
        move = m
        key = k
      }
    }
  }
  if (!move) return 0
  const gain = captureValue(move)
  makeMove(board, move)
  try {
    return Math.max(0, gain - see(board, square))
  } finally {
    undoMove(board)
  }
}

/** Most material the side to move can win right now by a capture sequence on one square, and where. */
export function bestCaptureGain(board: Chess): [number, Square | null] {
  let best = 0
  let where: Square | null = null
  const them = board.turn() === 'w' ? 'b' : 'w'
  for (const sq of SQUARES) {
    const p = board.get(sq)
    if (!p || p.color !== them || p.type === 'k') continue
    const g = see(board, sq)
    if (g > best) {
      best = g
      where = sq
    }
  }
  return [best, where]
}

/** Name of the mover's piece the opponent can win after the move ("queen", "knight", ...). */
export function sacrificedPiece(board: Chess, uci: string): string | null {
  const m = findFastMove(board, uci)
  if (!m) return null
  makeMove(board, m)
  try {
    const [, where] = bestCaptureGain(board)
    return where ? PIECE_NAMES[board.get(where)!.type] : null
  } finally {
    undoMove(board)
  }
}

function materialGivenMove(board: Chess, m: FastMove): number {
  const taken = captureValue(m)
  makeMove(board, m)
  let threat: number
  try {
    if (board.isCheckmate()) return 0
    threat = bestCaptureGain(board)[0]
  } finally {
    undoMove(board)
  }
  return threat - taken
}

/** Points the mover stands to lose with the move: what the opponent can then win, minus what it captured. */
export function materialGiven(board: Chess, uci: string): number {
  const m = findFastMove(board, uci)
  return m ? materialGivenMove(board, m) : 0
}

/** Material sacrificed relative to the safest legal alternative; 0 below SAC_MIN_POINTS. */
export function sacrificePoints(board: Chess, uci: string): number {
  const legal = legalMoves(board)
  const m = legal.find((x) => fastUci(x) === uci)
  if (!m) return 0
  const given = materialGivenMove(board, m)
  if (given < SAC_MIN_POINTS) return 0
  const others = legal.filter((x) => fastUci(x) !== uci)
  if (others.length === 0) return 0
  let safest = Infinity
  for (const o of others) safest = Math.min(safest, materialGivenMove(board, o))
  return given - safest >= SAC_MIN_POINTS ? given : 0
}

/** The move captures where the most material is simply there for the taking (SEE gain >= minGain). */
export function takesHangingMaterial(board: Chess, uci: string, minGain = 2): boolean {
  const m = findFastMove(board, uci)
  if (!m || !isCapture(m)) return false
  const [gain, where] = bestCaptureGain(board)
  return gain >= minGain && algebraic(m.to) === where
}

// ---------- label rules (mover's point of view) ----------

export function isGreat(
  isBest: boolean,
  epBest: number,
  epSecond: number | null,
  elo: number,
  legalMoves: number,
  isObviousCapture: boolean,
  givesMate = false,
): boolean {
  if (!isBest || epSecond === null || legalMoves < 2 || isObviousCapture || givesMate) return false
  const gap = epBest - epSecond
  if (gap >= thresholdsFor(elo).great_gap) return true
  return gap >= GREAT_BAND_MIN_GAP && outcomeBand(epBest) > outcomeBand(epSecond)
}

export function isMiss(
  isBest: boolean,
  epLoss: number,
  epAfter: number,
  oppPrevLoss: number | null,
  moverEpBeforeGift: number | null,
): boolean {
  if (isBest || oppPrevLoss === null || moverEpBeforeGift === null || oppPrevLoss < MISS_MIN_GIFT) return false
  if (epLoss < Math.max(MISS_MIN_LOSS, MISS_GIVE_BACK * oppPrevLoss)) return false
  return epAfter >= moverEpBeforeGift - MISS_FLOOR_MARGIN
}

export function isBrilliant(epLoss: number, epAfter: number, epSecond: number | null, elo: number, sacPoints: number): boolean {
  if (sacPoints < SAC_MIN_POINTS || epLoss > thresholdsFor(elo).brilliant_max_loss) return false
  if (epAfter < BRILLIANT_MIN_EP_AFTER) return false
  return epSecond === null || epSecond < BRILLIANT_WINNING_CAP
}
