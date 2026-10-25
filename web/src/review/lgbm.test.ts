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

describe('rating model (identity objective) matches LightGBM', () => {
  // 12 random feature vectors and Python's booster.predict on them (ep_model/phase_d/data/rating_lgbm.txt).
  const data = {"x": [[77.37410169338212, 0.14835739785214588, 0.15903871311313933, 0.28273508513311507, 0.4439391448439584, 4.329114992663918, 26.104705455253264, 67.93735926268633, 0.9433567169983137, 0.0], [94.05402950503736, 0.022641192930628874, 0.09381380955643276, 0.07397184978594909, 0.32625651554155827, 3.5626706134418216, 11.802770630011983, 53.00378802783089, 0.2794823660111103, 3.0], [49.57625274148229, 0.15942939828624092, 0.027753483679780633, 0.18523575613983498, 0.07601953953016183, 2.303904696845576, 784.2642702518539, 52.567382949707074, 0.21548116922473226, 1.0], [92.34446592620812, 0.0578610335493853, 0.1922955977900167, 0.16176704066124317, 0.4066982863503554, 2.7505149319743443, 846.8784009791991, 81.4385164664145, 0.9665643123171954, 3.0], [57.927333871232065, 0.07223798694447683, 0.03319121142594912, 0.043710572862204755, 0.039083828025405755, 2.9629900216928173, 542.7989976668889, 40.202987162461405, 0.6779342495476912, 2.0], [43.96134703306463, 0.07107027145999383, 0.06121285182348666, 0.208925942292347, 0.1108639440590965, 3.3395843695869454, 158.50807243064662, 55.37091015656272, 0.939011804929864, 2.0], [90.69285336328778, 0.003613507075706024, 0.15754766079608684, 0.10985534275255816, 0.3471112974341247, 2.3199724510029625, 42.05440682904737, 50.85516927706287, 0.9551798995911663, 1.0], [47.1412334244265, 0.049217358126722746, 0.16389863333410595, 0.1386616081246327, 0.3074976072674685, 4.263964402335465, 225.80456061693064, 67.77098556222894, 0.5897633712619398, 2.0], [91.5816591512548, 0.007326315988565502, 0.18916003700843675, 0.027353959251530578, 0.20444432130253334, 3.643820583803773, 826.278466979981, 60.39757159755068, 0.9241976194277907, 0.0], [58.74702216057442, 0.06335999713267544, 0.035495555100997715, 0.023458869666172045, 0.08932082677394912, 3.816184092167525, 897.0541330830334, 49.691767865476976, 0.04855216354845626, 3.0], [41.909588979484106, 0.14811169891649517, 0.06876658026322054, 0.07506265742107875, 0.39057986328791355, 2.620383841712444, 881.1455586885095, 78.29946236285025, 0.8016644306001379, 2.0], [90.30575687008793, 0.026114365430624, 0.1463328846753353, 0.2849395687865696, 0.37823957605583675, 4.033621009516786, 95.96754872753301, 66.07331143602623, 0.14924534454025784, 3.0]], "y": [1866.147998918264, 1496.9895097229123, 754.8988828290732, 1118.5559063762541, 742.1124176084999, 1055.94956554947, 1228.4950322066063, 1060.544250447704, 1376.2587836870944, 950.2080086272607, 721.915115461603, 1580.1789832858192]}
  it('raw regression output', () => {
    const rating = loadTreeModel(readJson<TreeModelJson>('../../public/data/models/rating.json'))
    rating.predictVectors(data.x).forEach((p, i) => expect(Math.abs(p - data.y[i])).toBeLessThan(1e-6))
  })
})
