import { describe, expect, it } from 'vitest'
import { modelFeatures } from './features'
import { loadTreeModel, type TreeModelJson } from './lgbm'
import type { ModelRow } from './types'

// node:fs without @types/node: vitest runs in Node, so a dynamic import is enough.
const fs = (await import(/* @vite-ignore */ 'node:fs' as string)) as { readFileSync(p: URL, enc: string): string }
const readJson = <T,>(rel: string): T => JSON.parse(fs.readFileSync(new URL(rel, import.meta.url), 'utf8')) as T

interface Fixture {
  rows: ModelRow[]
  features: (number | string | null)[][]
  board: number[]
  chances: number[]
}
const fx = readJson<Fixture>('./__fixtures__/model_rows.json')
const board = loadTreeModel(readJson<TreeModelJson>('../../public/data/models/board.json'))
const chances = loadTreeModel(readJson<TreeModelJson>('../../public/data/models/chances.json'))

describe('features match Python add_model_features', () => {
  it('every row, in the chances model feature order', () => {
    fx.rows.forEach((row, i) => {
      const f = modelFeatures(row)
      chances.features.forEach((name, j) => {
        const want = fx.features[i][j]
        const got = f[name]
        if (typeof want === 'number') expect(got as number).toBeCloseTo(want, 9)
        else expect(got).toBe(want)
      })
    })
  })
})

describe('tree models match LightGBM predictions', () => {
  it('board model, 400 rows', () => {
    board.predictRows(fx.rows).forEach((p, i) => expect(Math.abs(p - fx.board[i])).toBeLessThan(1e-9))
  })
  it('chances model, 400 rows', () => {
    chances.predictRows(fx.rows).forEach((p, i) => expect(Math.abs(p - fx.chances[i])).toBeLessThan(1e-9))
  })
})
