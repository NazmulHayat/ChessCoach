import { createContext, forwardRef, useContext, useMemo } from 'react'
import { Chessboard } from 'react-chessboard'
import type { CustomSquareProps, Square } from 'react-chessboard/dist/chessboard/types'
import { initials } from '../format'
import type { Label, Side } from '../types'
import { LabelIcon } from './LabelIcon'

export interface PlayerInfo {
  name: string
  elo: number | null
  side: Side
  clock: string | null
}

interface Badge {
  square: string
  label: Label
}

// The square renderer must be a stable component, so the current badge reaches it via context.
const BadgeContext = createContext<Badge | null>(null)

const BadgeSquare = forwardRef<HTMLDivElement, CustomSquareProps>(function BadgeSquare({ children, square, style }, ref) {
  const badge = useContext(BadgeContext)
  return (
    <div ref={ref} style={{ ...style, position: 'relative' }}>
      {children}
      {badge && badge.square === square && (
        <span className="square-badge">
          <LabelIcon label={badge.label} size={26} />
        </span>
      )}
    </div>
  )
})

function PlayerBar({ p }: { p: PlayerInfo }) {
  return (
    <div className="player-bar">
      <div className={`avatar ${p.side === 'white' ? 'avatar-w' : ''}`}>{initials(p.name)}</div>
      <span className="player-name">{p.name}</span>
      {p.elo !== null && <span className="player-elo">({p.elo})</span>}
      <span className={`clock ${p.side === 'white' ? 'clock-w' : ''}`}>{p.clock ?? '—'}</span>
    </div>
  )
}

interface Props {
  fen: string
  orientation: Side
  white: PlayerInfo
  black: PlayerInfo
  lastMove: { from: string; to: string } | null
  badge: Badge | null
  arrow: { from: string; to: string } | null
  whiteShare: number
  evalText: string
}

export function BoardArea({ fen, orientation, white, black, lastMove, badge, arrow, whiteShare, evalText }: Props) {
  const squareStyles = useMemo(() => {
    const s: Record<string, Record<string, string>> = {}
    if (lastMove) {
      for (const sq of [lastMove.from, lastMove.to]) s[sq] = { boxShadow: 'inset 0 0 0 999px var(--sq-highlight)' }
    }
    return s
  }, [lastMove])

  const arrows = useMemo(
    () => (arrow ? [[arrow.from as Square, arrow.to as Square, 'rgba(255, 170, 0, 0.82)'] as [Square, Square, string]] : []),
    [arrow],
  )

  const top = orientation === 'white' ? black : white
  const bottom = orientation === 'white' ? white : black
  // Eval bar fills from the bottom with the bottom player's colour.
  const bottomShare = orientation === 'white' ? whiteShare : 1 - whiteShare
  const bottomAhead = bottomShare >= 0.5

  return (
    <div className="board-area">
      <PlayerBar p={top} />
      <div className="board-row">
        <div className={`eval-bar ${orientation === 'black' ? 'eval-flipped' : ''}`} aria-label={`Evaluation ${evalText}`}>
          <div className="eval-fill" style={{ height: `${bottomShare * 100}%` }} />
          <span className={`eval-text ${bottomAhead ? 'eval-bottom' : 'eval-top'}`}>{evalText}</span>
        </div>
        <div className="board">
          <BadgeContext.Provider value={badge}>
            <Chessboard
              id="review-board"
              position={fen}
              boardOrientation={orientation}
              arePiecesDraggable={false}
              areArrowsAllowed={false}
              animationDuration={180}
              customArrows={arrows}
              customSquare={BadgeSquare}
              customSquareStyles={squareStyles}
              customDarkSquareStyle={{ backgroundColor: 'var(--sq-dark)' }}
              customLightSquareStyle={{ backgroundColor: 'var(--sq-light)' }}
              customBoardStyle={{ borderRadius: '4px', boxShadow: '0 6px 24px rgba(0,0,0,.35)' }}
            />
          </BadgeContext.Provider>
        </div>
      </div>
      <PlayerBar p={bottom} />
    </div>
  )
}
