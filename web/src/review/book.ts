// Polyglot opening book reader (as python-chess's chess.polyglot.find_all): Zobrist key of a FEN, then the
// book's legal moves for that key, weight >= 1, castling given as king-to-rook converted to e1g1 etc.
import { Chess } from 'chess.js'

const PIECE_KIND: Record<string, number> = { p: 0, n: 1, b: 2, r: 3, q: 4, k: 5 }
const ENTRY = 16

export interface Book {
  key(fen: string): bigint
  movesFor(fen: string): string[]
}

function sqIndex(name: string): number {
  return name.charCodeAt(0) - 97 + 8 * (Number(name[1]) - 1)
}

function sqName(i: number): string {
  return `${'abcdefgh'[i % 8]}${Math.floor(i / 8) + 1}`
}

/** Polyglot Zobrist key, from the FEN fields (en passant only when a side-to-move pawn could capture). */
export function polyglotKey(fen: string, keys: bigint[]): bigint {
  const [placement, turn, castling, ep] = fen.split(/\s+/)
  const board: (string | null)[] = new Array(64).fill(null)
  let h = 0n
  placement.split('/').forEach((row, r) => {
    let file = 0
    for (const ch of row) {
      if (/\d/.test(ch)) {
        file += Number(ch)
        continue
      }
      const sq = 8 * (7 - r) + file
      board[sq] = ch
      const white = ch === ch.toUpperCase()
      h ^= keys[64 * (PIECE_KIND[ch.toLowerCase()] * 2 + (white ? 1 : 0)) + sq]
      file++
    }
  })
  // Castling rights as python-chess keeps them: the king and rook must still be on their squares.
  const has = (flag: string, king: number, rook: number, k: string, rk: string) =>
    castling.includes(flag) && board[king] === k && board[rook] === rk
  if (has('K', 4, 7, 'K', 'R')) h ^= keys[768]
  if (has('Q', 4, 0, 'K', 'R')) h ^= keys[769]
  if (has('k', 60, 63, 'k', 'r')) h ^= keys[770]
  if (has('q', 60, 56, 'k', 'r')) h ^= keys[771]
  if (ep && ep !== '-') {
    const e = sqIndex(ep)
    const pawnRank = turn === 'w' ? e - 8 : e + 8 // the pawn that just moved sits here
    const own = turn === 'w' ? 'P' : 'p'
    const f = e % 8
    const left = f > 0 && board[pawnRank - 1] === own
    const right = f < 7 && board[pawnRank + 1] === own
    if (left || right) h ^= keys[772 + f]
  }
  if (turn === 'w') h ^= keys[780]
  return h
}

export function loadBook(buffer: ArrayBuffer, hexKeys: string[]): Book {
  const keys = hexKeys.map((k) => BigInt(`0x${k}`))
  const view = new DataView(buffer)
  const size = Math.floor(buffer.byteLength / ENTRY)
  const keyAt = (i: number) => view.getBigUint64(i * ENTRY, false)

  function bisectLeft(key: bigint): number {
    let lo = 0
    let hi = size
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (keyAt(mid) < key) lo = mid + 1
      else hi = mid
    }
    return lo
  }

  return {
    key: (fen) => polyglotKey(fen, keys),
    movesFor(fen: string): string[] {
      const key = polyglotKey(fen, keys)
      const board = new Chess(fen)
      const legal = new Set(board.moves({ verbose: true }).map((m) => m.from + m.to + (m.promotion ?? '')))
      const out: string[] = []
      for (let i = bisectLeft(key); i < size && keyAt(i) === key; i++) {
        const raw = view.getUint16(i * ENTRY + 8, false)
        const weight = view.getUint16(i * ENTRY + 10, false)
        if (weight < 1) continue
        const to = raw & 0x3f
        const from = (raw >> 6) & 0x3f
        const promoPart = (raw >> 12) & 0x7
        let promo = promoPart ? ' nbrq'[promoPart] : ''
        if (from === to) promo = '' // drops: not in standard chess
        let toSq = to
        if (!promo) {
          const piece = board.get(sqName(from) as never)
          if (from === 4 && piece?.type === 'k') toSq = to === 7 ? 6 : to === 0 ? 2 : to
          else if (from === 60 && piece?.type === 'k') toSq = to === 63 ? 62 : to === 56 ? 58 : to
        }
        const uci = sqName(from) + sqName(toSq) + promo
        if (legal.has(uci)) out.push(uci)
      }
      return out
    },
  }
}
