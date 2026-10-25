// Coach bubble text, filled in from the review numbers (no LLM).
import { BAD_LABELS, describe, LABELS } from './labels'
import { engineScore, timeClassLabel } from './format'
import type { RetryState } from './App'
import type { Review, ReviewMove, ReviewPosition } from './types'

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

/** Who stands better, in words, from a white-POV engine score (Chess.com-style: no percentages). */
function standing(review: Review, p: ReviewPosition): string {
  const white = playerName(review, 'white')
  const black = playerName(review, 'black')
  if (p.mate !== null) {
    if (p.mate === 0) return 'Checkmate'
    return `${p.mate > 0 ? white : black} has mate in ${Math.abs(p.mate)}`
  }
  const cp = p.cp ?? 0
  const side = cp > 0 ? white : black
  const a = Math.abs(cp)
  if (a < 50) return 'The position is equal'
  if (a < 150) return `${side} is slightly better`
  if (a < 300) return `${side} is better`
  return `${side} is winning`
}

/** "Evaluation: +0.6 → -3.6" (white's view, like Chess.com and Lichess). */
function evalChange(review: Review, move: ReviewMove): string {
  return `Evaluation: ${engineScore(review.positions[move.ply - 1])} → ${engineScore(review.positions[move.ply])}`
}

const capitalize = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

export function moveCoach(review: Review, move: ReviewMove): CoachText {
  const label = move.ep_label
  const title = `${move.san} is ${describe(label)}`
  const after = review.positions[move.ply]

  if (label === 'book') {
    const opening = review.headers.Opening || review.headers.ECOUrl?.split('/').pop()?.replace(/-/g, ' ')
    return { title, body: opening ? `A known opening move: ${opening}.` : 'This move follows a known opening.' }
  }

  const opp = playerName(review, move.mover === 'white' ? 'black' : 'white')
  const now = `${standing(review, after)}.`
  const bestWas = move.best_san && move.best_san !== move.san ? ` ${move.best_san} was best.` : ''
  let body: string
  if (label === 'brilliant') {
    body = `Gives up ${move.sacrifice_piece ? `the ${move.sacrifice_piece}` : materialPhrase(move.sacrifice)}, and it works. ${now}`
  } else if (label === 'great') {
    body = `The only good move here${move.second_san ? `: anything else, even ${move.second_san}, was much worse` : ''}. ${now}`
  } else if (label === 'best') {
    body = now
  } else if (label === 'miss') {
    body = `${opp} had just made a mistake, and this lets them off the hook.${bestWas} ${now}`
    if (move.tactic) body = `${capitalize(move.tactic)}. ${body}`
  } else if (BAD_LABELS.includes(label)) {
    body = `${move.tactic ? `${capitalize(move.tactic)}. ` : ''}${now}${bestWas}`
  } else {
    body = `${now}${bestWas}`
  }
  const line = BAD_LABELS.includes(label) && move.best_line_san.length > 1 ? `Best: ${formatLine(move.best_line_san, move.ply)}` : undefined
  const note = label === 'best' || label === 'great' || label === 'brilliant' ? undefined : evalChange(review, move)
  return { title, body: body.trim(), note, line }
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
        body: exact ? 'That’s the best move.' : `That works just as well as ${move.best_san}.`,
        line: exact ? formatLine(move.best_line_san, move.ply) : undefined,
      }
    }
    case 'wrong':
    case 'solution': {
      const tried = r ? `${r.san} isn’t the best move here.` : ''
      if (retry.phase === 'wrong') return { title: 'Not quite', body: `${tried} Try another move.` }
      return {
        title: `The move was ${move.best_san}`,
        body: tried,
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
    body = 'No mistakes or blunders by either side. Explore the key moments to see how the game unfolded.'
  } else {
    const first = bad[0]
    body = `The turning point: ${san(first)} by ${playerName(review, first.mover)}, a ${LABELS[first.ep_label].name.toLowerCase()}.`
    if (bad.length > 1) body += ` Also look at ${bad.slice(1, 3).map(san).join(' and ')}.`
  }
  if (brilliant.length) body += ` Don’t miss ${san(brilliant[0])}, a brilliant sacrifice by ${playerName(review, brilliant[0].mover)}.`
  return { title, body }
}
