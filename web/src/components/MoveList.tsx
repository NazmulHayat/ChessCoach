import { useEffect, useRef } from 'react'
import type { ReviewMove } from '../types'
import { LabelIcon } from './LabelIcon'

interface Props {
  moves: ReviewMove[]
  current: number // ply shown on the board (0 = start)
  onSelect: (ply: number) => void
}

export function MoveList({ moves, current, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = box.current?.querySelector<HTMLElement>('.move-cell.current')
    el?.scrollIntoView({ block: 'nearest' })
  }, [current])

  const rows: [ReviewMove, ReviewMove | undefined][] = []
  for (let i = 0; i < moves.length; i += 2) {
    // Games that start with black to move are rare in review; pair in order.
    rows.push([moves[i], moves[i + 1]])
  }

  const cell = (m: ReviewMove | undefined) =>
    m ? (
      <button type="button" data-ply={m.ply} className={`move-cell ${m.ply === current ? 'current' : ''}`} onClick={() => onSelect(m.ply)}>
        <LabelIcon label={m.ep_label} size={16} />
        <span>{m.san}</span>
      </button>
    ) : (
      <span />
    )

  return (
    <div className="move-list" ref={box}>
      {rows.map(([w, b]) => (
        <div className="move-row" key={w.ply}>
          <span className="move-num">{w.move_number}.</span>
          {cell(w)}
          {cell(b)}
        </div>
      ))}
    </div>
  )
}
