import { useEffect, useRef, useState } from 'react'
import { BOARD_THEMES, type Appearance, type BoardTheme, type Settings } from '../lib/settings'

export function SettingsMenu({ settings, onChange }: { settings: Settings; onChange: (patch: Partial<Settings>) => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !box.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <div className="settings" ref={box}>
      <button type="button" className="icon-btn" aria-label="Settings" aria-expanded={open} title="Settings" onClick={() => setOpen((o) => !o)}>
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
          <path
            fill="currentColor"
            d="M19.4 13a7.6 7.6 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.4 7.4 0 0 0-1.7-1L15 3h-4l-.4 2.9a7.4 7.4 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.6 7.6 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1a7.4 7.4 0 0 0 1.7 1L11 21h4l.4-2.9a7.4 7.4 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z"
            transform="translate(-1 0)"
          />
        </svg>
      </button>
      {open && (
        <div className="settings-pop" role="dialog" aria-label="Settings">
          <label className="settings-label">Appearance
            <select className="field" value={settings.appearance} onChange={(e) => onChange({ appearance: e.target.value as Appearance })}>
              <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
            </select>
          </label>
          <div className="section-title">Board</div>
          <div className="theme-grid">
            {(Object.keys(BOARD_THEMES) as BoardTheme[]).map((t) => (
              <button
                key={t}
                type="button"
                className={`theme-swatch ${settings.theme === t ? 'on' : ''}`}
                onClick={() => onChange({ theme: t })}
                aria-pressed={settings.theme === t}
              >
                <span className="swatch" style={{ background: `linear-gradient(135deg, ${BOARD_THEMES[t].light} 50%, ${BOARD_THEMES[t].dark} 50%)` }} />
                {BOARD_THEMES[t].name}
              </button>
            ))}
          </div>
          <label className="toggle-row">
            <span>Move sounds</span>
            <input type="checkbox" checked={settings.sounds} onChange={(e) => onChange({ sounds: e.target.checked })} />
            <span className="toggle" aria-hidden />
          </label>
          <label className="volume-row">
            <span>Volume <output>{settings.volume}%</output></span>
            <input type="range" min="0" max="100" step="1" value={settings.volume} disabled={!settings.sounds} onChange={(e) => onChange({ volume: Number(e.target.value) })} />
          </label>
        </div>
      )}
    </div>
  )
}
