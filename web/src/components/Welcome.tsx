import { Chessboard } from 'react-chessboard'
import { LABELS } from '../labels'
import type { Label } from '../types'
import { LabelIcon } from './LabelIcon'

// The sample game after 5. Nxe5!!, the moment the preview card shows.
const PREVIEW_FEN = 'r2qkbnr/ppp2ppp/2np4/4N3/2B1P1b1/2N5/PPPP1PPP/R1BQK2R b KQkq - 0 5'
const PREVIEW_CHANCES = 0.69
const LEGEND: Label[] = ['brilliant', 'great', 'best', 'inaccuracy', 'mistake', 'blunder']

const STEPS: [string, string][] = [
  ['Pick a game', 'From Chess.com, Lichess, or a pasted PGN.'],
  ['Get every move labelled', 'Stockfish and a rating-aware model, in your browser.'],
  ['Retry your mistakes', 'Find the better move on the board.'],
]

interface Props {
  colors: { light: string; dark: string }
  onSample: () => void
}

export function Welcome({ colors, onSample }: Props) {
  return (
    <div className="welcome">
      <span className="eyebrow">Free · No sign-up · Runs in your browser</span>
      <h1>See the moves that <span className="hl">decided</span> your game</h1>
      <p className="welcome-pitch">
        ChessCoach labels every move like Chess.com’s Game Review, shows where your chances slipped,
        and lets you replay the critical moments.
      </p>

      <figure className="preview">
        <div className="preview-board">
          <div className="preview-eval" aria-hidden>
            <div style={{ height: `${PREVIEW_CHANCES * 100}%` }} />
          </div>
          <div className="preview-squares">
            <Chessboard
              id="preview-board"
              position={PREVIEW_FEN}
              arePiecesDraggable={false}
              areArrowsAllowed={false}
              showBoardNotation={false}
              customSquareStyles={{
                f3: { boxShadow: 'inset 0 0 0 999px var(--sq-highlight)' },
                e5: { boxShadow: 'inset 0 0 0 999px var(--sq-highlight)' },
              }}
              customDarkSquareStyle={{ backgroundColor: colors.dark }}
              customLightSquareStyle={{ backgroundColor: colors.light }}
              customBoardStyle={{ borderRadius: '6px' }}
            />
            {/* e5: fifth file, fourth row from the top. */}
            <span className="preview-badge" style={{ left: 'calc(62.5% - 13px)', top: 'calc(37.5% - 11px)' }}>
              <LabelIcon label="brilliant" size={26} />
            </span>
          </div>
        </div>

        <figcaption className="preview-side">
          <div className="preview-note">
            <div className="preview-note-title">
              <LabelIcon label="brilliant" size={18} />
              <span>5. Nxe5 is brilliant</span>
            </div>
            <p>Alice gives up the queen and the position holds: her chances go up to 69%.</p>
          </div>
          <ul className="preview-legend" aria-label="Move labels">
            {LEGEND.map((l) => (
              <li key={l}>
                <LabelIcon label={l} size={16} />
                {LABELS[l].name}
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn-secondary btn-block" onClick={onSample}>
            Review this game
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
              <path d="M5 12h14m-6-6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </figcaption>
      </figure>

      <ol className="steps">
        {STEPS.map(([title, text], i) => (
          <li key={title}>
            <span className="step-num">{i + 1}</span>
            <strong>{title}</strong>
            <p>{text}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
