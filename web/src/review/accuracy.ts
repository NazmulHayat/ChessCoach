// Game accuracy, Lichess-style: port of ep_model/phase_d/accuracy.py.

export function winPercent(cpWhite: number): number {
  const cp = Math.max(-1000, Math.min(1000, cpWhite))
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1)
}

export function moveAccuracyPct(drop: number, bonus = 1): number {
  if (drop <= 0) return 100
  const raw = 103.1668100711649 * Math.exp(-0.04354415386753951 * drop) - 3.166924740191411
  return Math.max(0, Math.min(100, raw + bonus))
}

function pstdev(xs: number[]): number {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length
  return Math.sqrt(xs.reduce((a, x) => a + (x - mean) ** 2, 0) / xs.length)
}

/** One weight per move: SD of white's win% over a sliding window, clamped to [0.5, 12]. */
export function volatilityWeights(winWhite: number[]): number[] {
  const nMoves = winWhite.length - 1
  const size = Math.max(2, Math.min(8, Math.floor(nMoves / 10)))
  const windows: number[][] = []
  for (let i = 0; i < size - 2; i++) windows.push(winWhite.slice(0, size))
  for (let i = 0; i < winWhite.length - size + 1; i++) windows.push(winWhite.slice(i, i + size))
  return windows.slice(0, Math.max(0, nMoves)).map((w) => Math.max(0.5, Math.min(12, pstdev(w))))
}

/** Lichess's game accuracy from per-move accuracies and their volatility weights. */
export function combine(accs: number[], weights: number[]): number | null {
  if (accs.length === 0) return null
  let num = 0
  let den = 0
  for (let i = 0; i < accs.length; i++) {
    num += accs[i] * weights[i]
    den += weights[i]
  }
  const weighted = num / den
  const harmonic = accs.length / accs.reduce((a, x) => a + 1 / Math.max(x, 1), 0)
  return (weighted + harmonic) / 2
}

/** Lichess's accuracy per colour from white-POV evals, one per position including the start. */
export function lichessGameAccuracy(cpsWhite: number[], whiteStarts = true): { white: number | null; black: number | null } {
  const wins = cpsWhite.map(winPercent)
  const weights = volatilityWeights(wins)
  const per = { white: { accs: [] as number[], ws: [] as number[] }, black: { accs: [] as number[], ws: [] as number[] } }
  for (let i = 0; i < wins.length - 1; i++) {
    const whiteMoved = (i % 2 === 0) === whiteStarts
    const [before, after] = whiteMoved ? [wins[i], wins[i + 1]] : [100 - wins[i], 100 - wins[i + 1]]
    const side = whiteMoved ? per.white : per.black
    side.accs.push(moveAccuracyPct(before - after))
    side.ws.push(weights[i])
  }
  return { white: combine(per.white.accs, per.white.ws), black: combine(per.black.accs, per.black.ws) }
}

/** Volatility weights for our review, from white's chances (0-1) per position. */
export function epMoveWeights(whiteEpByPosition: number[]): number[] {
  return volatilityWeights(whiteEpByPosition.map((w) => 100 * w))
}
