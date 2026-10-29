// In-browser port of ep_model/review/review.py (review_game, score_attempt). Same rules and numbers; tested
// against Python reviews of the benchmark games (review.test.ts, fixture from scripts/export_web_reviews.py).
import { Chess, type Square } from 'chess.js'

import type { Label, Review, ReviewMove, RetryResult, Side } from '../types'
import { combine, moveAccuracyPct, volatilityWeights } from './accuracy'
import type { Book } from './book'
import { cpOrMateProxy } from './features'
import { parsePgn } from './pgn'
import { estimateRating, MAX_SWING, phaseGrade, phaseOf, type RatingMeta } from './rating'
import { detectPool, fromLichessScale, pyRound, toLichessScale } from './ratings'
import {
  classifyTimeClass,
  gamePhaseFromHalfMoves,
  parseClockComment,
  parseClockHeader,
  parseTimeControl,
  ratingBandFromAverage,
} from './rowgen'
import { isBrilliant, isGreat, isMiss, sacrificedPiece, sacrificePoints, takesHangingMaterial, thresholdsFor } from './special'
import { tacticHint } from './tactics'
import type { AnalyseFn, EngineFields, ModelRow, ProgressFn, TreeModel } from './types'

export const BOOK_MAX_PLY = 30
export const DEFAULT_ELO = 1500
export const RETRY_TOLERANCE = 0.02
const LABELS: [number, Label][] = [
  [0.02, 'excellent'],
  [0.05, 'good'],
  [0.1, 'inaccuracy'],
  [0.2, 'mistake'],
]
export const BAD_LABELS: Label[] = ['inaccuracy', 'mistake', 'blunder', 'miss']
const LICHESS_K = 0.00368208

export interface Models {
  board: TreeModel // judges moves
  chances: TreeModel // clock-aware, for the bar and graph
  rating: TreeModel & RatingMeta
  book: Book | null
}

/** A position row: model inputs plus what the review derives for it. */
export interface PositionRow extends ModelRow {
  fen: string
  terminal: number | null
  cp_stm: number
  ep_stm: number
  lichess_stm: number
  white_ep_judge: number
  white_ep_display: number
  best_uci: string | null
  best_san: string | null
  best_line_san: string[]
  second_uci: string | null
  second_san: string | null
  second_cp_stm: number | null
  second_mate_stm: number | null
  eval_depth: number | null
}

export interface ReviewResult extends Review {
  white_ep_by_ply: number[]
  white_lichess_by_ply: number[]
  rows: PositionRow[]
}

export function labelForLoss(loss: number, isEngineBest: boolean): Label {
  if (isEngineBest) return 'best'
  for (const [limit, name] of LABELS) if (loss < limit) return name
  return 'blunder'
}

export function lichessExpected(cp: number): number {
  const c = Math.max(-1000, Math.min(1000, cp))
  return 1 / (1 + Math.exp(-LICHESS_K * c))
}

/** Position identity for repetitions (python-chess _transposition_key): placement, turn, castling, legal en passant. */
function transpositionKey(board: Chess): string {
  const [placement, turn, castling] = board.fen().split(' ')
  const ep = board.moves({ verbose: true }).find((m) => m.isEnPassant())
  return `${placement} ${turn} ${castling} ${ep ? ep.to : '-'}`
}

/**
 * Expected score for the side to move when the game is over on the board, as python-chess
 * is_game_over(claim_draw=True): mate, stalemate, insufficient material, 75 / 50 moves, five- / threefold
 * repetition, including a draw claimable by announcing the next move. `since` holds the transposition keys of
 * the positions since the last irreversible move, the current one last (empty: no history, as Board(fen)).
 */
function terminalScore(board: Chess, since: string[] = []): number | null {
  if (board.isCheckmate()) return 0
  if (board.isStalemate() || board.isInsufficientMaterial()) return 0.5
  const half = Number(board.fen().split(' ')[4])
  const legal = board.moves({ verbose: true })
  if (half >= 100 && legal.length) return 0.5
  if (half >= 99 && legal.some((m) => m.piece !== 'p' && !m.captured)) return 0.5
  if (!since.length) return null
  const counts = new Map<string, number>()
  for (const k of since) counts.set(k, (counts.get(k) ?? 0) + 1)
  if ((counts.get(since[since.length - 1]) ?? 0) >= 3) return 0.5
  for (const m of legal) {
    board.move(m)
    const k = transpositionKey(board)
    board.undo()
    if ((counts.get(k) ?? 0) >= 2) return 0.5
  }
  return null
}

/** python-chess is_irreversible: a zeroing move, a move that changes castling rights, or en passant was available. */
function isIrreversible(board: Chess, uci: string): boolean {
  const legal = board.moves({ verbose: true })
  if (legal.some((m) => m.isEnPassant())) return true
  const m = legal.find((x) => x.from + x.to + (x.promotion ?? '') === uci)
  if (!m) return true
  if (m.piece === 'p' || m.captured) return true
  return m.before.split(' ')[2] !== m.after.split(' ')[2]
}

function withWhiteFields<T extends ModelRow>(row: T): T {
  const sign = row.side_to_move === 'w' ? 1 : -1
  row.eval_cp_white = row.eval_cp_stm !== null ? sign * row.eval_cp_stm : null
  row.mate_white = row.mate_stm !== null ? sign * row.mate_stm : null
  return row
}

/** `after`'s context with the opponent to move, scored as if the mover's move had eval (cp, mate) for them. */
export function counterfactualRow(after: PositionRow, cp: number | null, mate: number | null): PositionRow {
  const row: PositionRow = { ...after, terminal: null }
  if (mate !== null) {
    if (mate > 0) {
      row.eval_cp_stm = null
      row.mate_stm = -(mate - 1)
      if (mate === 1) row.terminal = 0
    } else {
      row.eval_cp_stm = null
      row.mate_stm = -mate
    }
  } else {
    row.eval_cp_stm = cp !== null ? -cp : null
    row.mate_stm = null
  }
  return withWhiteFields(row)
}

export function mirroredRow(row: PositionRow): PositionRow {
  return {
    ...row,
    side_to_move: row.side_to_move === 'w' ? 'b' : 'w',
    elo_to_move: row.elo_opponent,
    elo_opponent: row.elo_to_move,
    elo_diff: -row.elo_diff,
    eval_cp_stm: row.eval_cp_stm !== null ? -row.eval_cp_stm : null,
    mate_stm: row.mate_stm !== null ? -row.mate_stm : null,
  }
}

function sanLine(fen: string, ucis: string[]): string[] {
  const b = new Chess(fen)
  const out: string[] = []
  for (const u of ucis) {
    try {
      out.push(b.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] }).san)
    } catch {
      break
    }
  }
  return out
}

function sanOf(fen: string, uci: string | null): string | null {
  if (!uci) return null
  try {
    return new Chess(fen).move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }).san
  } catch {
    return null
  }
}

function headerElo(h: Record<string, string>, key: string): number | null {
  const v = (h[key] ?? '').trim()
  return /^-?\d+$/.test(v) ? Number(v) : null
}

export interface ReviewOptions {
  whiteElo?: number
  blackElo?: number
  ratingPool?: 'auto' | 'lichess' | 'chesscom'
  useBook?: boolean
  depth: number
  progress?: ProgressFn
}

export async function reviewGame(pgn: string, models: Models, analyse: AnalyseFn, opts: ReviewOptions): Promise<ReviewResult> {
  const game = parsePgn(pgn)
  const h = game.headers
  const wEloRaw = opts.whiteElo ?? headerElo(h, 'WhiteElo') ?? DEFAULT_ELO
  const bEloRaw = opts.blackElo ?? headerElo(h, 'BlackElo') ?? DEFAULT_ELO
  const [init, inc] = parseTimeControl(h.TimeControl ?? null)
  const timeClass = classifyTimeClass(init)
  const pool = !opts.ratingPool || opts.ratingPool === 'auto' ? detectPool(h) : opts.ratingPool
  const wElo = toLichessScale(wEloRaw, pool, timeClass)
  const bElo = toLichessScale(bEloRaw, pool, timeClass)
  const band = ratingBandFromAverage((wElo + bElo) / 2)
  const eco = h.ECO || null

  const board = new Chess(game.startFen)
  let clkW = parseClockHeader(h.WhiteClock ?? null)
  let clkB = parseClockHeader(h.BlackClock ?? null)
  const positions: PositionRow[] = []
  let since = [transpositionKey(board)]
  for (let i = 0; i <= game.moves.length; i++) {
    const whiteToMove = board.turn() === 'w'
    const [eloToMove, eloOpp] = whiteToMove ? [wElo, bElo] : [bElo, wElo]
    positions.push({
      fen: board.fen(),
      terminal: terminalScore(board, since),
      ply: i + 1,
      move_number: Number(board.fen().split(' ')[5]),
      side_to_move: whiteToMove ? 'w' : 'b',
      white_elo: wElo,
      black_elo: bElo,
      elo_to_move: eloToMove,
      elo_opponent: eloOpp,
      elo_diff: eloToMove - eloOpp,
      time_class: timeClass,
      initial_time_sec: init,
      increment_sec: inc,
      clk_white_sec: clkW,
      clk_black_sec: clkB,
      phase: gamePhaseFromHalfMoves(i),
      opening_eco: eco,
      rating_band: band,
      eval_cp_stm: null,
      mate_stm: null,
      eval_cp_white: null,
      mate_white: null,
      cp_stm: 0,
      ep_stm: 0,
      lichess_stm: 0,
      white_ep_judge: 0,
      white_ep_display: 0,
      best_uci: null,
      best_san: null,
      best_line_san: [],
      second_uci: null,
      second_san: null,
      second_cp_stm: null,
      second_mate_stm: null,
      eval_depth: null,
    })
    if (i === game.moves.length) break
    const mv = game.moves[i]
    const clkAfter = parseClockComment(mv.comment)
    const irreversible = isIrreversible(board, mv.uci)
    board.move({ from: mv.uci.slice(0, 2), to: mv.uci.slice(2, 4), promotion: mv.uci[4] })
    since = irreversible ? [transpositionKey(board)] : [...since, transpositionKey(board)]
    if (clkAfter !== null) {
      if (board.turn() === 'b') clkW = clkAfter
      else clkB = clkAfter
    }
  }

  const evals: EngineFields[] = await analyse(
    positions.map((p) => p.fen),
    opts.progress,
  )
  positions.forEach((pos, k) => {
    const ev = evals[k]
    pos.eval_cp_white = ev.eval_cp_white
    pos.mate_white = ev.mate_white
    pos.eval_cp_stm = ev.eval_cp_stm
    pos.mate_stm = ev.mate_stm
    pos.eval_depth = ev.eval_depth
    pos.best_uci = ev.best_uci ?? null
    pos.best_san = sanOf(pos.fen, pos.best_uci)
    pos.best_line_san = sanLine(pos.fen, ev.pv_uci ?? [])
    pos.second_uci = ev.second_uci ?? null
    pos.second_san = sanOf(pos.fen, pos.second_uci)
    pos.second_cp_stm = ev.second_cp_stm
    pos.second_mate_stm = ev.second_mate_stm
  })

  const ep = models.board.predictRows(positions)
  const epMirror = models.board.predictRows(positions.map(mirroredRow))
  const sameModel = models.chances === models.board
  const ch = sameModel ? ep : models.chances.predictRows(positions)
  const chMirror = sameModel ? epMirror : models.chances.predictRows(positions.map(mirroredRow))
  const whiteView = (pos: PositionRow, e: number, em: number): number => {
    if (pos.terminal !== null) return pos.side_to_move === 'w' ? pos.terminal : 1 - pos.terminal
    const stm = pos.side_to_move === 'w' ? e : 1 - e
    const mirror = pos.side_to_move === 'w' ? 1 - em : em
    return 0.5 * (stm + mirror)
  }
  positions.forEach((pos, k) => {
    const cp = cpOrMateProxy(pos.eval_cp_stm, pos.mate_stm)
    pos.cp_stm = cp
    if (pos.terminal !== null) {
      pos.ep_stm = pos.lichess_stm = pos.terminal
    } else {
      pos.ep_stm = ep[k]
      pos.lichess_stm = lichessExpected(cp)
    }
    pos.white_ep_judge = whiteView(pos, ep[k], epMirror[k])
    pos.white_ep_display = whiteView(pos, ch[k], chMirror[k])
  })

  const n = game.moves.length
  const bestRows = Array.from({ length: n }, (_, i) => counterfactualRow(positions[i + 1], positions[i].eval_cp_stm, positions[i].mate_stm))
  const bestEp = models.board.predictRows(bestRows)
  const secondIdx = Array.from({ length: n }, (_, i) => i).filter((i) => positions[i].second_uci)
  const secondRows = secondIdx.map((i) => counterfactualRow(positions[i + 1], positions[i].second_cp_stm, positions[i].second_mate_stm))
  const secondPred = models.board.predictRows(secondRows)
  const epSecondByPly = new Map<number, number>()
  secondIdx.forEach((i, k) => epSecondByPly.set(i, 1 - (secondRows[k].terminal ?? secondPred[k])))

  const book = opts.useBook === false ? null : models.book
  let inBook = book !== null
  const moves: ReviewMove[] = []
  const b = new Chess(game.startFen)
  for (let i = 0; i < n; i++) {
    const before = positions[i]
    const after = positions[i + 1]
    const uci = game.moves[i].uci
    const from = uci.slice(0, 2) as Square
    const to = uci.slice(2, 4) as Square
    const mover: Side = b.turn() === 'w' ? 'white' : 'black'
    let isBook = false
    if (inBook && book && i < BOOK_MAX_PLY) isBook = book.movesFor(b.fen()).includes(uci)
    inBook = inBook && isBook
    const phase = phaseOf(new Chess(b.fen()), i + 1, isBook)
    const legalCount = b.moves().length
    const prev = moves.length ? moves[moves.length - 1] : null
    const fenBefore = b.fen()
    const played = b.move({ from, to, promotion: uci[4] })
    const isCapture = played.isCapture() || played.isEnPassant()
    const isRecapture = prev !== null && prev.capture && to === prev.to && isCapture
    const isBest = uci === before.best_uci
    const bst = bestRows[i]
    const epBest = 1 - (bst.terminal ?? bestEp[i])
    const epAfter = 1 - after.ep_stm
    const liBest = before.lichess_stm
    const liAfter = 1 - after.lichess_stm
    const epLoss = isBest || isBook ? 0 : Math.max(0, epBest - epAfter)
    const liLoss = isBest || isBook ? 0 : Math.max(0, liBest - liAfter)
    const baseLabel: Label = isBook ? 'book' : labelForLoss(epLoss, isBest)
    const epSecond = epSecondByPly.get(i) ?? null
    const moverElo = before.elo_to_move
    let special: Label | null = null
    let sac = 0
    let sacPiece: string | null = null
    if (!isBook) {
      const alt = isBest ? epSecond : epBest
      if (epLoss <= thresholdsFor(moverElo).brilliant_max_loss) sac = sacrificePoints(new Chess(fenBefore), uci)
      if (isBrilliant(epLoss, epAfter, alt, moverElo, sac)) {
        special = 'brilliant'
        sacPiece = sacrificedPiece(new Chess(fenBefore), uci)
      } else if (
        isGreat(isBest, epBest, epSecond, moverElo, legalCount, isRecapture || takesHangingMaterial(new Chess(fenBefore), uci), b.isCheckmate())
      ) {
        special = 'great'
      } else if (prev !== null && isMiss(isBest, epLoss, epAfter, prev.ep_loss, 1 - prev.ep_best)) {
        special = 'miss'
      }
    }
    const epLabel = special ?? baseLabel
    const tactic = BAD_LABELS.includes(epLabel) ? tacticHint(before.fen, uci, before.best_uci, before.mate_stm, after.mate_stm) : null
    const bu = before.best_uci
    moves.push({
      ply: i + 1,
      move_number: before.move_number,
      mover,
      san: played.san,
      uci,
      from,
      to,
      fen_before: before.fen,
      fen_after: after.fen,
      best_uci: bu,
      best_san: before.best_san,
      best_from: bu ? bu.slice(0, 2) : null,
      best_to: bu ? bu.slice(2, 4) : null,
      best_line_san: before.best_line_san,
      second_san: before.second_san,
      ep_second: epSecond,
      capture: isCapture,
      sacrifice: sac,
      sacrifice_piece: sacPiece,
      base_label: baseLabel,
      tactic,
      cp_before: before.cp_stm,
      ep_best: epBest,
      ep_after: epAfter,
      ep_loss: epLoss,
      ep_label: epLabel,
      lichess_best: liBest,
      lichess_after: liAfter,
      lichess_loss: liLoss,
      lichess_label: isBook ? 'book' : labelForLoss(liLoss, isBest),
      // Lichess's formula on our engine's evals (see review.py).
      accuracy: isBook ? 100 : moveAccuracyPct(100 * (liBest - liAfter)),
      phase: phase as ReviewMove['phase'],
      clock_sec: mover === 'white' ? before.clk_white_sec : before.clk_black_sec,
    })
  }

  const weights = volatilityWeights(positions.map((p) => 100 * (p.side_to_move === 'w' ? p.lichess_stm : 1 - p.lichess_stm)))
  moves.forEach((m, k) => (m.weight = weights[k]))

  const summary = {} as Review['summary']
  for (const side of ['white', 'black'] as Side[]) {
    const mine = moves.filter((m) => m.mover === side)
    const counts: Partial<Record<Label, number>> = {}
    for (const m of mine) counts[m.ep_label] = (counts[m.ep_label] ?? 0) + 1
    const later = mine.filter((m) => m.ply > 1)
    let est = estimateRating(
      models.rating,
      models.rating,
      later.map((m) => Math.max(0, m.lichess_best - m.lichess_after)),
      later.map((m) => Math.abs(m.cp_before ?? 0)),
      timeClass,
      side === 'white' ? wElo : bElo,
    )
    if (est && pool !== 'lichess') {
      const e = est
      est = { rating: fromLichessScale(e.rating, pool, timeClass), low: fromLichessScale(e.low, pool, timeClass), high: fromLichessScale(e.high, pool, timeClass), plays_like: fromLichessScale(e.plays_like, pool, timeClass, -2) }
      // Keep the ±400 single-game bound on the scale the player sees.
      const own = side === 'white' ? wEloRaw : bEloRaw
      est.plays_like = pyRound(Math.max(own - MAX_SWING, Math.min(own + MAX_SWING, est.plays_like)), -2)
    }
    summary[side] = {
      moves: mine.length,
      avg_ep_loss: mine.length ? mine.reduce((s, m) => s + m.ep_loss, 0) / mine.length : 0,
      accuracy: mine.length
        ? (combine(
            mine.map((m) => m.accuracy),
            mine.map((m) => m.weight ?? 1),
          ) as number)
        : 100,
      labels: counts,
      estimated_rating: est,
      phases: Object.fromEntries(
        (['opening', 'middlegame', 'endgame'] as const).map((ph) => [ph, phaseGrade(mine.filter((m) => m.phase === ph))]),
      ) as Review['summary']['white']['phases'],
    }
  }

  const key = moves
    .filter((m) => ['mistake', 'blunder', 'miss'].includes(m.ep_label))
    .sort((a, b2) => b2.ep_loss - a.ep_loss)
    .slice(0, 5)
    .concat(moves.filter((m) => m.ep_label === 'brilliant').slice(0, 2))

  const whiteLichess = (p: PositionRow) => (p.side_to_move === 'w' ? p.lichess_stm : 1 - p.lichess_stm)
  return {
    headers: h,
    white_elo: wEloRaw,
    black_elo: bEloRaw,
    white_model_elo: wElo,
    black_model_elo: bElo,
    rating_pool: pool as Review['rating_pool'],
    time_class: timeClass,
    rating_band: band,
    engine_depth: opts.depth,
    start_fen: game.startFen,
    positions: positions.map((p) => ({
      fen: p.fen,
      white_ep: p.white_ep_display,
      white_lichess: whiteLichess(p),
      cp: p.eval_cp_white,
      mate: p.mate_white,
    })),
    white_ep_by_ply: positions.map((p) => p.white_ep_display),
    white_lichess_by_ply: positions.map(whiteLichess),
    moves,
    summary,
    key_moments: key.map((m) => m.ply).sort((a, b2) => a - b2),
    rows: positions,
  }
}

/** Judge a move tried in retry mode, like the played move: the real context after the move, the attempt's eval. */
export async function scoreAttempt(
  review: ReviewResult,
  move: ReviewMove,
  uci: string,
  model: TreeModel,
  analyse: AnalyseFn,
): Promise<RetryResult> {
  const i = move.ply - 1
  const board = new Chess(move.fen_before)
  let played
  try {
    played = board.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
  } catch {
    throw new Error('Illegal move')
  }
  const terminal = terminalScore(board)
  const row: PositionRow = { ...review.rows[i + 1], terminal }
  let ep: number
  if (uci === move.best_uci) ep = move.ep_best
  else if (terminal !== null) ep = 1 - terminal
  else {
    const [ev] = await analyse([board.fen()])
    Object.assign(row, {
      eval_cp_white: ev.eval_cp_white,
      mate_white: ev.mate_white,
      eval_cp_stm: ev.eval_cp_stm,
      mate_stm: ev.mate_stm,
      eval_depth: ev.eval_depth,
    })
    ep = 1 - model.predictRows([row])[0]
  }
  const loss = Math.max(0, move.ep_best - ep)
  const isBest = uci === move.best_uci
  return {
    uci,
    san: played.san,
    ep_after: ep,
    ep_loss: loss,
    label: labelForLoss(loss, isBest),
    correct: isBest || loss <= RETRY_TOLERANCE,
    best_san: move.best_san,
    best_line_san: move.best_line_san,
  } as RetryResult
}
