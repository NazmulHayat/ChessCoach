import type { GameListItem, Review } from './types'

async function errorDetail(r: Response): Promise<string> {
  try {
    const body = await r.json()
    return typeof body.detail === 'string' ? body.detail : `Request failed (${r.status})`
  } catch {
    return `Request failed (${r.status})`
  }
}

export async function fetchGames(site: 'chesscom' | 'lichess', user: string): Promise<GameListItem[]> {
  const r = await fetch(`/api/games/${site}/${encodeURIComponent(user.trim())}`)
  if (!r.ok) throw new Error(await errorDetail(r))
  return r.json()
}

/** POST the PGN and read the server-sent event stream: progress events, then one result (or error). */
export async function streamReview(
  pgn: string,
  onProgress: (done: number, total: number) => void,
  signal?: AbortSignal,
): Promise<Review> {
  const r = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pgn }),
    signal,
  })
  if (!r.ok || !r.body) throw new Error(await errorDetail(r))

  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    let sep: number
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = /^data: (.*)$/m.exec(block)?.[1]
      if (!event || data === undefined) continue
      const payload = JSON.parse(data)
      if (event === 'progress') onProgress(payload.done, payload.total)
      else if (event === 'result') return payload as Review
      else if (event === 'error') throw new Error(payload.detail || 'Analysis failed')
    }
  }
  throw new Error('Connection closed before the analysis finished')
}
