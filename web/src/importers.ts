// Recent games from Chess.com and Lichess, fetched straight from the browser (both public APIs send
// Access-Control-Allow-Origin: *). Same output as the server's /api/games/{site}/{user} endpoints.
import type { GameListItem } from './types'

export const GAMES_LIMIT = 25

type Fetch = typeof fetch

function parseTimeControl(tc: string | null | undefined): [number | null, number | null] {
  if (!tc || tc === '-' || tc === '?') return [null, null]
  const s = tc.trim()
  const toInt = (x: string) => (/^\s*-?\d+\s*$/.test(x) ? parseInt(x, 10) : null)
  if (s.includes('+')) {
    const i = s.indexOf('+')
    const a = toInt(s.slice(0, i))
    const b = toInt(s.slice(i + 1))
    return a === null || b === null ? [null, null] : [a, b]
  }
  const a = toInt(s)
  return a === null ? [null, null] : [a, 0]
}

export function classifyTimeClass(initialSec: number | null): string {
  if (initialSec === null) return 'unknown'
  if (initialSec < 180) return 'bullet'
  if (initialSec < 480) return 'blitz'
  if (initialSec < 1500) return 'rapid'
  return 'classical'
}

/** 'win' / 'loss' / 'draw' from `user`'s point of view. */
export function resultFor(white: string, black: string, user: string, result: string): 'win' | 'loss' | 'draw' {
  void black
  if (result === '1/2-1/2') return 'draw'
  const whiteWon = result === '1-0'
  const isWhite = white.toLowerCase() === user.toLowerCase()
  return whiteWon === isWhite ? 'win' : 'loss'
}

function pgnResult(pgn: string): string {
  const m = pgn.match(/\[Result\s+"([^"]*)"\]/)
  return m ? m[1] : '*'
}

async function get(f: Fetch, url: string, site: string, init?: RequestInit): Promise<Response> {
  try {
    return await f(url, init)
  } catch {
    throw new Error(`Can’t reach ${site}. Check your internet connection and try again.`)
  }
}

function failure(site: string, user: string, status: number): Error {
  if (status === 404) return new Error(`No ${site} player '${user}'.`)
  if (status === 429) return new Error(`${site} is limiting requests right now. Try again in a minute.`)
  return new Error(`${site} request failed (${status}).`)
}

interface ChesscomPlayer {
  username?: string
  rating?: number
}

interface ChesscomGame {
  uuid?: string
  url?: string
  pgn?: string
  rules?: string
  time_control?: string
  time_class?: string
  end_time?: number
  white: ChesscomPlayer
  black: ChesscomPlayer
}

export async function chesscomGames(user: string, f: Fetch = fetch): Promise<GameListItem[]> {
  user = user.trim().toLowerCase()
  const site = 'Chess.com'
  const r = await get(f, `https://api.chess.com/pub/player/${encodeURIComponent(user)}/games/archives`, site)
  if (!r.ok) throw failure(site, user, r.status)
  const archives: string[] = (await r.json()).archives ?? []
  const games: ChesscomGame[] = []
  for (const url of archives.slice(-3).reverse()) {
    const ar = await get(f, url, site)
    if (!ar.ok) throw failure(site, user, ar.status)
    games.push(...((await ar.json()).games ?? []).slice().reverse())
    if (games.length >= GAMES_LIMIT) break
  }
  const out: GameListItem[] = []
  for (const g of games) {
    if (g.rules !== 'chess' || !g.pgn) continue
    const w = g.white
    const b = g.black
    const result = pgnResult(g.pgn)
    const [init] = parseTimeControl(g.time_control)
    out.push({
      id: g.uuid || g.url || '',
      site: 'chesscom',
      url: g.url ?? '',
      white: w.username ?? '',
      black: b.username ?? '',
      white_elo: w.rating ?? null,
      black_elo: b.rating ?? null,
      result,
      user_result: resultFor(w.username ?? '', b.username ?? '', user, result),
      time_control: g.time_control ?? '-',
      time_class: g.time_class || classifyTimeClass(init),
      end_time: new Date((g.end_time ?? 0) * 1000).toISOString(),
      pgn: g.pgn,
    })
    if (out.length >= GAMES_LIMIT) break
  }
  return out
}

interface LichessPlayer {
  user?: { name?: string }
  rating?: number
}

interface LichessGame {
  id?: string
  variant?: string
  pgn?: string
  winner?: 'white' | 'black'
  speed?: string
  clock?: { initial?: number; increment?: number }
  players?: { white?: LichessPlayer; black?: LichessPlayer }
  createdAt?: number
  lastMoveAt?: number
}

export async function lichessGames(user: string, f: Fetch = fetch): Promise<GameListItem[]> {
  user = user.trim()
  const site = 'Lichess'
  const params = new URLSearchParams({ max: String(GAMES_LIMIT), pgnInJson: 'true', clocks: 'true', opening: 'true' })
  const r = await get(f, `https://lichess.org/api/games/user/${encodeURIComponent(user)}?${params}`, site, {
    headers: { Accept: 'application/x-ndjson' },
  })
  if (!r.ok) throw failure(site, user, r.status)
  const out: GameListItem[] = []
  for (const line of (await r.text()).split('\n')) {
    if (!line.trim()) continue
    const g: LichessGame = JSON.parse(line)
    if ((g.variant ?? 'standard') !== 'standard' || !g.pgn) continue
    const w = g.players?.white ?? {}
    const b = g.players?.black ?? {}
    const wn = w.user?.name ?? 'Anonymous'
    const bn = b.user?.name ?? 'Anonymous'
    const result = g.winner === 'white' ? '1-0' : g.winner === 'black' ? '0-1' : '1/2-1/2'
    const clock = g.clock
    out.push({
      id: g.id ?? '',
      site: 'lichess',
      url: `https://lichess.org/${g.id}`,
      white: wn,
      black: bn,
      white_elo: w.rating ?? null,
      black_elo: b.rating ?? null,
      result,
      user_result: resultFor(wn, bn, user, result),
      time_control: clock ? `${clock.initial ?? 0}+${clock.increment ?? 0}` : '-',
      time_class: g.speed ?? 'unknown',
      end_time: new Date(g.lastMoveAt ?? g.createdAt ?? 0).toISOString(),
      pgn: g.pgn,
    })
  }
  return out
}

export function fetchGamesDirect(site: 'chesscom' | 'lichess', user: string, f: Fetch = fetch): Promise<GameListItem[]> {
  return site === 'chesscom' ? chesscomGames(user, f) : lichessGames(user, f)
}
