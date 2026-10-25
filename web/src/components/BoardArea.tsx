import { Chess } from 'chess.js'
import { createContext, forwardRef, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Chessboard } from 'react-chessboard'
import type { CustomSquareProps, Piece, Square } from 'react-chessboard/dist/chessboard/types'
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

/** Retry mode: the board takes moves for `side`; onMove returns false to reject (piece snaps back). */
export interface BoardInput {
  side: Side
  onMove: (from: string, to: string, promotion?: string) => boolean
}

interface Props {
  fen: string
  input?: BoardInput | null
  // Board accepts drags for this whole session; `input` decides whether a drag is allowed right now.
  // react-chessboard wires up dragging only at mount, so toggling arePiecesDraggable later doesn't work;
  // changing inputSession remounts the board instead.
  inputSession?: string | null
  orientation: Side
  white: PlayerInfo
  black: PlayerInfo
  lastMove: { from: string; to: string } | null
  badge: Badge | null
  arrow: { from: string; to: string } | null
  whiteShare: number
  evalText: string
}

export function BoardArea({ fen, input, inputSession, orientation, white, black, lastMove, badge, arrow, whiteShare, evalText }: Props) {
  // Click-to-move (touch friendly): first click picks a piece, second picks the target.
  const [selected, setSelected] = useState<string | null>(null)
  useEffect(() => setSelected(null), [fen, input])

  const targets = useMemo(() => {
    if (!input || !selected) return []
    try {
      return new Chess(fen).moves({ square: selected as Square, verbose: true }).map((m) => m.to)
    } catch {
      return []
    }
  }, [fen, input, selected])

  const squareStyles = useMemo(() => {
    const s: Record<string, Record<string, string>> = {}
    if (lastMove) {
      for (const sq of [lastMove.from, lastMove.to]) s[sq] = { boxShadow: 'inset 0 0 0 999px var(--sq-highlight)' }
    }
    if (selected) s[selected] = { boxShadow: 'inset 0 0 0 999px var(--sq-select)' }
    for (const t of targets) s[t] = { ...s[t], backgroundImage: 'radial-gradient(circle, var(--sq-dot) 22%, transparent 24%)' }
    return s
  }, [lastMove, selected, targets])

  const myColor = input ? (input.side === 'white' ? 'w' : 'b') : null
  // react-chessboard can call drag/drop handlers from an earlier render; read the current values via refs.
  const live = useRef({ input, fen, myColor })
  live.current = { input, fen, myColor }
  const isPromotion = (from: string, to: string) => {
    try {
      const p = new Chess(live.current.fen).get(from as Square)
      return !!p && p.type === 'p' && (to[1] === '8' || to[1] === '1')
    } catch {
      return false
    }
  }

  function onSquareClick(square: Square, piece: Piece | undefined) {
    if (!input) return
    if (piece && piece[0] === myColor) {
      setSelected(square === selected ? null : square)
      return
    }
    if (selected && targets.includes(square)) {
      input.onMove(selected, square, isPromotion(selected, square) ? 'q' : undefined)
      setSelected(null)
    } else setSelected(null)
  }

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
    <div className={`board-area ${input ? 'board-input' : ''}`}>
      <PlayerBar p={top} />
      <div className="board-row">
        <div className={`eval-bar ${orientation === 'black' ? 'eval-flipped' : ''}`} aria-label={`Evaluation ${evalText}`}>
          <div className="eval-fill" style={{ height: `${bottomShare * 100}%` }} />
          <span className={`eval-text ${bottomAhead ? 'eval-bottom' : 'eval-top'}`}>{evalText}</span>
        </div>
        <div className="board">
          <BadgeContext.Provider value={badge}>
            <Chessboard
              key={inputSession ?? 'view'}
              id="review-board"
              position={fen}
              boardOrientation={orientation}
              arePiecesDraggable={!!inputSession}
              isDraggablePiece={({ piece }) => !!live.current.input && piece[0] === live.current.myColor}
              onPieceDrop={(from, to, piece) => {
                const cur = live.current.input
                if (!cur) return false
                const promo = isPromotion(from, to) ? piece[1].toLowerCase() : undefined
                return cur.onMove(from, to, promo)
              }}
              onSquareClick={onSquareClick}
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
