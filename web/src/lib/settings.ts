// Per-browser preferences (board theme, sounds), kept in localStorage when available.
import { useCallback, useState } from 'react'

export type BoardTheme = 'slate' | 'green' | 'walnut' | 'ice'

export const BOARD_THEMES: Record<BoardTheme, { name: string; light: string; dark: string }> = {
  slate: { name: 'Slate', light: '#dee3e6', dark: '#8ca2ad' },
  green: { name: 'Green', light: '#eeeed2', dark: '#769656' },
  walnut: { name: 'Walnut', light: '#f0d9b5', dark: '#b58863' },
  ice: { name: 'Ice', light: '#e8eef5', dark: '#7d93b2' },
}

export interface Settings {
  theme: BoardTheme
  sounds: boolean
}

const KEY = 'cc.settings'
const DEFAULTS: Settings = { theme: 'slate', sounds: true }

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    const s = raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
    return s.theme in BOARD_THEMES ? s : { ...s, theme: DEFAULTS.theme }
  } catch {
    return DEFAULTS
  }
}

export function useSettings(): [Settings, (patch: Partial<Settings>) => void] {
  const [settings, setSettings] = useState<Settings>(load)
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
