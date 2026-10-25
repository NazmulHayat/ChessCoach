import type { ReviewPosition } from './types'

export const pct = (v: number) => `${Math.round(v * 100)}%`

/** White-POV engine score as "+1.3", "-0.4", "M3", "-M2". */
export function engineScore(p: ReviewPosition): string {
  if (p.mate !== null) return `${p.mate < 0 ? '-' : ''}M${Math.abs(p.mate)}`
  if (p.cp === null) return '0.0'
  const v = p.cp / 100
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}`
}

/** Bar fill for engine mode: Lichess's win% curve on white's eval (mate = full). */
export function engineWhiteShare(p: ReviewPosition): number {
  if (p.mate !== null) return p.mate > 0 ? 1 : 0
  const cp = Math.max(-1000, Math.min(1000, p.cp ?? 0))
  return 1 / (1 + Math.exp(-0.00368208 * cp))
}

export function timeClassLabel(tc: string): string {
  return tc ? tc[0].toUpperCase() + tc.slice(1) : ''
}

export function shortDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function initials(name: string): string {
  const clean = name.replace(/[^A-Za-z0-9]/g, '')
  return (clean.slice(0, 2) || '?').toUpperCase()
}
