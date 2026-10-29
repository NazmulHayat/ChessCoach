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
      <div className="bubble" aria-live="polite">
        <div className="bubble-title">
          {label && <LabelIcon label={label} size={22} />}
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
