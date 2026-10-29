import { Chess } from 'chess.js'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { explainMove, GoneError, health, retryMove, streamReview } from './api'
import { moveCoach, retryCoach, startCoach, summaryCoach } from './coach'
import { BoardArea, type BoardInput, type PlayerInfo } from './components/BoardArea'
import { Coach } from './components/Coach'
import { Controls } from './components/Controls'
import { Graph } from './components/Graph'
import { ImportPanel } from './components/ImportPanel'
import { MoveList } from './components/MoveList'
import { SettingsMenu } from './components/SettingsMenu'
import { HelpMenu } from './components/HelpMenu'
import { InfoTip } from './components/InfoTip'
import { ReviewTour } from './components/ReviewTour'
import { MODE_HELP } from './lib/help'
import { Welcome } from './components/Welcome'
import { rememberGame } from './lib/recent'
import { Summary } from './components/Summary'
import { engineScore, engineWhiteShare, pct } from './format'
import { play, soundForSan } from './lib/sound'
import { BOARD_THEMES, useSettings } from './lib/settings'
import { BAD_LABELS, GRAPH_LABELS, RETRY_LABELS, TOP_LABELS } from './labels'
import type { Mode, RetryResult, Review, ReviewMove, Side } from './types'

type Stage = 'import' | 'analyzing' | 'summary' | 'review'

/** Retry mode at move `ply`: try → checking → correct | wrong (→ try again | solution). */
export interface RetryState {
  ply: number
  phase: 'try' | 'checking' | 'correct' | 'wrong' | 'solution'
  fen: string
  tries: number
  attempt?: { from: string; to: string }
  result?: RetryResult
  error?: string
}

const RETRY_TOLERANCE = 0.02 // same as the server: within 2% of the best move counts as finding it

/** Fallback when the server no longer has the review: only the engine's top two moves can be judged. */
function localRetryResult(move: ReviewMove, uci: string, san: string): RetryResult {
  const isBest = uci === move.best_uci
  const isSecond = san === move.second_san && move.ep_second !== null
  const ep = isBest ? move.ep_best : isSecond ? (move.ep_second as number) : NaN
  const loss = Number.isNaN(ep) ? NaN : Math.max(0, move.ep_best - ep)
  return {
    uci, san, ep_after: ep, ep_loss: loss, label: isBest ? 'best' : 'good',
    correct: isBest || (!Number.isNaN(loss) && loss <= RETRY_TOLERANCE),
    best_san: move.best_san, best_line_san: move.best_line_san,
  }
}

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
  const [mode, setMode] = useState<Mode>('engine') // engine score by default, as Chess.com shows it
  const [orientation, setOrientation] = useState<Side>('white')
  const [playing, setPlaying] = useState(false)
  const [showBest, setShowBest] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0, elapsed: 0 })
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<Record<string, string>>({})
  const [you, setYou] = useState<Side | null>(null)
  const [retry, setRetry] = useState<RetryState | null>(null)
  const [settings, updateSettings] = useSettings()
  const [explainOn, setExplainOn] = useState(false)
  const [notes, setNotes] = useState<Record<number, { text?: string; loading?: boolean; error?: string }>>({})
  const [lastPgn, setLastPgn] = useState<{ pgn: string; side?: Side } | null>(null)
  const abort = useRef<AbortController | null>(null)
  const prevPly = useRef(0)

  useEffect(() => {
    health().then((h) => {
      setExplainOn(!!h?.explain)
    })
  }, [])

  const explainPly = useCallback((reviewId: string, p: number) => {
    setNotes((n) => ({ ...n, [p]: { loading: true } }))
    explainMove(reviewId, p)
      .then((text) => setNotes((n) => ({ ...n, [p]: { text } })))
      .catch((e) => setNotes((n) => ({ ...n, [p]: { error: e instanceof Error ? e.message : String(e) } })))
  }, [])

  const total = review ? review.moves.length : 0

  const analyze = useCallback(async (pgn: string, side?: Side) => {
    abort.current?.abort()
    setPlaying(false)
    prevPly.current = 0
    setYou(side ?? null)
    setOrientation(side ?? 'white')
    setLastPgn({ pgn, side })
    setRetry(null)
    const ctrl = new AbortController()
    abort.current = ctrl
    setError(null)
    setReview(null)
    setNotes({})
    setPly(0)
    setPending(previewHeaders(pgn))
    setProgress({ done: 0, total: 0, elapsed: 0 })
    const started = Date.now()
    setStage('analyzing')
    try {
      const r = await streamReview(pgn, (done, t) => {
        if (!ctrl.signal.aborted) setProgress({ done, total: t, elapsed: (Date.now() - started) / 1000 })
      }, ctrl.signal)
      setReview(r)
      rememberGame(pgn, r.headers, side)
      setStage('summary')
    } catch (e) {
      if (ctrl.signal.aborted) return
      setError(e instanceof Error ? e.message : String(e))
      setStage('import')
    }
  }, [])

  const go = useCallback((p: number) => {
    setShowBest(false)
    setRetry(null)
    setPly((cur) => {
      const max = review ? review.moves.length : 0
      const next = Math.max(0, Math.min(max, p))
      return next === cur ? cur : next
    })
  }, [review])

  const flip = useCallback(() => setOrientation((o) => (o === 'white' ? 'black' : 'white')), [])

  // Forward navigation includes clicks and jumps; backward navigation stays quiet.
  useEffect(() => {
    const prev = prevPly.current
    prevPly.current = ply
    if (!review || !settings.sounds || stage !== 'review' || ply <= prev || ply === 0) return
    play(soundForSan(review.moves[ply - 1].san), settings.volume)
    if (ply === review.moves.length) {
      const timer = setTimeout(() => play('end', settings.volume), 180)
      return () => clearTimeout(timer)
    }
  }, [ply, review, settings.sounds, settings.volume, stage])

  // Keyboard: ← → Home End, Space play, F flip.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!review || stage === 'analyzing' || stage === 'import') return
      const target = e.target as HTMLElement
      if (e.ctrlKey || e.metaKey || e.altKey || target.closest('input, textarea, select, [contenteditable="true"], [popover], [role="dialog"]')) return
      if (e.key === ' ' && target.closest('button')) return
      if (['ArrowRight', 'ArrowLeft', 'Home', 'End', ' '].includes(e.key)) setStage('review')
      if (e.key === 'ArrowRight') go(ply + 1)
      else if (e.key === 'ArrowLeft') go(ply - 1)
      else if (e.key === 'Home') go(0)
      else if (e.key === 'End') go(total)
      else if (e.key === ' ' && !retry) setPlaying((p) => !p)
      else if (e.key.toLowerCase() === 'f') flip()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [review, stage, ply, total, go, flip, retry])

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

  const startRetry = useCallback((p: number) => {
    if (!review) return
    const m = review.moves[p - 1]
    setPlaying(false)
    setShowBest(false)
    setPly(p)
    setRetry({ ply: p, phase: 'try', fen: m.fen_before, tries: 0 })
  }, [review])

  const onRetryMove = useCallback((from: string, to: string, promotion?: string): boolean => {
    if (!review || !retry || retry.phase !== 'try') return false
    const m = review.moves[retry.ply - 1]
    const chess = new Chess(m.fen_before)
    let san: string
    try {
      san = chess.move({ from, to, promotion }).san
    } catch {
      if (settings.sounds) play('illegal', settings.volume)
      return false
    }
    const uci = from + to + (promotion ?? '')
    const tries = retry.tries + 1
    const base = { ply: retry.ply, tries, attempt: { from, to } }
    setRetry({ ...base, phase: 'checking', fen: chess.fen() })
    if (settings.sounds) play(soundForSan(san), settings.volume)
    const finish = (result: RetryResult) => {
      if (settings.sounds) play(result.correct ? 'correct' : 'wrong', settings.volume)
      setRetry((cur) => {
        if (!cur || cur.ply !== base.ply || cur.phase !== 'checking') return cur
        if (result.correct) return { ...base, phase: 'correct', fen: chess.fen(), result }
        return { ...base, phase: tries >= 2 ? 'solution' : 'wrong', fen: m.fen_before, result }
      })
    }
    if (uci === m.best_uci || !review.review_id) {
      finish(localRetryResult(m, uci, san))
    } else {
      retryMove(review.review_id, retry.ply, uci)
        .then(finish)
        .catch((e) => {
          if (e instanceof GoneError) finish(localRetryResult(m, uci, san))
          else setRetry((cur) => (cur && cur.phase === 'checking' ? { ...cur, phase: 'try', fen: m.fen_before, error: String(e.message ?? e) } : cur))
        })
    }
    return true
  }, [review, retry, settings.sounds, settings.volume])

  const me: Side = you ?? orientation
  const myMistakes = useMemo(
    () => (review ? review.moves.filter((m) => m.mover === me && RETRY_LABELS.includes(m.ep_label)).map((m) => m.ply) : []),
    [review, me],
  )
  const nextMistake = useCallback(() => {
    if (!myMistakes.length) return
    go(myMistakes.find((p) => p > ply) ?? myMistakes[0])
  }, [myMistakes, ply, go])

  const move = review && ply > 0 ? review.moves[ply - 1] : null
  const position = review ? review.positions[retry ? retry.ply - 1 : ply] : null
  const fen = retry ? retry.fen : review ? (move ? move.fen_after : review.start_fen) : START_FEN

  const graphValues = useMemo(() => {
    if (!review) return []
    return review.positions.map((p) => (mode === 'chances' ? p.white_ep : engineWhiteShare(p)))
  }, [review, mode])

  const markers = useMemo(
    () => (review ? review.moves.filter((m) => GRAPH_LABELS.includes(m.ep_label)).map((m) => ({ ply: m.ply, label: m.ep_label })) : []),
    [review],
  )

  const headers = review?.headers ?? pending
  const clockFor = (side: Side): string | null => {
    if (!review) return null
    // Most recent known clock for `side` at or before the shown position.
    for (let i = Math.min(ply - 1, review.moves.length - 1); i >= 0; i--) {
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
  let arrow = inReview && !retry && move && move.best_from && move.best_to && !TOP_LABELS.includes(move.ep_label) && bestVisible
    ? { from: move.best_from, to: move.best_to }
    : null
  if (retry && move && retry.phase === 'solution' && move.best_from && move.best_to) arrow = { from: move.best_from, to: move.best_to }

  const boardInput: BoardInput | null = inReview && retry && retry.phase === 'try' && move ? { side: move.mover, onMove: onRetryMove } : null
  let lastMove = inReview && move ? { from: move.from, to: move.to } : null
  let badge = inReview && move ? { square: move.to, label: move.ep_label } : null
  if (retry) {
    lastMove = retry.attempt && (retry.phase === 'checking' || retry.phase === 'correct') ? retry.attempt : null
    badge = retry.phase === 'correct' && retry.attempt && retry.result ? { square: retry.attempt.to, label: retry.result.label } : null
  }
  const canRetry = !!move && RETRY_LABELS.includes(move.ep_label)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width={26} height={26} />
          <span>elo101</span>
        </div>
        <div className="topbar-actions">
          {review && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setStage('import'); setPlaying(false); setRetry(null) }}>
              New game
            </button>
          )}
          <HelpMenu kind="shortcuts" />
          <SettingsMenu settings={settings} onChange={updateSettings} />
        </div>
      </header>
      <main className={`layout ${stage === 'import' || stage === 'analyzing' ? 'layout-welcome' : ''}`}>
        <section className="left">
          {stage === 'import' || stage === 'analyzing' ? <Welcome colors={BOARD_THEMES[settings.theme]} /> : <BoardArea
            fen={fen}
            orientation={orientation}
            white={whiteP}
            black={blackP}
            input={boardInput}
            inputSession={retry ? `retry-${retry.ply}` : null}
            lastMove={lastMove}
            badge={badge}
            arrow={arrow}
            whiteShare={whiteShare}
            evalText={evalText}
            onStep={inReview && !retry ? (direction) => go(ply + direction) : undefined}
            colors={BOARD_THEMES[settings.theme]}
          />}
        </section>

        <aside className="panel">
          <div className="panel-head">
            <span className="panel-title">{stage === 'import' ? 'Review a game' : 'Game Review'}</span>
            <HelpMenu kind="labels" />
            {review && stage !== 'import' && (
              <div className="evaluation-mode">
                <div className="seg" role="group" aria-label="Evaluation mode">
                  <button type="button" aria-pressed={mode === 'chances'} className={mode === 'chances' ? 'on' : ''} onClick={() => setMode('chances')} title="Expected points at these players' level">
                    Chances
                  </button>
                  <button type="button" aria-pressed={mode === 'engine'} className={mode === 'engine' ? 'on' : ''} onClick={() => setMode('engine')} title="Raw Stockfish evaluation">
                    Engine
                  </button>
                </div>
                <InfoTip label="Chances vs Engine">{MODE_HELP}</InfoTip>
              </div>
            )}
          </div>

          {stage === 'import' && (
            <>
              {error && (
                <div className="error banner" role="alert">
                  <span>{error}</span>
                  {lastPgn && (
                    <button type="button" className="link-btn" onClick={() => analyze(lastPgn.pgn, lastPgn.side)}>Try again</button>
                  )}
                </div>
              )}
              <ImportPanel onAnalyze={analyze} />
            </>
          )}

          {stage === 'analyzing' && (
            <div className="panel-body analyzing">
              <div className="spinner" aria-hidden />
              <div className="an-title">Analyzing game…</div>
              <div className="progress" role="progressbar" aria-label="Game analysis" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.total ? Math.round(progress.done / progress.total * 100) : undefined}>
                <div style={{ width: progress.total ? `${(progress.done / progress.total) * 100}%` : '4%' }} />
              </div>
              <div className="analysis-status" role="status">
                <strong>{progress.total ? `${Math.round(progress.done / progress.total * 100)}%` : 'Starting Stockfish…'}</strong>
                {progress.total > 1 && <span>Analyzing move {Math.max(1, progress.done - 1)} of {progress.total - 1}</span>}
                <span className="muted">{progress.done > 1 && progress.elapsed > 0
                  ? `About ${Math.max(1, Math.ceil((progress.total - progress.done) * progress.elapsed / progress.done / 60))} min left`
                  : 'Estimating time remaining…'}</span>
              </div>
              <button type="button" className="btn btn-ghost" onClick={() => { abort.current?.abort(); setStage('import') }}>
                Cancel
              </button>
              <div className="skeleton-block" aria-hidden>
                <div className="sk sk-graph" />
                <div className="sk-row"><div className="sk sk-acc" /><div className="sk sk-acc" /></div>
                {Array.from({ length: 5 }, (_, i) => <div key={i} className="sk sk-line" />)}
              </div>
            </div>
          )}

          {stage === 'summary' && review && (
            <Summary
              review={review}
              coach={summaryCoach(review)}
              graphValues={graphValues}
              axisLabel={mode === 'chances' ? '50%' : '0.0'}
              onStart={() => { setStage('review'); go(Math.max(ply, 1)) }}
              onJump={(p) => { setStage('review'); go(p) }}
            />
          )}

          {inReview && (
            <div className="panel-body review">
              {retry && move ? (
                <Coach text={retryCoach(move, retry)} label={retry.phase === 'correct' ? retry.result?.label : undefined}>
                  {retry.phase === 'try' && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRetry(null)}>Cancel</button>
                  )}
                  {retry.phase === 'wrong' && (
                    <>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => setRetry({ ...retry, phase: 'try', attempt: undefined, error: undefined })}>Try again</button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRetry({ ...retry, phase: 'solution' })}>Show solution</button>
                    </>
                  )}
                  {(retry.phase === 'correct' || retry.phase === 'solution') && (
                    <>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => go(ply + 1)}>Continue</button>
                      {myMistakes.some((p) => p !== ply) && (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={nextMistake}>Next mistake</button>
                      )}
                    </>
                  )}
                </Coach>
              ) : (
                <Coach text={move ? moveCoach(review, move) : startCoach(review)} label={move?.ep_label} ai={move ? notes[move.ply] ?? null : null}>
                  <button type="button" data-tour="retry" className="btn btn-primary btn-sm" disabled={!canRetry} onClick={() => startRetry(ply)}>Retry</button>
                  {myMistakes.length > 0 && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={nextMistake} title={`Your mistakes as ${me}`}>
                      Next mistake
                    </button>
                  )}
                  {explainOn && review.review_id && move && move.ep_label !== 'book' && !notes[move.ply] && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => explainPly(review.review_id as string, move.ply)} title="Ask Claude to explain this move">
                      Explain
                    </button>
                  )}
                </Coach>
              )}
              <div className="graph-wrap" data-tour="graph">
                <Graph values={graphValues} moves={review.moves} chances={review.positions.map((p) => p.white_ep)} current={ply} markers={markers} onSelect={go} axisLabel={mode === 'chances' ? '50%' : '0.0'} />
              </div>
              <MoveList moves={review.moves} current={ply} onSelect={go} />
              <Controls
                onFirst={() => go(0)}
                onPrev={() => go(ply - 1)}
                onNext={() => go(ply + 1)}
                onLast={() => go(total)}
                onTogglePlay={() => setPlaying((p) => !p)}
                onFlip={flip}
                playing={playing}
                atStart={ply === 0}
                atEnd={ply === total}
                retrying={!!retry}
              />
              <div className="panel-actions two">
                <button type="button" className="btn btn-ghost" onClick={() => { setRetry(null); setPlaying(false); setStage('summary') }}>
                  Summary
                </button>
                <button
                  type="button"
                  className={`btn ${arrow ? 'btn-secondary' : 'btn-primary'}`}
                  disabled={!move || !!retry || TOP_LABELS.includes(move.ep_label)}
                  onClick={() => setShowBest((s) => !s)}
                >
                  {arrow ? 'Hide best' : 'Show best'}
                </button>
              </div>
            </div>
          )}
        </aside>
      </main>
      {inReview && !retry && <ReviewTour onShowRetry={() => {
        const first = review.moves.find((m) => RETRY_LABELS.includes(m.ep_label))
        if (first) go(first.ply)
      }} />}
    </div>
  )
}
