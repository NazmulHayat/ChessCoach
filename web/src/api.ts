import type { GameListItem, RetryResult, Review } from './types'

async function errorDetail(r: Response): Promise<string> {
  try {
    const body = await r.json()
    return typeof body.detail === 'string' ? body.detail : `Request failed (${r.status})`
  } catch {
    return `Request failed (${r.status})`
  }
}

/** Engine depth and worker count if the server is up, else null. */
export async function health(): Promise<{ depth: number; workers: number; explain: boolean } | null> {
  try {
    const r = await fetch('/api/health')
    return r.ok ? r.json() : null
  } catch {
    return null
  }
}

export async function fetchGames(site: 'chesscom' | 'lichess', user: string): Promise<GameListItem[]> {
  let r: Response
  try {
    r = await fetch(`/api/games/${site}/${encodeURIComponent(user.trim())}`)
  } catch {
    throw new Error('Can’t reach the ChessCoach server. Is it running?')
  }
  if (!r.ok) throw new Error(await errorDetail(r))
  return r.json()
}

/** POST the PGN and read the server-sent event stream: progress events, then one result (or error). */
export async function streamReview(
  pgn: string,
  onProgress: (done: number, total: number) => void,
  signal?: AbortSignal,
): Promise<Review> {
  let r: Response
  try {
    r = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pgn }),
      signal,
    })
  } catch (e) {
    if (signal?.aborted) throw e
    throw new Error('Can’t reach the ChessCoach server. Is it running?')
  }
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

export class GoneError extends Error {}

/** Score a move tried in retry mode. Throws GoneError if the server no longer has this review. */
export async function retryMove(reviewId: string, ply: number, uci: string): Promise<RetryResult> {
  const r = await fetch('/api/retry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_id: reviewId, ply, uci }),
  })
  if (r.status === 410) throw new GoneError(await errorDetail(r))
  if (!r.ok) throw new Error(await errorDetail(r))
  return r.json()
}

/** Claude-written note on one move (only when the server has ANTHROPIC_API_KEY). */
export async function explainMove(reviewId: string, ply: number): Promise<string> {
  const r = await fetch('/api/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_id: reviewId, ply }),
  })
  if (!r.ok) throw new Error(await errorDetail(r))
  return (await r.json()).text
}
