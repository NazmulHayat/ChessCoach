import { useRef } from 'react'
import { LABELS } from '../labels'
import type { Label } from '../types'

interface Props {
  values: number[] // white's share per ply, 0..1 (index 0 = start position)
  current: number | null
  markers: { ply: number; label: Label }[]
  onSelect?: (ply: number) => void
  height?: number
}

const W = 600

export function Graph({ values, current, markers, onSelect, height = 84 }: Props) {
  const ref = useRef<SVGSVGElement>(null)
  const n = Math.max(values.length, 2)
  const x = (i: number) => (i / (n - 1)) * W
  const y = (v: number) => height - v * height
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' L')

  function pick(e: React.MouseEvent<SVGSVGElement>) {
    if (!onSelect || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const ply = Math.round(((e.clientX - r.left) / r.width) * (n - 1))
    onSelect(Math.max(0, Math.min(values.length - 1, ply)))
  }

  return (
    <svg
      ref={ref}
      className={`graph ${onSelect ? 'graph-clickable' : ''}`}
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      onClick={pick}
      role="img"
      aria-label="Advantage graph"
    >
      <rect width={W} height={height} fill="var(--graph-black)" />
      {values.length > 1 && <path d={`M0,${height} L${line} L${W},${height} Z`} fill="var(--graph-white)" />}
      <line x1={0} x2={W} y1={height / 2} y2={height / 2} stroke="var(--muted)" strokeWidth={1} strokeDasharray="4 4" opacity={0.6} vectorEffect="non-scaling-stroke" />
      {current !== null && (
        <line x1={x(current)} x2={x(current)} y1={0} y2={height} stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      )}
      {markers.map((m) => (
        <circle key={m.ply} cx={x(m.ply)} cy={y(values[m.ply] ?? 0.5)} r={4.5} fill={LABELS[m.label].color} stroke="var(--panel)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  )
}
