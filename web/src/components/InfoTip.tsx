import { useId, type ReactNode } from 'react'

export function InfoTip({ label, children, trigger = 'i' }: { label: string; children: ReactNode; trigger?: ReactNode }) {
  const id = useId()
  return (
    <>
      <button type="button" className="info-trigger" popoverTarget={id} aria-label={`About ${label}`}>{trigger}</button>
      <div id={id} popover="auto" className="info-pop" role="dialog" aria-label={label}>
        <div className="popover-head"><strong>{label}</strong><button type="button" className="icon-btn" popoverTarget={id} popoverTargetAction="hide" aria-label={`Close ${label}`}>×</button></div>
        <div className="info-copy">{children}</div>
      </div>
    </>
  )
}
