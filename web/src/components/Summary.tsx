import { useState, type CSSProperties } from 'react'
import type { CoachText } from '../coach'
import { pct } from '../format'
import { BAD_LABELS, GRAPH_LABELS, LABEL_ORDER, LABELS } from '../labels'
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
  axisLabel?: string
  onStart: () => void
  onJump: (ply: number) => void
}

const PHASES: [Phase, string][] = [['opening', 'Opening'], ['middlegame', 'Middlegame'], ['endgame', 'Endgame']]

function GradeCell({ g, side }: { g: PhaseGrade | null; side: 'white' | 'black' }) {
  if (!g) return <td className={`pt-cell pt-${side} muted`}>–</td>
  return (
    <td className={`pt-cell pt-${side}`} title={`${g.accuracy.toFixed(1)} accuracy over ${g.moves} moves in this phase`}>
      <span><LabelIcon label={g.grade} size={20} /><span className="pt-acc">{g.accuracy.toFixed(1)}</span></span>
    </td>
  )
}

function CountCell({ n, max, color, side }: { n: number; max: number; color: string; side: 'white' | 'black' }) {
  return (
    <td className={`lt-count lt-${side} ${n ? '' : 'lt-zero'}`}>
      {n > 0 && <span className="lt-bar" aria-hidden="true" style={{ '--lc': color, '--w': n / max } as CSSProperties} />}
      <span className="lt-n">{n || '–'}</span>
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

export function Summary({ review, coach, graphValues, axisLabel, onStart, onJump }: Props) {
  const [showAll, setShowAll] = useState(false)
  const { white: ws, black: bs } = review.summary
  const used = LABEL_ORDER.filter((l) => ws.labels[l] || bs.labels[l])
  const visibleLabels = showAll ? LABEL_ORDER : used
  const hidden = LABEL_ORDER.length - used.length
  const maxCount = Math.max(1, ...LABEL_ORDER.flatMap((l) => [ws.labels[l] ?? 0, bs.labels[l] ?? 0]))
  // The first error label shown starts the second group.
  const firstBad = visibleLabels.find((l) => BAD_LABELS.includes(l))
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
        <Graph values={graphValues} moves={review.moves} chances={review.positions.map((p) => p.white_ep)} current={null} markers={markers} onSelect={onJump} axisLabel={axisLabel} />
      </div>

      <section className="sum-section players-acc" aria-label="Accuracy">
        <h3 className="sum-h">Accuracy <InfoTip label="Accuracy">{ACCURACY_HELP}</InfoTip></h3>
        <div className="pa">
          <div className="pa-name"><span className="side-chip side-white" aria-label="White" />{white}</div>
          <div className="acc">{ws.accuracy.toFixed(1)}</div>
        </div>
        <div className="pa">
          <div className="pa-name"><span className="side-chip side-black" aria-label="Black" />{black}</div>
          <div className="acc">{bs.accuracy.toFixed(1)}</div>
        </div>
        {(ws.estimated_rating || bs.estimated_rating) && (
          <div
            className="game-rating"
            title="The rating of players who typically play as well as you did in this game, judged by how much each move gave away."
          >
            <GameRating est={ws.estimated_rating} rating={review.white_elo} />
            <span className="gr-mid">Game rating <InfoTip label="Game rating">{RATING_HELP}</InfoTip></span>
            <GameRating est={bs.estimated_rating} rating={review.black_elo} />
          </div>
        )}
      </section>

      <section className="sum-section" aria-label="Moves">
        <h3 className="sum-h">
          Moves
          {hidden > 0 && (
            <button type="button" className="sum-link" aria-expanded={showAll} onClick={() => setShowAll((s) => !s)}>
              {showAll ? 'Hide empty' : `Show all ${LABEL_ORDER.length}`}
            </button>
          )}
        </h3>
        <table className="label-table">
          <thead className="sr-only">
            <tr><th>{white}</th><th>Label</th><th>{black}</th></tr>
          </thead>
          <tbody>
            {visibleLabels.map((l) => (
              <tr key={l} className={l === firstBad && l !== visibleLabels[0] ? 'lt-group' : undefined}>
                <CountCell n={ws.labels[l] ?? 0} max={maxCount} color={LABELS[l].color} side="white" />
                <td className="lt-name">
                  <span>
                    <LabelIcon label={l} size={18} />
                    {LABELS[l].name}
                  </span>
                </td>
                <CountCell n={bs.labels[l] ?? 0} max={maxCount} color={LABELS[l].color} side="black" />
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="sum-section" aria-label="Phases">
        <h3 className="sum-h">Phases <InfoTip label="Phases">Each grade summarizes move accuracy during the opening, middlegame or endgame. The number is that phase’s accuracy; a dash means there were no moves to grade.</InfoTip></h3>
        <table className="label-table phase-table">
          <tbody>
            {PHASES.map(([ph, name]) => (
              <tr key={ph}>
                <GradeCell g={ws.phases?.[ph] ?? null} side="white" />
                <td className="lt-name"><span>{name}</span></td>
                <GradeCell g={bs.phases?.[ph] ?? null} side="black" />
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {keyMoves.length > 0 && (
        <section className="sum-section key-moments" aria-label="Key moments">
          <h3 className="sum-h">Key moments</h3>
          {keyMoves.map((m) => (
            <button
              type="button"
              key={m.ply}
              className="key-item"
              onClick={() => onJump(m.ply)}
              aria-label={`${m.move_number}${m.mover === 'white' ? '.' : '...'} ${m.san}, ${LABELS[m.ep_label].name.toLowerCase()}: ${pct(m.ep_best)} to ${pct(m.ep_after)}`}
            >
              <LabelIcon label={m.ep_label} size={20} />
              <span className="key-move">
                <span><span className="key-num">{m.move_number}{m.mover === 'white' ? '.' : '…'}</span> {m.san}</span>
                <small><span className={`side-chip side-${m.mover}`} />{m.mover === 'white' ? white : black}</small>
              </span>
              <span className="key-drop">
                <span className="key-pct">{pct(m.ep_best)} → <strong>{pct(m.ep_after)}</strong></span>
                <span className="key-track" aria-hidden="true" style={{ '--lc': LABELS[m.ep_label].color, '--from': m.ep_best, '--to': m.ep_after } as CSSProperties}>
                  <span />
                </span>
              </span>
              <svg className="key-chev" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          ))}
        </section>
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
