import type { Label } from './types'

export interface LabelMeta {
  name: string
  article: string // "a" / "an" / "the"
  color: string
  glyph: string
}

// Order matches the summary table, best to worst.
export const LABELS: Record<Label, LabelMeta> = {
  brilliant: { name: 'Brilliant', article: 'a', color: 'var(--c-brilliant)', glyph: '!!' },
  great: { name: 'Great', article: 'a', color: 'var(--c-great)', glyph: '!' },
  best: { name: 'Best', article: 'the', color: 'var(--c-best)', glyph: '★' },
  excellent: { name: 'Excellent', article: 'an', color: 'var(--c-excellent)', glyph: '+' },
  good: { name: 'Good', article: 'a', color: 'var(--c-good)', glyph: '✓' },
  book: { name: 'Book', article: 'a', color: 'var(--c-book)', glyph: 'B' },
  inaccuracy: { name: 'Inaccuracy', article: 'an', color: 'var(--c-inaccuracy)', glyph: '?!' },
  mistake: { name: 'Mistake', article: 'a', color: 'var(--c-mistake)', glyph: '?' },
  miss: { name: 'Miss', article: 'a', color: 'var(--c-miss)', glyph: '✕' },
  blunder: { name: 'Blunder', article: 'a', color: 'var(--c-blunder)', glyph: '??' },
}

export const LABEL_ORDER: Label[] = ['brilliant', 'great', 'best', 'excellent', 'good', 'book', 'inaccuracy', 'mistake', 'miss', 'blunder']

export const BAD_LABELS: Label[] = ['inaccuracy', 'mistake', 'miss', 'blunder']

/** Labels worth retrying: you lost real chances here. */
export const RETRY_LABELS: Label[] = ['mistake', 'miss', 'blunder']

/** Marked on the advantage graph. */
export const GRAPH_LABELS: Label[] = ['brilliant', 'great', 'inaccuracy', 'mistake', 'miss', 'blunder']

/** Good moves that don't get a best-move arrow. */
export const TOP_LABELS: Label[] = ['brilliant', 'great', 'best', 'book']

/** "the best move", "an excellent move", "a mistake" … */
export function describe(label: Label): string {
  const m = LABELS[label]
  const noun = ['inaccuracy', 'mistake', 'miss', 'blunder'].includes(label) ? m.name.toLowerCase() : `${m.name.toLowerCase()} move`
  return `${m.article} ${noun}`
}
