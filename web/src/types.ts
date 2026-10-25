// Shapes returned by the FastAPI server (ep_model/phase_d/review.py, server.py).

export type Label =
  | 'brilliant'
  | 'great'
  | 'best'
  | 'excellent'
  | 'good'
  | 'book'
  | 'inaccuracy'
  | 'mistake'
  | 'miss'
  | 'blunder'
export type Side = 'white' | 'black'

export interface ReviewMove {
  ply: number
  move_number: number
  mover: Side
  san: string
  uci: string
  from: string
  to: string
  fen_before: string
  fen_after: string
  best_uci: string | null
  best_san: string | null
  best_from: string | null
  best_to: string | null
  best_line_san: string[]
  second_san: string | null
  ep_second: number | null
  capture: boolean
  sacrifice: number
  sacrifice_piece: string | null
  base_label: Label // EP band label before Great / Miss / Brilliant
  tactic: string | null // e.g. "hangs the knight on f6", "allows mate in 2"
  ep_best: number
  ep_after: number
  ep_loss: number
  ep_label: Label
  lichess_best: number
  lichess_after: number
  lichess_loss: number
  lichess_label: Label
  accuracy: number
  phase: Phase
  clock_sec: number | null
}

export type Phase = 'opening' | 'middlegame' | 'endgame'

export interface PhaseGrade {
  accuracy: number
  grade: Label
  moves: number
}

export interface ReviewPosition {
  fen: string
  white_ep: number
  white_lichess: number
  cp: number | null
  mate: number | null
}

export interface SideSummary {
  moves: number
  avg_ep_loss: number
  accuracy: number
  labels: Partial<Record<Label, number>>
  // Game (performance) rating, in the game's own rating pool: your rating moved by how you played.
  estimated_rating: { rating: number; low: number; high: number; plays_like: number } | null
  phases: Record<Phase, PhaseGrade | null>
}

export interface Review {
  review_id?: string
  headers: Record<string, string>
  white_elo: number
  black_elo: number
  white_model_elo: number
  black_model_elo: number
  rating_pool: 'lichess' | 'chesscom'
  time_class: string
  rating_band: string
  engine_depth: number
  start_fen: string
  positions: ReviewPosition[]
  moves: ReviewMove[]
  summary: Record<Side, SideSummary>
  key_moments: number[]
}

export interface GameListItem {
  id: string
  site: 'chesscom' | 'lichess'
  url: string
  white: string
  black: string
  white_elo: number | null
  black_elo: number | null
  result: string
  user_result: 'win' | 'loss' | 'draw'
  time_control: string
  time_class: string
  end_time: string
  pgn: string
}

export type Mode = 'chances' | 'engine'

/** POST /api/retry: how a move tried in retry mode compares to the engine's best. */
export interface RetryResult {
  uci: string
  san: string
  ep_after: number
  ep_loss: number
  label: Label
  correct: boolean
  best_san: string | null
  best_line_san: string[]
}
