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
    const list = box.current
    if (el && list) {
      const cellRect = el.getBoundingClientRect()
      const listRect = list.getBoundingClientRect()
      if (cellRect.top < listRect.top) list.scrollTop -= listRect.top - cellRect.top
      else if (cellRect.bottom > listRect.bottom) list.scrollTop += cellRect.bottom - listRect.bottom
    }
  }, [current])

  const rows: [ReviewMove, ReviewMove | undefined][] = []
  for (let i = 0; i < moves.length; i += 2) {
    // Games that start with black to move are rare in review; pair in order.
    rows.push([moves[i], moves[i + 1]])
  }

  const cell = (m: ReviewMove | undefined) =>
    m ? (
      <button type="button" aria-current={m.ply === current ? 'step' : undefined} aria-label={`${m.move_number}${m.mover === 'white' ? '.' : '...'} ${m.san}`} data-ply={m.ply} className={`move-cell ${m.ply === current ? 'current' : ''}`} onClick={() => onSelect(m.ply)}>
        <LabelIcon label={m.ep_label} size={16} />
        <span>{m.san}</span>
      </button>
    ) : (
      <span />
    )

  return (
    <div className="move-list" data-tour="moves" ref={box}>
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
