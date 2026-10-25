import type { CoachText } from '../coach'
import { initials, pct } from '../format'
import { GRAPH_LABELS, LABEL_ORDER, LABELS } from '../labels'
import type { Phase, PhaseGrade, Review } from '../types'
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
    <td className="lt-count" title={`${g.accuracy.toFixed(1)} accuracy over ${g.moves} moves`}>
      <span className="grade-cell">
        <LabelIcon label={g.grade} size={22} />
      </span>
    </td>
  )
}

function GameRating({ est, rating }: { est: Review['summary']['white']['estimated_rating']; rating: number }) {
  if (!est) return <span className="gr-val">–</span>
  const diff = est.rating - rating
  return (
    <span className="gr-val" title={`Range ${est.low}–${est.high}`}>
      {est.rating}
      <span className={`gr-diff ${diff > 0 ? 'up' : diff < 0 ? 'down' : ''}`}>{diff > 0 ? `+${diff}` : diff < 0 ? `${diff}` : '±0'}</span>
    </span>
  )
}

export function Summary({ review, coach, graphValues, onStart, onJump }: Props) {
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
        <Graph values={graphValues} current={null} markers={markers} onSelect={onJump} />
      </div>

      <div className="players-acc">
        <div className="pa">
          <div className="avatar avatar-w avatar-lg">{initials(white)}</div>
          <div className="pa-name">{white}</div>
          <div className="acc acc-w">{review.summary.white.accuracy.toFixed(1)}</div>
        </div>
        <div className="pa-mid">Accuracy</div>
        <div className="pa">
          <div className="avatar avatar-lg">{initials(black)}</div>
          <div className="pa-name">{black}</div>
          <div className="acc acc-b">{review.summary.black.accuracy.toFixed(1)}</div>
        </div>
      </div>

      {(review.summary.white.estimated_rating || review.summary.black.estimated_rating) && (
        <div
          className="game-rating"
          title="How you played compared with players at your rating: your rating moved up or down by how much better or worse your moves were than theirs typically are. One game is a small sample, so it moves less in fast games."
        >
          <GameRating est={review.summary.white.estimated_rating} rating={review.white_elo} />
          <span className="gr-mid">Game rating</span>
          <GameRating est={review.summary.black.estimated_rating} rating={review.black_elo} />
        </div>
      )}

      <table className="label-table">
        <tbody>
          {LABEL_ORDER.map((l) => (
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
