// Short tactical hints for the coach: port of ep_model/phase_d/tactics.py.
import { Chess } from 'chess.js'
import {
  PIECE_NAMES,
  bestCaptureGain,
  captureValue,
  findFastMove,
  findMove,
  isCapture,
  makeMove,
  undoMove,
  type FastMove,
} from './special'

const MIN_HANG_POINTS = 1
const MIN_WIN_POINTS = 2

/** ["knight on f6", points] if the opponent can win material by capture right after the move. */
export function hangingAfter(board: Chess, m: FastMove): [string, number] | null {
  const taken = captureValue(m)
  makeMove(board, m)
  try {
    if (board.isCheckmate()) return null
    const [gain, where] = bestCaptureGain(board)
    if (where === null || gain - taken < MIN_HANG_POINTS) return null
    return [`${PIECE_NAMES[board.get(where)!.type]} on ${where}`, gain - taken]
  } finally {
    undoMove(board)
  }
}

/** ["queen", points] if the move captures and keeps at least MIN_WIN_POINTS after the best recapture. */
export function materialWon(board: Chess, m: FastMove): [string, number] | null {
  if (!isCapture(m)) return null
  const victim = m.captured ?? 'p' // en passant has no captured piece on the target square
  const taken = captureValue(m)
  makeMove(board, m)
  let threat: number
  try {
    threat = bestCaptureGain(board)[0]
  } finally {
    undoMove(board)
  }
  const net = taken - threat
  return net >= MIN_WIN_POINTS ? [PIECE_NAMES[victim], net] : null
}

/**
 * One phrase about the played move ("hangs the knight on f6", "allows mate in 2", "missed mate in 3",
 * "missed Nxe5, winning the queen"). mateBefore: the mover's mate score before the move; mateAfterOpp: the
 * opponent's mate score after it (positive = opponent mates).
 */
export function tacticHint(
  fenBefore: string,
  playedUci: string,
  bestUci: string | null,
  mateBefore: number | null,
  mateAfterOpp: number | null,
): string | null {
  const board = new Chess(fenBefore)
  if (mateBefore !== null && mateBefore > 0 && playedUci !== bestUci) {
    if (mateAfterOpp === null || mateAfterOpp >= 0) return `missed mate in ${mateBefore}`
  }
  if (mateAfterOpp !== null && mateAfterOpp > 0) return `allows mate in ${mateAfterOpp}`
  const played = findFastMove(board, playedUci)
  if (played) {
    const hang = hangingAfter(board, played)
    if (hang !== null) return `hangs the ${hang[0]}`
  }
  if (bestUci && bestUci !== playedUci) {
    const best = findFastMove(board, bestUci)
    if (best) {
      const won = materialWon(board, best)
      if (won !== null) return `missed ${findMove(board, bestUci)!.san}, winning the ${won[0]}`
    }
  }
  return null
}
