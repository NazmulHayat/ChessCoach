import type { Side } from '../types'

export interface RecentGame {
  pgn: string
  side?: Side
  white: string
  black: string
  result: string
  date: string
}

const KEY = 'cc.recent'

export function recentGames(): RecentGame[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    if (!Array.isArray(data)) return []
    return data.filter((g): g is RecentGame => !!g && typeof g === 'object'
      && ['pgn', 'white', 'black', 'result', 'date'].every((k) => typeof g[k] === 'string')
      && (g.side === undefined || g.side === 'white' || g.side === 'black')).slice(0, 5)
  } catch {
    return []
  }
}

export function rememberGame(pgn: string, headers: Record<string, string>, side?: Side) {
  const game: RecentGame = {
    pgn, side, white: headers.White || 'White', black: headers.Black || 'Black',
    result: headers.Result || '*', date: new Date().toISOString(),
  }
  try {
    localStorage.setItem(KEY, JSON.stringify([game, ...recentGames().filter((g) => g.pgn !== pgn)].slice(0, 5)))
  } catch {
    /* Private browsing or full storage: analysis still works. */
  }
}
