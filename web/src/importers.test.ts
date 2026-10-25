import { describe, expect, it, vi } from 'vitest'
import { chesscomGames, classifyTimeClass, GAMES_LIMIT, lichessGames, resultFor } from './importers'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const ccGame = (n: number, extra: Record<string, unknown> = {}) => ({
  uuid: `u${n}`,
  url: `https://www.chess.com/game/live/${n}`,
  pgn: `[Event "Live"]\n[Result "${n % 3 === 0 ? '1/2-1/2' : n % 2 ? '1-0' : '0-1'}"]\n\n1. e4 e5 *`,
  rules: 'chess',
  time_control: '180+2',
  time_class: 'blitz',
  end_time: 1790978999,
  white: { username: 'Alice', rating: 1500 },
  black: { username: 'Bob', rating: 1450 },
  ...extra,
})

describe('chesscomGames', () => {
  it('walks the latest archives newest first and maps fields', async () => {
    const f = vi.fn(async (url: string) => {
      if (url.endsWith('/games/archives')) return json({ archives: ['a/2026/08', 'a/2026/09', 'a/2026/10'] })
      if (url === 'a/2026/10') return json({ games: [ccGame(1), ccGame(2), ccGame(3, { rules: 'chess960' })] })
      if (url === 'a/2026/09') return json({ games: [ccGame(4)] })
      return json({ games: [] })
    })
    const out = await chesscomGames('  ALICE ', f as unknown as typeof fetch)
    expect(f.mock.calls[0][0]).toBe('https://api.chess.com/pub/player/alice/games/archives')
    expect(out.map((g) => g.id)).toEqual(['u2', 'u1', 'u4']) // newest first, chess960 skipped
    expect(out[0]).toMatchObject({
      site: 'chesscom', white: 'Alice', black: 'Bob', white_elo: 1500, result: '0-1', user_result: 'loss',
      time_control: '180+2', time_class: 'blitz', end_time: new Date(1790978999 * 1000).toISOString(),
    })
    expect(out[1].user_result).toBe('win')
  })

  it('stops at the games limit and falls back to the time control for the class', async () => {
    const many = Array.from({ length: 40 }, (_, i) => ccGame(i + 1, { time_class: undefined, time_control: '60' }))
    const f = vi.fn(async (url: string) => (url.endsWith('archives') ? json({ archives: ['x'] }) : json({ games: many })))
    const out = await chesscomGames('alice', f as unknown as typeof fetch)
    expect(out).toHaveLength(GAMES_LIMIT)
    expect(out[0].time_class).toBe('bullet')
  })

  it('reports unknown players and network failures in plain words', async () => {
    await expect(chesscomGames('nobody', (async () => json({}, 404)) as unknown as typeof fetch)).rejects.toThrow(
      "No Chess.com player 'nobody'.",
    )
    const down = (async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch
    await expect(chesscomGames('alice', down)).rejects.toThrow(/Can’t reach Chess.com/)
  })
})

describe('lichessGames', () => {
  const line = (o: Record<string, unknown>) => JSON.stringify(o)
  const ndjson = [
    line({
      id: 'abc', variant: 'standard', pgn: '1. e4 *', winner: 'black', speed: 'bullet', clock: { initial: 60, increment: 0 },
      players: { white: { user: { name: 'Sacui' }, rating: 1737 }, black: { user: { name: 'Nazmul' }, rating: 1730 } },
      createdAt: 1000, lastMoveAt: 1790000000000,
    }),
    line({ id: 'z', variant: 'chess960', pgn: '1. e4 *', players: {} }),
    line({ id: 'd', variant: 'standard', pgn: '1. d4 *', speed: 'rapid', players: { white: { rating: 1500 }, black: { user: { name: 'nazmul' } } } }),
    '',
  ].join('\n')

  it('asks for ndjson and maps results from the user’s side', async () => {
    const f = vi.fn(async () => new Response(ndjson, { status: 200 }))
    const out = await lichessGames('Nazmul', f as unknown as typeof fetch)
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('https://lichess.org/api/games/user/Nazmul?')
    expect(url).toContain(`max=${GAMES_LIMIT}`)
    expect((init.headers as Record<string, string>).Accept).toBe('application/x-ndjson')
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({
      id: 'abc', url: 'https://lichess.org/abc', result: '0-1', user_result: 'win', time_control: '60+0',
      time_class: 'bullet', white_elo: 1737, end_time: new Date(1790000000000).toISOString(),
    })
    expect(out[1]).toMatchObject({ white: 'Anonymous', black: 'nazmul', result: '1/2-1/2', user_result: 'draw', time_control: '-' })
  })

  it('reports unknown players and rate limits', async () => {
    await expect(lichessGames('x', (async () => new Response('', { status: 404 })) as unknown as typeof fetch)).rejects.toThrow(
      "No Lichess player 'x'.",
    )
    await expect(lichessGames('x', (async () => new Response('', { status: 429 })) as unknown as typeof fetch)).rejects.toThrow(
      /limiting requests/,
    )
  })
})

describe('helpers', () => {
  it('matches the server rules', () => {
    expect(classifyTimeClass(null)).toBe('unknown')
    expect(classifyTimeClass(179)).toBe('bullet')
    expect(classifyTimeClass(480)).toBe('rapid')
    expect(classifyTimeClass(1500)).toBe('classical')
    expect(resultFor('A', 'B', 'a', '1-0')).toBe('win')
    expect(resultFor('A', 'B', 'b', '1-0')).toBe('loss')
  })
})
