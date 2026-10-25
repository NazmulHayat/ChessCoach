import { LABELS } from '../labels'
import type { Label } from '../types'

export function LabelIcon({ label, size = 16 }: { label: Label; size?: number }) {
  const m = LABELS[label]
  return (
    <span
      className="label-icon"
      style={{ background: m.color, width: size, height: size, fontSize: Math.round(size * 0.55) }}
      title={m.name}
      aria-label={m.name}
    >
      {m.glyph}
    </span>
  )
}
