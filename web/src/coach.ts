// Coach bubble text, filled in from the review numbers (no LLM).
import { BAD_LABELS, describe, LABELS } from './labels'
import { pct, timeClassLabel } from './format'
import type { Review, ReviewMove } from './types'

export interface CoachText {
  title: string
  body: string
  note?: string
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

  let body: string
  if (label === 'best') {
    body = `${who}'s chances stay at ${pct(move.ep_after)}.`
  } else if (BAD_LABELS.includes(label)) {
    body = `${who}'s chances dropped from ${pct(move.ep_best)} to ${pct(move.ep_after)}.`
    if (move.best_san) body += ` ${move.best_san} was best.`
  } else {
    body = `${who}'s chances: ${pct(move.ep_after)}.`
    if (move.best_san) body += ` ${move.best_san} was best (${pct(move.ep_best)}).`
  }

  let note: string | undefined
  const evalOnly = move.lichess_label
  if (evalOnly !== label && evalOnly !== 'book' && label !== 'best') {
    const level = levelPhrase(review, move.mover)
    const harsher = move.lichess_loss > move.ep_loss
    note = harsher
      ? `An eval-only review would call this ${describe(evalOnly)}. The engine score drops more, but at ${level} this position is still very playable.`
      : `An eval-only review would call this ${describe(evalOnly)}. The engine score barely moves, but at ${level} this costs real chances.`
  }
  return { title, body, note }
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
  const key = review.moves.filter((m) => review.key_moments.includes(m.ply))
  const keyText = key.slice(0, 3).map((m) => `${m.move_number}${m.mover === 'white' ? '.' : '...'} ${m.san}`)

  let title = winner ? `${playerName(review, winner)} won` : result === '1/2-1/2' ? 'A draw' : 'Game review'
  let body: string
  if (key.length === 0) {
    body = 'No mistakes or blunders by either side. A clean game decided by small edges.'
  } else {
    const first = key[0]
    const loserTurn = first.mover
    title = winner ? `${playerName(review, winner)} won` : title
    body = `The turning point: ${keyText[0]} by ${playerName(review, loserTurn)} (${LABELS[first.ep_label].name.toLowerCase()}, chances ${pct(first.ep_best)} → ${pct(first.ep_after)}).`
    if (keyText.length > 1) body += ` Also look at ${keyText.slice(1).join(' and ')}.`
  }
  return { title, body }
}
