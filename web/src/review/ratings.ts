// Rating pools: port of ep_model/review/ratings.py (Chess.com ratings mapped onto the Lichess scale).

const CHESSCOM_TO_LICHESS: Record<string, [number, number]> = {
  bullet: [0.75, 560],
  blitz: [0.75, 600],
  rapid: [0.7, 740],
  classical: [0.7, 740],
}

/** Python round(): to `ndigits` decimals (negative = tens, hundreds), halves to even. */
export function pyRound(x: number, ndigits = 0): number {
  const scale = 10 ** Math.abs(ndigits)
  if (ndigits < 0) {
    let q = Math.floor(x / scale)
    let r = x - q * scale
    if (r < 0) {
      q -= 1
      r += scale
    } else if (r >= scale) {
      q += 1
      r -= scale
    }
    const half = scale / 2
    if (r > half || (r === half && q % 2 !== 0)) q += 1
    return q * scale
  }
  const y = x * scale
  const f = Math.floor(y)
  const d = y - f
  const n = d > 0.5 || (d === 0.5 && f % 2 !== 0) ? f + 1 : f
  return n / scale
}

export function detectPool(headers: Record<string, string | undefined>): 'chesscom' | 'lichess' {
  const site = `${headers.Site ?? ''} ${headers.Link ?? ''}`.toLowerCase()
  return site.includes('chess.com') ? 'chesscom' : 'lichess'
}

export function toLichessScale(elo: number, pool: string, timeClass: string): number {
  if (pool !== 'chesscom') return elo
  const [a, b] = CHESSCOM_TO_LICHESS[timeClass] ?? CHESSCOM_TO_LICHESS.blitz
  return pyRound(a * elo + b)
}

/** Inverse of toLichessScale (e.g. to show an estimate in Chess.com terms), rounded to 10 by default. */
export function fromLichessScale(elo: number, pool: string, timeClass: string, ndigits = -1): number {
  if (pool !== 'chesscom') return elo
  const [a, b] = CHESSCOM_TO_LICHESS[timeClass] ?? CHESSCOM_TO_LICHESS.blitz
  return pyRound((elo - b) / a, ndigits)
}
