// Model features for one row: a port of add_model_features / cp_or_mate_proxy (ep_model/training/prepare.py).
import type { ModelRow } from './types'

/** Mate-in-N (signed, side to move) on a centipawn-like scale. */
export function mateToPseudoCp(mate: number): number {
  return (mate > 0 ? 1 : -1) * (10000 - Math.abs(Math.trunc(mate)) * 100)
}

/** Single numeric score: cp when present, else pseudo-cp from mate, else 0. */
export function cpOrMateProxy(cp: number | null | undefined, mate: number | null | undefined): number {
  if (mate != null && !Number.isNaN(mate)) return mateToPseudoCp(mate)
  if (cp != null && !Number.isNaN(cp)) return cp
  return 0
}

const num = (v: unknown): number => (typeof v === 'number' ? v : v == null ? NaN : Number(v))

/**
 * Derived feature values by name (numbers, or strings for categoricals). Clocks are relative to the side to
 * move; before a side's first clock comment (ply <= 2) a missing clock is the initial time, otherwise -1.
 */
export function modelFeatures(row: ModelRow): Record<string, number | string | null> {
  const whiteToMove = row.side_to_move === 'w'
  const init = num(row.initial_time_sec)
  const early = num(row.ply) <= 2
  const clock = (v: unknown) => {
    const x = num(v)
    return Number.isNaN(x) && early ? init : x
  }
  const cw = clock(row.clk_white_sec)
  const cb = clock(row.clk_black_sec)
  const stm = whiteToMove ? cw : cb
  const opp = whiteToMove ? cb : cw
  const frac = init > 0 ? stm / init : NaN
  const orMinus1 = (x: number) => (Number.isNaN(x) ? -1 : x)
  return {
    cp_stm_proxy: cpOrMateProxy(row.eval_cp_stm, row.mate_stm),
    cp_white_proxy: cpOrMateProxy(row.eval_cp_white, row.mate_white),
    elo_to_move: num(row.elo_to_move),
    elo_opponent: num(row.elo_opponent),
    elo_diff: num(row.elo_diff),
    ply: num(row.ply),
    move_number: num(row.move_number),
    side_w: whiteToMove ? 1 : 0,
    initial_time_sec: Number.isNaN(init) ? -1 : Math.trunc(init),
    increment_sec: row.increment_sec == null ? -1 : Math.trunc(num(row.increment_sec)),
    clk_stm_sec: orMinus1(stm),
    clk_opp_sec: orMinus1(opp),
    clk_stm_frac: orMinus1(frac),
    phase: row.phase ?? null,
    time_class: row.time_class ?? null,
    rating_band: row.rating_band ?? null,
    opening_eco: row.opening_eco ?? '?',
  }
}
