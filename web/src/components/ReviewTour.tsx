import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../lib/motion'

const STEPS = [
  { target: 'graph', title: 'Spot the turning points', body: 'Hover or tap the graph to explore the game. Click a point to jump to that position.' },
  { target: 'moves', title: 'Explore any move', body: 'Pick a move from the list to see its label, position and coach explanation.' },
  { target: 'retry', title: 'Turn a mistake into practice', body: 'On a mistake, miss or blunder, choose Retry and find a better move on the board.' },
]

export function ReviewTour({ onShowRetry }: { onShowRetry: () => void }) {
  const [step, setStep] = useState<number | null>(() => {
    try { return localStorage.getItem('cc.tour.seen') ? null : 0 } catch { return 0 }
  })
  const card = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 80, left: 16 })
  const reduced = useReducedMotion()

  function dismiss() {
    try { localStorage.setItem('cc.tour.seen', '1') } catch { /* This visit only. */ }
    setStep(null)
  }

  useEffect(() => {
    if (step === null) return
    const el = document.querySelector<HTMLElement>(`[data-tour="${STEPS[step].target}"]`)
    const popup = card.current
    if (!el || !popup) return
    popup.showPopover()
    el.classList.add('tour-target')
    el.scrollIntoView({ block: 'nearest', behavior: reduced ? 'instant' : 'smooth' })
    popup.focus({ preventScroll: true })
    const place = () => {
      const rect = el.getBoundingClientRect()
      const width = popup.offsetWidth
      const height = popup.offsetHeight
      setPosition({
        top: Math.max(12, Math.min(rect.bottom + 10, window.innerHeight - height - 12)),
        left: Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12)),
      })
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') dismiss() }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    window.addEventListener('keydown', key)
    return () => {
      el.classList.remove('tour-target')
      popup.hidePopover()
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('keydown', key)
    }
  }, [step, reduced])

  if (step === null) return null
  return (
    <div ref={card} popover="manual" className="tour-card" role="dialog" aria-label="Quick review tour" tabIndex={-1} style={position}>
      <div className="popover-head"><span className="muted">Quick tour · {step + 1} of 3</span><button type="button" className="icon-btn" onClick={dismiss} aria-label="Dismiss tour">×</button></div>
      <h2>{STEPS[step].title}</h2>
      <p>{STEPS[step].body}</p>
      <div className="tour-actions"><button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>Skip tour</button><button type="button" className="btn btn-primary btn-sm" onClick={() => {
        if (step === 2) dismiss()
        else { if (step === 1) onShowRetry(); setStep(step + 1) }
      }}>{step === 2 ? 'Got it' : 'Next'}</button></div>
    </div>
  )
}
