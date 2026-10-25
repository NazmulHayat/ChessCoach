// Coach bubble text, filled in from the review numbers (no LLM).
import { BAD_LABELS, describe, LABELS } from './labels'
import { pct, timeClassLabel } from './format'
import type { RetryState } from './App'
import type { Review, ReviewMove } from './types'

export interface CoachText {
  title: string
  body: string
  note?: string
  line?: string // an engine line in SAN, shown in monospace
}

/** "14. Nf5 Qg6 15. Nh6+" from a SAN list starting at `ply` (1-based ply of the first move). */
export function formatLine(sans: string[], ply: number, max = 6): string {
  const out: string[] = []
  sans.slice(0, max).forEach((san, i) => {
    const p = ply + i
    const num = Math.ceil(p / 2)
    if (p % 2 === 1) out.push(`${num}. ${san}`)
    else out.push(i === 0 ? `${num}... ${san}` : san)
  })
  return out.join(' ')
}

function playerName(review: Review, side: 'white' | 'black'): string {
  return review.headers[side === 'white' ? 'White' : 'Black'] || (side === 'white' ? 'White' : 'Black')
}

function levelPhrase(review: Review, side: 'white' | 'black'): string {
  const elo = side === 'white' ? review.white_elo : review.black_elo
  return `${Math.round(elo / 50) * 50} ${review.time_class}`
}

export function moveCoach(review: Review, move: ReviewMove): CoachText {
  const who = playerName(review, move.mover)
  const label = move.ep_label
  const title = `${move.san} is ${describe(label)}`

  if (label === 'book') {
    const opening = review.headers.Opening || review.headers.ECOUrl?.split('/').pop()?.replace(/-/g, ' ')
    return { title, body: opening ? `Still in opening theory: ${opening}.` : 'Still in opening theory.' }
  }

  const opp = playerName(review, move.mover === 'white' ? 'black' : 'white')
  let body: string
  if (label === 'brilliant') {
    body = `${who} gives up ${move.sacrifice_piece ? `the ${move.sacrifice_piece}` : materialPhrase(move.sacrifice)} and the position holds: chances ${pct(move.ep_after)}.`
    if (move.ep_second !== null && move.second_san && move.san !== move.second_san) body += ` The quieter ${move.second_san} gave ${pct(move.ep_second)}.`
  } else if (label === 'great') {
    body = `The only good move. ${who}'s chances stay at ${pct(move.ep_after)}`
    body += move.second_san && move.ep_second !== null ? `; the next best, ${move.second_san}, gave ${pct(move.ep_second)}.` : '.'
  } else if (label === 'miss') {
    body = `${opp} had just slipped, and this gives most of it back: chances ${pct(move.ep_best)} → ${pct(move.ep_after)}.`
    if (move.tactic) body = `${move.san} ${move.tactic}. ${body}`
    if (move.best_san) body += ` ${move.best_san} kept the advantage.`
  } else if (label === 'best') {
    body = `${who}'s chances stay at ${pct(move.ep_after)}.`
  } else if (BAD_LABELS.includes(label)) {
    body = `${who}'s chances dropped from ${pct(move.ep_best)} to ${pct(move.ep_after)}.`
    if (move.tactic) body = `${move.san} ${move.tactic}. ${body}`
    if (move.best_san) body += ` ${move.best_san} was best.`
  } else {
    body = `${who}'s chances: ${pct(move.ep_after)}.`
    if (move.best_san) body += ` ${move.best_san} was best (${pct(move.ep_best)}).`
  }
  const line = BAD_LABELS.includes(label) && move.best_line_san.length > 1 ? `Best: ${formatLine(move.best_line_san, move.ply)}` : undefined

  let note: string | undefined
  const evalOnly = move.lichess_label
  const base = move.base_label
  if (evalOnly !== base && evalOnly !== 'book' && base !== 'best' && label !== 'brilliant' && label !== 'great') {
    const level = levelPhrase(review, move.mover)
    const harsher = move.lichess_loss > move.ep_loss
    note = harsher
      ? `An eval-only review would call this ${describe(evalOnly)}. The engine score drops more, but at ${level} this position is still very playable.`
      : `An eval-only review would call this ${describe(evalOnly)}. The engine score barely moves, but at ${level} this costs real chances.`
    if (base !== label) note = undefined
  }
  return { title, body, note, line }
}

export function retryCoach(move: ReviewMove, retry: RetryState): CoachText {
  const color = move.mover === 'white' ? 'White' : 'Black'
  const r = retry.result
  switch (retry.phase) {
    case 'try':
    case 'checking':
      return {
        title: retry.phase === 'checking' ? 'Checking…' : 'Find a better move',
        body: retry.error
          ? `Couldn’t check that move (${retry.error}). Try again.`
          : `${move.san} was ${describe(move.ep_label)}. Drag a piece or tap it, then tap a square: what should ${color} play here?`,
      }
    case 'correct': {
      if (!r) return { title: 'Correct!', body: '' }
      const exact = r.uci === move.best_uci
      return {
        title: `${r.san} is correct!`,
        body: exact
          ? `That’s the engine’s top move: chances ${pct(move.ep_best)} instead of ${pct(move.ep_after)}.`
          : `As good as the engine’s ${move.best_san}: chances ${pct(r.ep_after)} instead of ${pct(move.ep_after)}.`,
        line: exact ? formatLine(move.best_line_san, move.ply) : undefined,
      }
    }
    case 'wrong':
    case 'solution': {
      const tried = r ? (Number.isNaN(r.ep_after) ? `${r.san} isn’t the engine’s move.` : `${r.san} gives ${pct(r.ep_after)}; the best move keeps ${pct(move.ep_best)}.`) : ''
      if (retry.phase === 'wrong') return { title: 'Not quite', body: `${tried} Try again?` }
      return {
        title: `The move was ${move.best_san}`,
        body: `${tried} ${move.best_san} keeps ${color}’s chances at ${pct(move.ep_best)}.`.trim(),
        line: formatLine(move.best_line_san, move.ply),
      }
    }
  }
}

function materialPhrase(points: number): string {
  if (points >= 9) return 'the queen'
  if (points >= 5) return 'a rook'
  if (points >= 3) return 'a piece'
  return 'the exchange'
}

export function startCoach(review: Review): CoachText {
  const opening = review.headers.Opening || review.headers.ECOUrl?.split('/').pop()?.replace(/-/g, ' ')
  return {
    title: 'Let’s review this game',
    body: `${timeClassLabel(review.time_class)} game${opening ? `, ${opening}` : ''}. Use the arrows or click any move.`,
  }
}

export function summaryCoach(review: Review): CoachText {
  const result = review.headers.Result
  const winner = result === '1-0' ? 'white' : result === '0-1' ? 'black' : null
  const san = (m: ReviewMove) => `${m.move_number}${m.mover === 'white' ? '.' : '...'} ${m.san}`
  const key = review.moves.filter((m) => review.key_moments.includes(m.ply))
  const bad = key.filter((m) => BAD_LABELS.includes(m.ep_label)).sort((a, b) => b.ep_loss - a.ep_loss)
  const brilliant = key.filter((m) => m.ep_label === 'brilliant')

  const title = winner ? `${playerName(review, winner)} won` : result === '1/2-1/2' ? 'A draw' : 'Game review'
  let body: string
  if (bad.length === 0) {
    body = 'No mistakes or blunders by either side. A clean game decided by small edges.'
  } else {
    const first = bad[0]
    body = `The turning point: ${san(first)} by ${playerName(review, first.mover)} (${LABELS[first.ep_label].name.toLowerCase()}, chances ${pct(first.ep_best)} → ${pct(first.ep_after)}).`
    if (bad.length > 1) body += ` Also look at ${bad.slice(1, 3).map(san).join(' and ')}.`
  }
  if (brilliant.length) body += ` Don’t miss ${san(brilliant[0])}, a brilliant sacrifice by ${playerName(review, brilliant[0].mover)}.`
  return { title, body }
}
