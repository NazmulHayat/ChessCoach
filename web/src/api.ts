// Everything runs in the browser: Stockfish (WebAssembly workers), the EP models and the review logic, so the
// app is a static site. Same function names as the old server client, so the UI didn't change.
import { createEnginePool, type EnginePool } from './engine/pool'
import { fetchGamesDirect } from './importers'
import { loadBook, type Book } from './review/book'
import { fetchTreeModel } from './review/lgbm'
import type { RatingMeta } from './review/rating'
import { reviewGame, scoreAttempt, type Models, type ReviewResult } from './review/review'
import type { GameListItem, RetryResult, Review } from './types'

export const ENGINE_DEPTH = 17 // the depth the models were trained and checked at

const base = import.meta.env.BASE_URL
let modelsPromise: Promise<Models> | null = null
let pool: EnginePool | null = null
const reviews = new Map<string, ReviewResult>()
const MAX_REVIEWS = 20

async function fetchBook(): Promise<Book | null> {
  try {
    const [bin, keys] = await Promise.all([
      fetch(`${base}data/book.bin`).then((r) => r.arrayBuffer()),
      fetch(`${base}data/polyglot.json`).then((r) => r.json() as Promise<string[]>),
    ])
    return loadBook(bin, keys)
  } catch {
    return null // reviews still work, just without "book" moves
  }
}

function models(): Promise<Models> {
  modelsPromise ??= Promise.all([
    fetchTreeModel(`${base}data/models/board.json`),
    fetchTreeModel(`${base}data/models/chances.json`),
    fetch(`${base}data/models/rating.json`)
      .then((r) => r.json())
      .then((json) => ({ curves: json.curves, offset: json.offset, spread: json.spread }) as RatingMeta),
    fetchBook(),
  ]).then(([board, chances, rating, book]) => ({ board, chances, rating, book }))
  modelsPromise.catch(() => (modelsPromise = null))
  return modelsPromise
}

function enginePool(): EnginePool {
  pool ??= createEnginePool({ depth: ENGINE_DEPTH })
  return pool
}

export class GoneError extends Error {}

/** Always available now (no server). Explanations need an API key on a server, so they are off here. */
export async function health(): Promise<{ depth: number; workers: number; explain: boolean } | null> {
  return { depth: ENGINE_DEPTH, workers: Math.min(8, Math.max(1, (navigator.hardwareConcurrency || 2) - 1)), explain: false }
}

export function fetchGames(site: 'chesscom' | 'lichess', user: string): Promise<GameListItem[]> {
  return fetchGamesDirect(site, user)
}

/** Review a game in this browser; progress counts analysed positions. */
export async function streamReview(
  pgn: string,
  onProgress: (done: number, total: number) => void,
  signal?: AbortSignal,
): Promise<Review> {
  const m = await models()
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
  const result = await reviewGame(pgn, m, enginePool().analyse, { depth: ENGINE_DEPTH, progress: onProgress })
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
  const id = crypto.randomUUID()
  reviews.set(id, result)
  if (reviews.size > MAX_REVIEWS) reviews.delete(reviews.keys().next().value as string)
  const review: Review & { rows?: unknown } = { ...result, review_id: id }
  delete review.rows
  return review
}

/** Score a move tried in retry mode. Throws GoneError if this review is no longer in memory. */
export async function retryMove(reviewId: string, ply: number, uci: string): Promise<RetryResult> {
  const r = reviews.get(reviewId)
  const move = r?.moves[ply - 1]
  if (!r || !move) throw new GoneError('This review is no longer in memory.')
  return scoreAttempt(r, move, uci, (await models()).board, enginePool().analyse)
}

export async function explainMove(...args: [reviewId: string, ply: number]): Promise<string> {
  void args
  throw new Error('Written explanations are not available in the browser version.')
}
