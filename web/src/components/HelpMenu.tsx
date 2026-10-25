import { useEffect, useId, useRef } from 'react'
import { LABEL_ORDER, LABELS } from '../labels'
import { LABEL_HELP } from '../lib/help'
import { LabelIcon } from './LabelIcon'

const SHORTCUTS = [['← / →', 'Previous / next move'], ['Home / End', 'First / final position'], ['Space', 'Play / pause'], ['F', 'Flip the board'], ['?', 'Open this help']]

export function HelpMenu({ kind }: { kind: 'labels' | 'shortcuts' }) {
  const id = useId()
  const pop = useRef<HTMLDivElement>(null)
  const title = kind === 'labels' ? 'Move labels' : 'Keyboard shortcuts'
  useEffect(() => {
    if (kind !== 'shortcuts') return
    const key = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (e.key !== '?' || e.ctrlKey || e.metaKey || e.altKey || target.closest('input, textarea, select, [contenteditable="true"]')) return
      e.preventDefault()
      pop.current?.togglePopover()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [kind])
  return (
    <>
      <button type="button" className="icon-btn help-button" popoverTarget={id} aria-label={title} title={title}>
        {kind === 'labels' ? '?' : <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M5 9h2m2 0h2m2 0h2m2 0h2M5 12h2m2 0h2m2 0h2m2 0h2M7 15h10" /></svg>}
      </button>
      <div ref={pop} id={id} popover="auto" className="help-pop" role="dialog" aria-label={title}>
        <div className="popover-head"><h2>{title}</h2><button type="button" className="icon-btn" popoverTarget={id} popoverTargetAction="hide" aria-label={`Close ${title}`}>×</button></div>
        {kind === 'labels' ? <ul className="label-legend">{LABEL_ORDER.map((label) => <li key={label}><LabelIcon label={label} size={24} /><div><strong>{LABELS[label].name}</strong><p>{LABEL_HELP[label]}</p></div></li>)}</ul>
          : <><p className="muted">Use these while reviewing a game. Shortcuts pause while you type or use a popup.</p><dl className="shortcut-list">{SHORTCUTS.map(([keys, action]) => <div key={keys}><dt><kbd>{keys}</kbd></dt><dd>{action}</dd></div>)}</dl></>}
      </div>
    </>
  )
}
