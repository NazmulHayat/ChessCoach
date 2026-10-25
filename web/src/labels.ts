import type { Label } from './types'

export interface LabelMeta {
  name: string
  article: string // "a" / "an" / "the"
  color: string
  glyph: string
}

// Order matches the summary table, best to worst.
export const LABELS: Record<Label, LabelMeta> = {
  best: { name: 'Best', article: 'the', color: 'var(--c-best)', glyph: '★' },
  excellent: { name: 'Excellent', article: 'an', color: 'var(--c-excellent)', glyph: '!' },
  good: { name: 'Good', article: 'a', color: 'var(--c-good)', glyph: '✓' },
  book: { name: 'Book', article: 'a', color: 'var(--c-book)', glyph: 'B' },
  inaccuracy: { name: 'Inaccuracy', article: 'an', color: 'var(--c-inaccuracy)', glyph: '?!' },
  mistake: { name: 'Mistake', article: 'a', color: 'var(--c-mistake)', glyph: '?' },
  blunder: { name: 'Blunder', article: 'a', color: 'var(--c-blunder)', glyph: '??' },
}

export const LABEL_ORDER: Label[] = ['best', 'excellent', 'good', 'book', 'inaccuracy', 'mistake', 'blunder']

export const BAD_LABELS: Label[] = ['inaccuracy', 'mistake', 'blunder']

/** "the best move", "an excellent move", "a mistake" … */
export function describe(label: Label): string {
  const m = LABELS[label]
  const noun = label === 'inaccuracy' || label === 'mistake' || label === 'blunder' ? m.name.toLowerCase() : `${m.name.toLowerCase()} move`
  return `${m.article} ${noun}`
}
