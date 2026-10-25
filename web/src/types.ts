// Shapes returned by the FastAPI server (ep_model/phase_d/review.py, server.py).

export type Label = 'best' | 'excellent' | 'good' | 'book' | 'inaccuracy' | 'mistake' | 'blunder'
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
  ep_best: number
  ep_after: number
  ep_loss: number
  ep_label: Label
  lichess_best: number
  lichess_after: number
  lichess_loss: number
  lichess_label: Label
  accuracy: number
  clock_sec: number | null
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
}

export interface Review {
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
