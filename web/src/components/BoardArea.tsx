import { Chess } from 'chess.js'
import { createContext, forwardRef, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Chessboard } from 'react-chessboard'
import type { CustomSquareProps, Piece, Square } from 'react-chessboard/dist/chessboard/types'
import { useReducedMotion } from '../lib/motion'
import { highlight } from '../lib/highlight'
import { capturedFrom, type Captured, type PieceType } from '../lib/material'
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
        <span className="square-badge" key={`${badge.square}-${badge.label}`}>
          <LabelIcon label={badge.label} size={26} />
        </span>
      )}
    </div>
  )
})

// Captured opponent pieces: filled glyphs (U+FE0E keeps ♟ from turning into an emoji), coloured per side in CSS.
const GLYPH: Record<PieceType, string> = { q: '♛\uFE0E', r: '♜\uFE0E', b: '♝\uFE0E', n: '♞\uFE0E', p: '♟\uFE0E' }

function CapturedPieces({ side, cap }: { side: Side; cap: Captured }) {
  const theirs = side === 'white' ? 'black' : 'white'
  const groups: PieceType[][] = []
  for (const t of cap.pieces) {
    const last = groups[groups.length - 1]
    if (last && last[0] === t) last.push(t)
    else groups.push([t])
  }
  return (
    <span className="captured" aria-label={`Captured: ${cap.pieces.join(' ') || 'none'}`}>
      {groups.map((g, i) => (
        <span key={i} className="cap-group">
          {g.map((t, j) => (
            <span key={j} className={`cap-piece cap-${theirs}`}>{GLYPH[t]}</span>
          ))}
        </span>
      ))}
      {cap.lead > 0 && <span className="cap-lead">+{cap.lead}</span>}
    </span>
  )
}

function PlayerBar({ p, cap }: { p: PlayerInfo; cap: Captured }) {
  return (
    <div className="player-bar">
      <span className={`side-chip side-${p.side}`} aria-label={p.side === 'white' ? 'White' : 'Black'} />
      <div className="player-id">
        <div className="player-line">
          <span className="player-name">{p.name}</span>
          {p.elo !== null && <span className="player-elo">{p.elo}</span>}
        </div>
        <CapturedPieces side={p.side} cap={cap} />
      </div>
      {p.clock && <span className={`clock clock-${p.side}`}>{p.clock}</span>}
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
  colors?: { light: string; dark: string }
  onStep?: (direction: -1 | 1) => void
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1']

/** The club mat: a green margin around the board with printed coordinates; `side` slots in beside the ranks (the eval bar). */
export function Mat({ orientation, side, children }: { orientation: Side; side?: ReactNode; children: ReactNode }) {
  const files = orientation === 'white' ? FILES : [...FILES].reverse()
  const ranks = orientation === 'white' ? RANKS : [...RANKS].reverse()
  const fileRow = (pos: string) => <div className={`mat-files mat-${pos}`} aria-hidden>{files.map((f) => <span key={f}>{f}</span>)}</div>
  const rankCol = (pos: string) => <div className={`mat-ranks mat-${pos}`} aria-hidden>{ranks.map((r) => <span key={r}>{r}</span>)}</div>
  return (
    <div className={`mat ${side ? 'mat-with-side' : ''}`}>
      {side}
      {fileRow('top')}
      {rankCol('left')}
      {children}
      {rankCol('right')}
      {fileRow('bottom')}
    </div>
  )
}

export function BoardArea({ fen, input, inputSession, orientation, white, black, lastMove, badge, arrow, whiteShare, evalText, colors, onStep }: Props) {
  const swipe = useRef<{ id: number; x: number; y: number; time: number } | null>(null)
  const reducedMotion = useReducedMotion()
  const captured = useMemo(() => capturedFrom(fen), [fen])
  // Click-to-move (touch friendly): first click picks a piece, second picks the target.
  const [selected, setSelected] = useState<string | null>(null)
  useEffect(() => setSelected(null), [fen, input])

  const targetMoves = useMemo(() => {
    if (!input || !selected) return []
    try {
      return new Chess(fen).moves({ square: selected as Square, verbose: true })
    } catch {
      return []
    }
  }, [fen, input, selected])
  const targets = useMemo(() => targetMoves.map((m) => m.to as string), [targetMoves])

  const squareStyles = useMemo(() => {
    const s: Record<string, Record<string, string>> = {}
    if (lastMove) {
      for (const sq of [lastMove.from, lastMove.to]) s[sq] = highlight(sq)
    }
    if (selected) s[selected] = { boxShadow: 'inset 0 0 0 999px var(--sq-select)' }
    // Dot on empty targets, ring on captures (a dot would hide under the piece).
    for (const m of targetMoves) {
      const ring = m.captured !== undefined
      s[m.to] = {
        ...s[m.to],
        backgroundImage: ring
          ? 'radial-gradient(circle, transparent 60%, var(--sq-dot) 62%, var(--sq-dot) 74%, transparent 76%)'
          : 'radial-gradient(circle, var(--sq-dot) 22%, transparent 24%)',
      }
    }
    return s
  }, [lastMove, selected, targetMoves])

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
    () => (arrow ? [[arrow.from as Square, arrow.to as Square, 'var(--arrow)'] as [Square, Square, string]] : []),
    [arrow],
  )

  const top = orientation === 'white' ? black : white
  const bottom = orientation === 'white' ? white : black
  // Eval bar fills from the bottom with the bottom player's colour.
  const bottomShare = orientation === 'white' ? whiteShare : 1 - whiteShare
  const bottomAhead = bottomShare >= 0.5

  return (
    <div className={`board-area ${input ? 'board-input' : ''}`}>
      <PlayerBar p={top} cap={captured[top.side]} />
      <Mat orientation={orientation} side={
        <div className={`eval-bar ${orientation === 'black' ? 'eval-flipped' : ''}`} aria-label={`${whiteShare >= .5 ? 'White' : 'Black'} ahead: ${evalText}`}>
          <div className="eval-fill" style={{ height: `${bottomShare * 100}%` }} />
          <span key={evalText} className={`eval-text ${bottomAhead ? 'eval-bottom' : 'eval-top'}`}>{evalText}</span>
        </div>
      }>
        <div className="board" role="group" aria-label={inputSession ? 'Retry position: drag a piece or tap its start and destination' : 'Chessboard'}
          style={{ touchAction: inputSession ? 'none' : 'pan-y' }}
          onPointerDown={(e) => {
            if (onStep && !inputSession && e.pointerType !== 'mouse') swipe.current = { id: e.pointerId, x: e.clientX, y: e.clientY, time: performance.now() }
          }}
          onPointerCancel={() => { swipe.current = null }}
          onPointerUp={(e) => {
            const start = swipe.current
            swipe.current = null
            if (!start || start.id !== e.pointerId || inputSession || !onStep) return
            const dx = e.clientX - start.x
            const dy = e.clientY - start.y
            if (performance.now() - start.time < 900 && Math.abs(dx) > 42 && Math.abs(dx) > Math.abs(dy) * 1.4) onStep(dx < 0 ? 1 : -1)
          }}
        >
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
              animationDuration={reducedMotion ? 0 : 200}
              customArrows={arrows}
              customSquare={BadgeSquare}
              customSquareStyles={squareStyles}
              customDarkSquareStyle={{ backgroundColor: colors?.dark ?? 'var(--sq-dark)' }}
              customLightSquareStyle={{ backgroundColor: colors?.light ?? 'var(--sq-light)' }}
              customBoardStyle={{ borderRadius: '2px', boxShadow: 'var(--shadow-board)' }}
              showBoardNotation={false}
            />
          </BadgeContext.Provider>
        </div>
      </Mat>
      <PlayerBar p={bottom} cap={captured[bottom.side]} />
    </div>
  )
}
