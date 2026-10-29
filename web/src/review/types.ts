// Shared shapes for the in-browser review (a TypeScript port of ep_model/review). Field names match the
// Python dicts, so fixtures exported from Python can be compared directly.

/** One engine result for a FEN (Python: engine_pool.analysis_fields). Scores are centipawns / mate-in-N. */
export interface EngineFields {
  eval_cp_white: number | null
  mate_white: number | null
  eval_cp_stm: number | null
  mate_stm: number | null
  eval_depth: number | null
  best_uci: string | null
  pv_uci: string[] // first moves of the top line (up to 8)
  second_uci: string | null
  second_cp_stm: number | null
  second_mate_stm: number | null
}

export type ProgressFn = (done: number, total: number) => void

/** fens -> engine fields, in input order (Python: EnginePool.analyse). */
export type AnalyseFn = (fens: string[], progress?: ProgressFn) => Promise<EngineFields[]>

/** A model input row (Python: Phase B-shaped dict). Missing values are null. */
export interface ModelRow {
  ply: number
  move_number: number
  side_to_move: 'w' | 'b'
  elo_to_move: number
  elo_opponent: number
  elo_diff: number
  white_elo?: number
  black_elo?: number
  time_class: string
  initial_time_sec: number | null
  increment_sec: number | null
  clk_white_sec: number | null
  clk_black_sec: number | null
  phase: string
  opening_eco: string | null
  rating_band: string
  eval_cp_stm: number | null
  mate_stm: number | null
  eval_cp_white: number | null
  mate_white: number | null
  [extra: string]: unknown
}

/** A loaded tree model: predict expected score (sigmoid models) or the raw value (identity). */
export interface TreeModel {
  features: string[]
  predictRows(rows: ModelRow[]): number[]
  predictVectors(x: (number | null)[][]): number[]
}
