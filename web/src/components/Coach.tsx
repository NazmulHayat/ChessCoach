import type { ReactNode } from 'react'
import type { CoachText } from '../coach'
import type { Label } from '../types'
import { LabelIcon } from './LabelIcon'

interface Props {
  text: CoachText
  label?: Label
  ai?: { text?: string; loading?: boolean; error?: string } | null
  children?: ReactNode
}

export function Coach({ text, label, ai, children }: Props) {
  return (
    <div className="coach">
      <div className="coach-avatar" aria-hidden>
        <svg viewBox="0 0 32 32" width="26" height="26">
          <path d="M8 27h17M10 24c0-5 2-8 6-11l-6 3-4-3 6-7 1-3 4 3c7 1 10 9 7 18H10Z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx="15" cy="9" r="1.2" fill="currentColor" />
        </svg>
      </div>
      <div className="bubble" aria-live="polite">
        <div className="bubble-title">
          {label && <LabelIcon label={label} size={20} />}
          <span>{text.title}</span>
        </div>
        <div className="bubble-body">{text.body}</div>
        {text.note && <div className="bubble-note">{text.note}</div>}
        {text.line && <div className="bubble-line">{text.line}</div>}
        {ai && (
          <div className="bubble-ai" aria-live="polite">
            <span className="ai-tag">AI note</span>
            {ai.loading ? 'Thinking…' : ai.error ? <span className="ai-error">{ai.error}</span> : ai.text}
          </div>
        )}
        {children && <div className="coach-actions">{children}</div>}
      </div>
    </div>
  )
}
