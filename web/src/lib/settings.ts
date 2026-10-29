// Per-browser preferences (board theme, sounds), kept in localStorage when available.
import { useCallback, useEffect, useState } from 'react'

export type Appearance = 'system' | 'light' | 'dark'
export type BoardTheme = 'club' | 'green' | 'walnut' | 'slate' | 'ice'

export const BOARD_THEMES: Record<BoardTheme, { name: string; light: string; dark: string }> = {
  club: { name: 'Club', light: '#ede6cf', dark: '#4a7a55' },
  green: { name: 'Green', light: '#eeeed2', dark: '#769656' },
  walnut: { name: 'Walnut', light: '#f0d9b5', dark: '#b58863' },
  slate: { name: 'Slate', light: '#dee3e6', dark: '#8ca2ad' },
  ice: { name: 'Ice', light: '#e8eef5', dark: '#7d93b2' },
}

export interface Settings {
  theme: BoardTheme
  sounds: boolean
  volume: number
  appearance: Appearance
}

const KEY = 'cc.settings'
const DEFAULTS: Settings = { theme: 'club', sounds: true, volume: 70, appearance: 'system' }

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    const s = raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
    return {
      theme: Object.prototype.hasOwnProperty.call(BOARD_THEMES, s.theme) ? s.theme : DEFAULTS.theme,
      appearance: s.appearance === 'light' || s.appearance === 'dark' ? s.appearance : 'system',
      sounds: typeof s.sounds === 'boolean' ? s.sounds : DEFAULTS.sounds,
      volume: typeof s.volume === 'number' && Number.isFinite(s.volume) ? Math.min(100, Math.max(0, s.volume)) : DEFAULTS.volume,
    }
  } catch {
    return DEFAULTS
  }
}

export function useSettings(): [Settings, (patch: Partial<Settings>) => void] {
  const [settings, setSettings] = useState<Settings>(load)
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: light)')
    const apply = () => {
      document.documentElement.dataset.theme = settings.appearance === 'system' ? (query.matches ? 'light' : 'dark') : settings.appearance
      const color = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', color)
    }
    apply()
    query.addEventListener('change', apply)
    return () => query.removeEventListener('change', apply)
  }, [settings.appearance])
  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((cur) => {
      const next = { ...cur, ...patch }
      try {
        localStorage.setItem(KEY, JSON.stringify(next))
      } catch {
        /* storage unavailable: setting lasts for this visit */
      }
      return next
    })
  }, [])
  return [settings, update]
}
