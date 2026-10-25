// Minimal PGN reader for the review: headers, start position, and the mainline with each move's comment
// (clocks live in comments). Variations, NAGs and annotation glyphs are skipped.
import { Chess } from 'chess.js'

export interface PgnMove {
  san: string
  uci: string
  comment: string
}

export interface ParsedGame {
  headers: Record<string, string>
  startFen: string
  moves: PgnMove[]
}

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const RESULTS = new Set(['1-0', '0-1', '1/2-1/2', '*'])

export function parsePgn(pgn: string): ParsedGame {
  const headers: Record<string, string> = {}
  const lines = pgn.replace(/\r\n?/g, '\n').split('\n')
  let i = 0
  for (; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) {
      if (Object.keys(headers).length) {
        i++
        break
      }
      continue
    }
    const m = /^\[(\w+)\s+"((?:[^"\\]|\\.)*)"\]$/.exec(line)
    if (!m) break
    headers[m[1]] = m[2].replace(/\\(.)/g, '$1')
  }
  const text = lines
    .slice(i)
    .map((l) => (l.startsWith('%') ? '' : l.replace(/;.*$/, '')))
    .join('\n')

  const startFen = headers.FEN || START_FEN
  const board = new Chess(startFen)
  const moves: PgnMove[] = []
  let depth = 0 // inside ( ... ) variations
  let k = 0
  while (k < text.length) {
    const ch = text[k]
    if (ch === '{') {
      const end = text.indexOf('}', k + 1)
      const comment = text.slice(k + 1, end === -1 ? text.length : end).trim()
      if (depth === 0 && moves.length) moves[moves.length - 1].comment += (moves[moves.length - 1].comment ? ' ' : '') + comment
      k = end === -1 ? text.length : end + 1
      continue
    }
    if (ch === '(') {
      depth++
      k++
      continue
    }
    if (ch === ')') {
      depth = Math.max(0, depth - 1)
      k++
      continue
    }
    if (/\s/.test(ch)) {
      k++
      continue
    }
    let j = k
    while (j < text.length && !/[\s{}()]/.test(text[j])) j++
    const token = text.slice(k, j)
    k = j
    if (depth > 0 || RESULTS.has(token) || /^\$\d+$/.test(token)) continue
    const san = token.replace(/^\d+\.+/, '').replace(/[!?]+$/, '')
    if (!san || /^\d+\.*$/.test(san)) continue
    let mv
    try {
      mv = board.move(san)
    } catch {
      throw new Error(`Couldn't read a game from that PGN (illegal move ${san}).`)
    }
    moves.push({ san: mv.san, uci: mv.from + mv.to + (mv.promotion ?? ''), comment: '' })
  }
  if (!moves.length) throw new Error("Couldn't read a game from that PGN.")
  return { headers, startFen, moves }
}
