import { useRef, useState } from 'react'
import { recentGames } from '../lib/recent'
import { SAMPLE_PGN } from '../lib/sample'
import { fetchGames } from '../api'
import { shortDate, timeClassLabel } from '../format'
import type { GameListItem } from '../types'

type Tab = 'chesscom' | 'lichess' | 'pgn'

const TAB_NAMES: Record<Tab, string> = { chesscom: 'Chess.com', lichess: 'Lichess', pgn: 'Paste PGN' }

function remembered(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: nothing to remember */
  }
}

export function ImportPanel({ onAnalyze }: { onAnalyze: (pgn: string, you?: 'white' | 'black') => void }) {
  const [tab, setTab] = useState<Tab>(() => {
    const saved = remembered('cc.tab')
    return saved === 'lichess' || saved === 'pgn' ? saved : 'chesscom'
  })
  const [user, setUser] = useState(() => remembered(`cc.user.${tab}`))
  const [games, setGames] = useState<GameListItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pgn, setPgn] = useState('')
  const [recent] = useState(recentGames)
  const request = useRef(0)

  function switchTab(t: Tab) {
    request.current++
    setLoading(false)
    setTab(t)
    remember('cc.tab', t)
    setUser(remembered(`cc.user.${t}`))
    setGames(null)
    setError(null)
  }

  async function find(e: React.FormEvent) {
    e.preventDefault()
    if (tab === 'pgn' || !user.trim()) return
    const id = ++request.current
    setLoading(true)
    setError(null)
    setGames(null)
    try {
      const list = await fetchGames(tab, user)
      if (id !== request.current) return
      setGames(list)
      remember(`cc.user.${tab}`, user.trim())
    } catch (err) {
      if (id !== request.current) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (id === request.current) setLoading(false)
    }
  }

  const me = user.trim().toLowerCase()

  return (
    <div className="panel-body">
      <div className="tabs" role="group" aria-label="Import source">
        {(Object.keys(TAB_NAMES) as Tab[]).map((t) => (
          <button key={t} type="button" aria-pressed={tab === t} className={`tab ${tab === t ? 'on' : ''}`} onClick={() => switchTab(t)}>
            {TAB_NAMES[t]}
          </button>
        ))}
      </div>

      {tab === 'pgn' ? (
        <form
          className="import-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (pgn.trim()) onAnalyze(pgn)
          }}
        >
          <textarea className="field pgn-field" value={pgn} onChange={(e) => setPgn(e.target.value)} placeholder={'[Event "Live Chess"]\n[White "you"] …\n\n1. e4 e5 2. Nf3 …'} aria-label="PGN" />
          <button type="submit" className="btn btn-primary btn-block" disabled={!pgn.trim()}>
            Analyze game
          </button>
        </form>
      ) : (
        <>
          <form className="search-row" onSubmit={find}>
            <input className="field" value={user} onChange={(e) => setUser(e.target.value)} placeholder={`${TAB_NAMES[tab]} username`} aria-label={`${TAB_NAMES[tab]} username`} autoComplete="off" spellCheck={false} />
            <button type="submit" className="btn btn-primary" disabled={loading || !user.trim()}>
              {loading ? 'Loading…' : 'Find games'}
            </button>
          </form>
          {error && <div className="error">{error}</div>}
          {loading && (
            <div className="game-list" aria-hidden>
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="game-item sk-item">
                  <span className="sk sk-dot" />
                  <span className="game-main"><span className="sk sk-text" /><span className="sk sk-text short" /></span>
                  <span className="sk sk-date" />
                </div>
              ))}
            </div>
          )}
          {games && games.length === 0 && <div className="muted pad">No recent standard games found.</div>}
          {games && games.length > 0 && (
            <div className="game-list">
              {games.map((g) => {
                const meWhite = g.white.toLowerCase() === me
                const opp = meWhite ? g.black : g.white
                const oppElo = meWhite ? g.black_elo : g.white_elo
                return (
                  <button type="button" key={g.id} className="game-item" onClick={() => onAnalyze(g.pgn, meWhite ? 'white' : 'black')}>
                    <span className={`result-pill ${g.user_result}`} aria-label={g.user_result}>{g.user_result === 'win' ? 'W' : g.user_result === 'loss' ? 'L' : 'D'}</span>
                    <span className="game-main">
                      <span className="game-opp">
                        vs {opp} {oppElo ? <span className="muted">({oppElo})</span> : null}
                      </span>
                      <span className="game-meta">
                        <svg className="time-icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" /><path d="M8 4v4l3 2" fill="none" stroke="currentColor" /></svg> {timeClassLabel(g.time_class)} · {g.time_control} · {meWhite ? 'White' : 'Black'}
                      </span>
                    </span>
                    <span className="game-date">{shortDate(g.end_time)}</span>
                  </button>
                )
              })}
            </div>
          )}
          {!games && !error && !loading && <p className="muted pad">Enter a username to list recent games, then pick one to review.</p>}
        </>
      )}
      <div className="sample-game">
        <button type="button" className="btn btn-secondary btn-block" onClick={() => onAnalyze(SAMPLE_PGN, 'white')}>Try a sample game</button>
        <p className="muted">A queen sacrifice. A seven-move lesson.</p>
      </div>
      {recent.length > 0 && (
        <section className="recent-games" aria-label="Recently reviewed">
          <h2>Recently reviewed</h2>
          {recent.map((g) => (
            <button type="button" className="recent-game" key={g.pgn} onClick={() => onAnalyze(g.pgn, g.side)}>
              <span><strong>{g.white} vs {g.black}</strong><small>Reviewed {shortDate(g.date)}</small></span>
              <span className="recent-result">{g.result}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  )
}
