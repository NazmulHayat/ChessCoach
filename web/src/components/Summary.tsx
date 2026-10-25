import { useState } from 'react'
import type { CoachText } from '../coach'
import { pct } from '../format'
import { GRAPH_LABELS, LABEL_ORDER, LABELS } from '../labels'
import type { Phase, PhaseGrade, Review } from '../types'
import { ACCURACY_HELP, RATING_HELP } from '../lib/help'
import { InfoTip } from './InfoTip'
import { Coach } from './Coach'
import { Graph } from './Graph'
import { LabelIcon } from './LabelIcon'

interface Props {
  review: Review
  coach: CoachText
  graphValues: number[]
  onStart: () => void
  onJump: (ply: number) => void
}

const PHASES: [Phase, string][] = [['opening', 'Opening'], ['middlegame', 'Middlegame'], ['endgame', 'Endgame']]

function GradeCell({ g }: { g: PhaseGrade | null }) {
  if (!g) return <td className="lt-count muted">–</td>
  return (
    <td className="lt-count">
      <InfoTip label="Phase grade" trigger={<LabelIcon label={g.grade} size={22} />}>
        {g.accuracy.toFixed(1)} accuracy over {g.moves} moves in this phase. The icon summarizes how accurately these moves were played; a dash means there were no moves to grade.
      </InfoTip>
    </td>
  )
}

function GameRating({ est, rating }: { est: Review['summary']['white']['estimated_rating']; rating: number }) {
  if (!est) return <span className="gr-val">–</span>
  // "Played like": the rating of players who typically play this well, as Chess.com's game rating does.
  return (
    <span className="gr-val" title={`Played like a ${est.plays_like}. Your rating: ${rating}.`}>
      {est.plays_like}
    </span>
  )
}

export function Summary({ review, coach, graphValues, onStart, onJump }: Props) {
  const [showAll, setShowAll] = useState(false)
  const visibleLabels = LABEL_ORDER.filter((l) => showAll || review.summary.white.labels[l] || review.summary.black.labels[l])
  const white = review.headers.White || 'White'
  const black = review.headers.Black || 'Black'
  const markers = review.moves.filter((m) => GRAPH_LABELS.includes(m.ep_label) && m.ep_label !== 'inaccuracy').map((m) => ({ ply: m.ply, label: m.ep_label }))
  const keyMoves = review.moves.filter((m) => review.key_moments.includes(m.ply))
  const converted = review.rating_pool === 'chesscom'

  return (
    <div className="panel-body summary">
      <div className="summary-scroll">
      <Coach text={coach} />
      <div className="graph-wrap">
        <Graph values={graphValues} moves={review.moves} chances={review.positions.map((p) => p.white_ep)} current={null} markers={markers} onSelect={onJump} />
      </div>

      <div className="players-acc">
        <div className="pa-heading">Accuracy <InfoTip label="Accuracy">{ACCURACY_HELP}</InfoTip></div>
        <div className="pa">
          <div className="avatar avatar-w avatar-lg">{white.charAt(0).toUpperCase()}</div>
          <div className="pa-name">{white}</div>
          <div className="acc acc-w">{review.summary.white.accuracy.toFixed(1)}</div>
        </div>
        <div className="pa">
          <div className="avatar avatar-lg">{black.charAt(0).toUpperCase()}</div>
          <div className="pa-name">{black}</div>
          <div className="acc acc-b">{review.summary.black.accuracy.toFixed(1)}</div>
        </div>
      </div>

      {(review.summary.white.estimated_rating || review.summary.black.estimated_rating) && (
        <div
          className="game-rating"
          title="The rating of players who typically play as well as you did in this game, judged by how much each move gave away."
        >
          <GameRating est={review.summary.white.estimated_rating} rating={review.white_elo} />
          <span className="gr-mid">Game rating <InfoTip label="Game rating">{RATING_HELP}</InfoTip></span>
          <GameRating est={review.summary.black.estimated_rating} rating={review.black_elo} />
        </div>
      )}

      <table className="label-table">
        <tbody>
          {visibleLabels.map((l) => (
            <tr key={l}>
              <td className="lt-count" style={{ color: LABELS[l].color }}>
                {review.summary.white.labels[l] ?? 0}
              </td>
              <td className="lt-name">
                <span>
                  <LabelIcon label={l} size={18} />
                  {LABELS[l].name}
                </span>
              </td>
              <td className="lt-count" style={{ color: LABELS[l].color }}>
                {review.summary.black.labels[l] ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" className="btn btn-ghost btn-sm label-toggle" aria-expanded={showAll} onClick={() => setShowAll((s) => !s)}>
        {showAll ? 'Hide empty labels' : 'Show all labels'}
      </button>

      <div className="phase-heading">Phase grades <InfoTip label="Phase grades">Each grade summarizes move accuracy during the opening, middlegame or endgame. Tap a grade for its accuracy and move count.</InfoTip></div>
      <table className="label-table phase-table">
        <tbody>
          {PHASES.map(([ph, name]) => (
            <tr key={ph}>
              <GradeCell g={review.summary.white.phases?.[ph] ?? null} />
              <td className="lt-name"><span>{name}</span></td>
              <GradeCell g={review.summary.black.phases?.[ph] ?? null} />
            </tr>
          ))}
        </tbody>
      </table>

      {keyMoves.length > 0 && (
        <div className="key-moments">
          <div className="section-title">Key moments</div>
          {keyMoves.map((m) => (
            <button type="button" key={m.ply} className="key-item" onClick={() => onJump(m.ply)}>
              <LabelIcon label={m.ep_label} size={18} />
              <span className="key-move">
                {m.move_number}
                {m.mover === 'white' ? '.' : '...'} {m.san}
              </span>
              <span className="muted">
                {pct(m.ep_best)} → {pct(m.ep_after)}
              </span>
            </button>
          ))}
        </div>
      )}

      <p className="fine-print">
        {converted
          ? `Chess.com ratings converted to the Lichess scale for the model (${review.white_elo} → ~${review.white_model_elo}, ${review.black_elo} → ~${review.black_model_elo}). `
          : ''}
        Stockfish depth {review.engine_depth}. Labels use expected-points loss at each player’s rating, clock and time control.
      </p>
      </div>

      <div className="panel-actions">
        <button type="button" className="btn btn-primary btn-block btn-lg" onClick={onStart}>
          Start Review
        </button>
      </div>
    </div>
  )
}
