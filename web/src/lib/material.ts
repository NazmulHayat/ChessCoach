// Captured pieces and material balance from a FEN, for the player bars.

export type PieceType = 'p' | 'n' | 'b' | 'r' | 'q'

const START: Record<PieceType, number> = { p: 8, n: 2, b: 2, r: 2, q: 1 }
const VALUE: Record<PieceType, number> = { p: 1, n: 3, b: 3, r: 5, q: 9 }
const ORDER: PieceType[] = ['q', 'r', 'b', 'n', 'p']

export interface Captured {
  /** Opponent pieces this side has taken, most valuable first. */
  pieces: PieceType[]
  /** Material lead in points (0 if behind or equal). */
  lead: number
}

function counts(fen: string): { w: Record<PieceType, number>; b: Record<PieceType, number> } {
  const w = { p: 0, n: 0, b: 0, r: 0, q: 0 }
  const b = { p: 0, n: 0, b: 0, r: 0, q: 0 }
  for (const ch of fen.split(' ')[0]) {
    const t = ch.toLowerCase() as PieceType
    if (!(t in w)) continue
    if (ch === t) b[t]++
    else w[t]++
  }
  return { w, b }
}

function missing(have: Record<PieceType, number>): PieceType[] {
  // Promoted pieces above the starting count came from pawns: count those pawns as still present.
  const extra = ORDER.filter((t) => t !== 'p').reduce((n, t) => n + Math.max(0, have[t] - START[t]), 0)
  const out: PieceType[] = []
  for (const t of ORDER) {
    const gone = t === 'p' ? START.p - have.p - extra : START[t] - have[t]
    for (let i = 0; i < gone; i++) out.push(t)
  }
  return out
}

export function capturedFrom(fen: string): { white: Captured; black: Captured } {
  const c = counts(fen)
  const score = (h: Record<PieceType, number>) => ORDER.reduce((s, t) => s + VALUE[t] * h[t], 0)
  const diff = score(c.w) - score(c.b)
  return {
    white: { pieces: missing(c.b), lead: Math.max(0, diff) },
    black: { pieces: missing(c.w), lead: Math.max(0, -diff) },
  }
}
