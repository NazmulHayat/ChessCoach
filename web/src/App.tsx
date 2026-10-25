import { Chess } from 'chess.js'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { streamReview } from './api'
import { moveCoach, startCoach, summaryCoach } from './coach'
import { BoardArea, type PlayerInfo } from './components/BoardArea'
import { Coach } from './components/Coach'
import { Controls } from './components/Controls'
import { Graph } from './components/Graph'
import { ImportPanel } from './components/ImportPanel'
import { MoveList } from './components/MoveList'
import { Summary } from './components/Summary'
import { engineScore, engineWhiteShare, pct } from './format'
import { BAD_LABELS } from './labels'
import type { Mode, Review, Side } from './types'

type Stage = 'import' | 'analyzing' | 'summary' | 'review'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

function formatClock(sec: number | null | undefined): string | null {
  if (sec === null || sec === undefined) return null
  const s = Math.max(0, Math.round(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`
}

/** Headers from a PGN without analysing it, so the board can show players while the engine runs. */
function previewHeaders(pgn: string): Record<string, string> {
  try {
    const c = new Chess()
    c.loadPgn(pgn)
    return c.getHeaders() as Record<string, string>
  } catch {
    return {}
  }
}

export default function App() {
  const [stage, setStage] = useState<Stage>('import')
  const [review, setReview] = useState<Review | null>(null)
  const [ply, setPly] = useState(0)
  const [mode, setMode] = useState<Mode>('chances')
  const [orientation, setOrientation] = useState<Side>('white')
  const [playing, setPlaying] = useState(false)
  const [showBest, setShowBest] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 })
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<Record<string, string>>({})
  const abort = useRef<AbortController | null>(null)

  const total = review ? review.moves.length : 0

  const analyze = useCallback(async (pgn: string) => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    setError(null)
    setReview(null)
    setPly(0)
    setPending(previewHeaders(pgn))
    setProgress({ done: 0, total: 0 })
    setStage('analyzing')
    try {
      const r = await streamReview(pgn, (done, t) => setProgress({ done, total: t }), ctrl.signal)
      setReview(r)
      setStage('summary')
    } catch (e) {
      if (ctrl.signal.aborted) return
      setError(e instanceof Error ? e.message : String(e))
      setStage('import')
    }
  }, [])

  const go = useCallback((p: number) => {
    setShowBest(false)
    setPly((cur) => {
      const max = review ? review.moves.length : 0
      const next = Math.max(0, Math.min(max, p))
      return next === cur ? cur : next
    })
  }, [review])

  // Keyboard: ← → Home End, Space play, F flip.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!review || stage === 'analyzing' || stage === 'import') return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowRight') {
        if (stage === 'summary') setStage('review')
        go(ply + 1)
      } else if (e.key === 'ArrowLeft') go(ply - 1)
      else if (e.key === 'Home') go(0)
      else if (e.key === 'End') go(total)
      else if (e.key === ' ') setPlaying((p) => !p)
      else if (e.key.toLowerCase() === 'f') setOrientation((o) => (o === 'white' ? 'black' : 'white'))
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [review, stage, ply, total, go])

  // Autoplay.
  useEffect(() => {
    if (!playing) return
    if (ply >= total) {
      setPlaying(false)
      return
    }
    const t = setTimeout(() => go(ply + 1), 900)
    return () => clearTimeout(t)
  }, [playing, ply, total, go])

  const move = review && ply > 0 ? review.moves[ply - 1] : null
  const position = review ? review.positions[ply] : null
  const fen = review ? (move ? move.fen_after : review.start_fen) : START_FEN

  const graphValues = useMemo(() => {
    if (!review) return []
    return review.positions.map((p) => (mode === 'chances' ? p.white_ep : engineWhiteShare(p)))
  }, [review, mode])

  const markers = useMemo(
    () => (review ? review.moves.filter((m) => m.ep_label === 'mistake' || m.ep_label === 'blunder' || m.ep_label === 'inaccuracy').map((m) => ({ ply: m.ply, label: m.ep_label })) : []),
    [review],
  )

  const headers = review?.headers ?? pending
  const clockFor = (side: Side): string | null => {
    if (!review) return null
    // Most recent known clock for `side` at or before the shown position.
    for (let i = Math.min(ply, review.moves.length - 1); i >= 0; i--) {
      const m = review.moves[i]
      if (m.mover === side && m.clock_sec !== null) return formatClock(m.clock_sec)
    }
    const initial = Number((review.headers.TimeControl || '').split('+')[0])
    return Number.isFinite(initial) && initial > 0 ? formatClock(initial) : null
  }
  const whiteP: PlayerInfo = {
    name: headers.White || 'White',
    elo: review ? review.white_elo : Number(headers.WhiteElo) || null,
    side: 'white',
    clock: clockFor('white'),
  }
  const blackP: PlayerInfo = {
    name: headers.Black || 'Black',
    elo: review ? review.black_elo : Number(headers.BlackElo) || null,
    side: 'black',
    clock: clockFor('black'),
  }

  let whiteShare = 0.5
  let evalText = mode === 'chances' ? '50%' : '0.0'
  if (position) {
    if (mode === 'chances') {
      whiteShare = position.white_ep
      evalText = pct(Math.max(whiteShare, 1 - whiteShare))
    } else {
      whiteShare = engineWhiteShare(position)
      evalText = engineScore(position).replace('+', '')
    }
  }

  const inReview = stage === 'review' && review
  // Mistakes show the best move automatically (like Chess.com); the button toggles it either way.
  const autoBest = move ? BAD_LABELS.includes(move.ep_label) : false
  const bestVisible = autoBest !== showBest
  const arrow = inReview && move && move.best_from && move.best_to && move.ep_label !== 'best' && move.ep_label !== 'book' && bestVisible
    ? { from: move.best_from, to: move.best_to }
    : null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>ChessCoach</span>
        </div>
        {review && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setStage('import'); setPlaying(false) }}>
            New game
          </button>
        )}
      </header>

      <main className="layout">
        <section className="left">
          <BoardArea
            fen={fen}
            orientation={orientation}
            white={whiteP}
            black={blackP}
            lastMove={inReview && move ? { from: move.from, to: move.to } : null}
            badge={inReview && move ? { square: move.to, label: move.ep_label } : null}
            arrow={arrow}
            whiteShare={whiteShare}
            evalText={evalText}
          />
        </section>

        <aside className="panel">
          <div className="panel-head">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden className="head-icon">
              <path d="M12 2l2.9 6.9 7.1.6-5.4 4.7 1.7 7.1L12 17.6 5.7 21.3l1.7-7.1L2 9.5l7.1-.6z" fill="currentColor" />
            </svg>
            <span>{stage === 'import' ? 'Review a game' : 'Game Review'}</span>
            {review && stage !== 'import' && (
              <div className="seg" role="group" aria-label="Evaluation mode">
                <button type="button" className={mode === 'chances' ? 'on' : ''} onClick={() => setMode('chances')} title="Expected points at these players' level">
                  Chances
                </button>
                <button type="button" className={mode === 'engine' ? 'on' : ''} onClick={() => setMode('engine')} title="Raw Stockfish evaluation">
                  Engine
                </button>
              </div>
            )}
          </div>

          {stage === 'import' && (
            <>
              {error && <div className="error banner">{error}</div>}
              <ImportPanel onAnalyze={analyze} />
            </>
          )}

          {stage === 'analyzing' && (
            <div className="panel-body analyzing">
              <div className="spinner" aria-hidden />
              <div className="an-title">Analyzing game…</div>
              <div className="progress">
                <div style={{ width: progress.total ? `${(progress.done / progress.total) * 100}%` : '4%' }} />
              </div>
              <div className="muted">
                {progress.total ? `Position ${progress.done} of ${progress.total}` : 'Starting Stockfish…'}
              </div>
              <button type="button" className="btn btn-ghost" onClick={() => { abort.current?.abort(); setStage('import') }}>
                Cancel
              </button>
            </div>
          )}

          {stage === 'summary' && review && (
            <Summary
              review={review}
              coach={summaryCoach(review)}
              graphValues={graphValues}
              onStart={() => { setStage('review'); go(Math.max(ply, 1)) }}
              onJump={(p) => { setStage('review'); go(p) }}
            />
          )}

          {inReview && (
            <div className="panel-body review">
              <Coach text={move ? moveCoach(review, move) : startCoach(review)} label={move?.ep_label} />
              <div className="graph-wrap">
                <Graph values={graphValues} current={ply} markers={markers} onSelect={go} />
              </div>
              <MoveList moves={review.moves} current={ply} onSelect={go} />
              <Controls
                onFirst={() => go(0)}
                onPrev={() => go(ply - 1)}
                onNext={() => go(ply + 1)}
                onLast={() => go(total)}
                onTogglePlay={() => setPlaying((p) => !p)}
                playing={playing}
              />
              <div className="panel-actions two">
                <button type="button" className="btn btn-ghost" onClick={() => setStage('summary')}>
                  Summary
                </button>
                <button
                  type="button"
                  className={`btn ${arrow ? 'btn-secondary' : 'btn-primary'}`}
                  disabled={!move || move.ep_label === 'best' || move.ep_label === 'book'}
                  onClick={() => setShowBest((s) => !s)}
                >
                  {arrow ? 'Hide best' : 'Show best'}
                </button>
              </div>
            </div>
          )}
        </aside>
      </main>
    </div>
  )
}
