import { useRef, useState } from 'react'
import { LABELS } from '../labels'
import type { Label, ReviewMove } from '../types'

interface Props {
  values: number[] // white's share per ply, 0..1 (index 0 = start position)
  chances?: number[]
  moves?: ReviewMove[]
  current: number | null
  markers: { ply: number; label: Label }[]
  onSelect?: (ply: number) => void
  height?: number
}

const W = 600

export function Graph({ values, chances = values, moves = [], current, markers, onSelect, height = 104 }: Props) {
  const ref = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const n = Math.max(values.length, 2)
  const x = (i: number) => (i / (n - 1)) * W
  const y = (v: number) => height - v * height
  const clamp = (p: number) => Math.max(0, Math.min(values.length - 1, p))
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' L')
  const selected = hover ?? current ?? 0
  const move = moves[selected - 1]
  const description = `${move ? `${move.move_number}${move.mover === 'white' ? '.' : '...'} ${move.san} · ${LABELS[move.ep_label].name}` : 'Starting position'} · White’s chances ${Math.round((chances[selected] ?? .5) * 100)}%`

  function pointerPly(clientX: number) {
    const r = ref.current?.getBoundingClientRect()
    return r ? clamp(Math.round(((clientX - r.left) / r.width) * (n - 1))) : 0
  }

  return (
    <div className="graph-container" onPointerLeave={() => setHover(null)}>
      <svg
        ref={ref}
        className={`graph ${onSelect ? 'graph-clickable' : ''}`}
        style={{ height }}
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        onPointerMove={(e) => setHover(pointerPly(e.clientX))}
        onClick={(e) => onSelect?.(pointerPly(e.clientX))}
        onFocus={() => setHover(current ?? 0)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (!onSelect) return
          let next: number
          if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = clamp(selected + 1)
          else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = clamp(selected - 1)
          else if (e.key === 'Home') next = 0
          else if (e.key === 'End') next = values.length - 1
          else return
          e.preventDefault()
          e.stopPropagation()
          setHover(next)
          onSelect(next)
        }}
        tabIndex={onSelect ? 0 : undefined}
        role={onSelect ? 'slider' : 'img'}
        aria-label="Game advantage; use arrow keys to explore moves"
        aria-valuemin={onSelect ? 0 : undefined}
        aria-valuemax={onSelect ? values.length - 1 : undefined}
        aria-valuenow={onSelect ? selected : undefined}
        aria-valuetext={onSelect ? description : undefined}
      >
        <rect width={W} height={height} fill="var(--graph-black)" />
        {values.length > 1 && <path d={`M0,${height} L${line} L${W},${height} Z`} fill="var(--graph-white)" />}
        <line x1={0} x2={W} y1={height / 2} y2={height / 2} stroke="var(--graph-axis)" strokeWidth={1} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        {current !== null && <line x1={x(current)} x2={x(current)} y1={0} y2={height} stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
        {markers.map((m) => (
          <circle key={m.ply} cx={x(m.ply)} cy={Math.max(5, Math.min(height - 5, y(values[m.ply] ?? .5)))} r={4.5} fill={LABELS[m.label].color} stroke="var(--graph-axis)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={height} stroke="var(--graph-cursor)" strokeWidth={2} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      <span className="graph-axis" aria-hidden>50%</span>
      {hover !== null && <div className="graph-tooltip" role="tooltip">{description}</div>}
    </div>
  )
}
