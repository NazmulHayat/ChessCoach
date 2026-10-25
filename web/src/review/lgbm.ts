// LightGBM tree models exported by ep_model/scripts/export_web.py, evaluated with LightGBM's own decision rules.
import { modelFeatures } from './features'
import type { ModelRow, TreeModel } from './types'

interface FlatTree {
  f: number[] // split feature index
  t: (number | number[])[] // threshold, or category codes going left
  c: number[] // 1 = categorical split
  dl: number[] // default left
  m: number[] // missing type: 0 none, 1 zero, 2 NaN
  l: number[] // child: >= 0 node, < 0 leaf ~index
  r: number[]
  v: number[] // leaf values
}

export interface TreeModelJson {
  objective: 'sigmoid' | 'identity'
  features: string[]
  categorical: Record<string, string[]>
  trees: FlatTree[]
  [extra: string]: unknown
}

const ZERO = 1e-35
const MISSING_ZERO = 1
const MISSING_NAN = 2

function goesLeft(tree: FlatTree, node: number, value: number | null): boolean {
  let v = value == null ? NaN : value
  const missing = tree.m[node]
  if (tree.c[node]) {
    // CategoricalDecision
    if (Number.isNaN(v)) {
      if (missing === MISSING_NAN) return false
      v = 0
    }
    const iv = Math.trunc(v)
    if (iv < 0) return false
    return (tree.t[node] as number[]).includes(iv)
  }
  // NumericalDecision
  if (Number.isNaN(v) && missing !== MISSING_NAN) v = 0
  if ((missing === MISSING_ZERO && Math.abs(v) <= ZERO) || (missing === MISSING_NAN && Number.isNaN(v))) {
    return tree.dl[node] === 1
  }
  return v <= (tree.t[node] as number)
}

function treeValue(tree: FlatTree, x: (number | null)[]): number {
  if (tree.f.length === 0) return tree.v[0]
  let node = 0
  for (;;) {
    const next = goesLeft(tree, node, x[tree.f[node]]) ? tree.l[node] : tree.r[node]
    if (next < 0) return tree.v[~next]
    node = next
  }
}

/** A loaded model; categorical values encode as their index in the training category list. */
export interface LoadedTreeModel extends TreeModel {
  categorical: Record<string, string[]>
  categoryCodes: Record<string, Map<string, number>>
}

export function loadTreeModel(json: TreeModelJson): LoadedTreeModel {
  const categoryCodes: Record<string, Map<string, number>> = {}
  for (const [name, values] of Object.entries(json.categorical ?? {})) {
    categoryCodes[name] = new Map(values.map((v, i) => [v, i]))
  }
  const sigmoid = json.objective === 'sigmoid'

  const predictVectors = (xs: (number | null)[][]): number[] =>
    xs.map((x) => {
      let sum = 0
      for (const t of json.trees) sum += treeValue(t, x)
      if (!sigmoid) return sum
      return Math.min(1, Math.max(0, 1 / (1 + Math.exp(-sum))))
    })

  const model: LoadedTreeModel = {
    features: json.features,
    categorical: json.categorical ?? {},
    categoryCodes,
    predictVectors,
    predictRows: (rows: ModelRow[]) => predictVectors(rows.map((r) => rowToVector(r, model))),
  }
  return model
}

/** Feature vector in the model's feature order (categoricals as training category codes). */
export function rowToVector(row: ModelRow, model: LoadedTreeModel): (number | null)[] {
  return valuesToVector(modelFeatures(row), model)
}

/** Vector from already-derived feature values (numbers, or strings for categorical features); unknown or missing -> NaN. */
export function valuesToVector(values: Record<string, number | string | null>, model: LoadedTreeModel): (number | null)[] {
  return model.features.map((name) => {
    const v = values[name]
    const codes = model.categoryCodes[name]
    if (codes) return typeof v === 'string' && codes.has(v) ? codes.get(v)! : NaN
    if (v == null) return NaN
    return typeof v === 'number' ? v : Number(v)
  })
}

export async function fetchTreeModel(url: string): Promise<LoadedTreeModel> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Could not load model ${url} (HTTP ${r.status})`)
  return loadTreeModel((await r.json()) as TreeModelJson)
}
