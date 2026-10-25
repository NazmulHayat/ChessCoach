import { useState } from 'react'
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

export function ImportPanel({ onAnalyze }: { onAnalyze: (pgn: string) => void }) {
  const [tab, setTab] = useState<Tab>(() => (remembered('cc.tab') as Tab) || 'chesscom')
  const [user, setUser] = useState(() => remembered(`cc.user.${tab}`))
  const [games, setGames] = useState<GameListItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pgn, setPgn] = useState('')

  function switchTab(t: Tab) {
    setTab(t)
    remember('cc.tab', t)
    setUser(remembered(`cc.user.${t}`))
    setGames(null)
    setError(null)
  }

  async function find(e: React.FormEvent) {
    e.preventDefault()
    if (tab === 'pgn' || !user.trim()) return
    setLoading(true)
    setError(null)
    setGames(null)
    try {
      const list = await fetchGames(tab, user)
      setGames(list)
      remember(`cc.user.${tab}`, user.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const me = user.trim().toLowerCase()

  return (
    <div className="panel-body">
      <div className="tabs" role="tablist">
        {(Object.keys(TAB_NAMES) as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className={`tab ${tab === t ? 'on' : ''}`} onClick={() => switchTab(t)}>
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
          {games && games.length === 0 && <div className="muted pad">No recent standard games found.</div>}
          {games && games.length > 0 && (
            <div className="game-list">
              {games.map((g) => {
                const meWhite = g.white.toLowerCase() === me
                const opp = meWhite ? g.black : g.white
                const oppElo = meWhite ? g.black_elo : g.white_elo
                return (
                  <button type="button" key={g.id} className="game-item" onClick={() => onAnalyze(g.pgn)}>
                    <span className={`result-dot ${g.user_result}`} aria-label={g.user_result} />
                    <span className="game-main">
                      <span className="game-opp">
                        vs {opp} {oppElo ? <span className="muted">({oppElo})</span> : null}
                      </span>
                      <span className="game-meta">
                        {timeClassLabel(g.time_class)} · {g.time_control} · {meWhite ? 'White' : 'Black'}
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
    </div>
  )
}
