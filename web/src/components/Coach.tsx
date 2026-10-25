import type { CoachText } from '../coach'
import type { Label } from '../types'
import { LabelIcon } from './LabelIcon'

export function Coach({ text, label }: { text: CoachText; label?: Label }) {
  return (
    <div className="coach">
      <div className="coach-avatar" aria-hidden>
        <svg viewBox="0 0 32 32" width="26" height="26">
          <path d="M11 25h10l-1.2-3.2c1.9-1.3 2.9-3.4 2.9-5.6 0-1.7-.6-3.2-1.6-4.4l1.4-1.6-1.7-1.5-1.6 1.6A6.8 6.8 0 0 0 16 9.5c-3.7 0-6.7 3-6.7 6.7 0 2.2 1 4.3 2.9 5.6z" fill="#fff" />
        </svg>
      </div>
      <div className="bubble" aria-live="polite">
        <div className="bubble-title">
          {label && <LabelIcon label={label} size={20} />}
          <span>{text.title}</span>
        </div>
        <div className="bubble-body">{text.body}</div>
        {text.note && <div className="bubble-note">{text.note}</div>}
      </div>
    </div>
  )
}
