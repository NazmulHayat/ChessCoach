// PGN header / clock helpers: port of the parts of ep_model/phase_a/rowgen.py the review uses.

export const RATING_BUCKETS = [0, 1000, 1200, 1400, 1600, 1800, 2000, 3000]
const CLK_RE = /\[%clk\s+([^\]]+)\]/

/** Python int(): optional sign, digits, surrounding whitespace. */
function pyInt(s: string): number | null {
  const t = s.trim()
  return /^[+-]?\d+$/.test(t) ? parseInt(t, 10) : null
}

/** Python float() for plain decimal strings. */
function pyFloat(s: string): number | null {
  const t = s.trim()
  return /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t) ? parseFloat(t) : null
}

/** TimeControl header ('300+0', '180+2', '60') -> [initial, increment] seconds. */
export function parseTimeControl(tc: string | null | undefined): [number | null, number | null] {
  if (!tc || tc === '-' || tc === '?') return [null, null]
  const t = tc.trim()
  if (t.includes('+')) {
    const i = t.indexOf('+')
    const a = pyInt(t.slice(0, i))
    const b = pyInt(t.slice(i + 1))
    return a === null || b === null ? [null, null] : [a, b]
  }
  const a = pyInt(t)
  return a === null ? [null, null] : [a, 0]
}

export function classifyTimeClass(initialSec: number | null): string {
  if (initialSec === null || initialSec === undefined) return 'unknown'
  if (initialSec < 180) return 'bullet'
  if (initialSec < 480) return 'blitz'
  if (initialSec < 1500) return 'rapid'
  return 'classical'
}

export function ratingBandFromAverage(avgElo: number): string {
  const x = Math.trunc(avgElo)
  for (let i = 0; i < RATING_BUCKETS.length - 1; i++) {
    if (RATING_BUCKETS[i] <= x && x < RATING_BUCKETS[i + 1]) return `${RATING_BUCKETS[i]}-${RATING_BUCKETS[i + 1]}`
  }
  return `${RATING_BUCKETS[RATING_BUCKETS.length - 2]}+`
}

export function gamePhaseFromHalfMoves(halfMovesPlayed: number): string {
  if (halfMovesPlayed < 20) return 'opening'
  if (halfMovesPlayed < 60) return 'middlegame'
  return 'endgame'
}

/** '0:05:00' or '5:00' -> seconds. */
export function parseClockToken(token: string): number | null {
  const parts = token.split(':')
  if (parts.length === 3) {
    const h = pyInt(parts[0])
    const mn = pyInt(parts[1])
    const s = pyFloat(parts[2])
    return h === null || mn === null || s === null ? null : h * 3600 + mn * 60 + s
  }
  if (parts.length === 2) {
    const mn = pyInt(parts[0])
    const s = pyFloat(parts[1])
    return mn === null || s === null ? null : mn * 60 + s
  }
  return null
}

/** [%clk H:MM:SS] in a move comment -> seconds. */
export function parseClockComment(comment: string | null | undefined): number | null {
  if (!comment) return null
  const m = CLK_RE.exec(comment)
  return m ? parseClockToken(m[1].trim()) : null
}

/** WhiteClock / BlackClock header values. */
export function parseClockHeader(h: string | null | undefined): number | null {
  if (!h) return null
  return parseClockToken(h.trim())
}
