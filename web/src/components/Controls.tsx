interface Props {
  onFirst: () => void
  onPrev: () => void
  onNext: () => void
  onLast: () => void
  onTogglePlay: () => void
  onFlip: () => void
  playing: boolean
  atStart: boolean
  atEnd: boolean
  retrying: boolean
}

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
    <path d={d} fill="currentColor" />
  </svg>
)

export function Controls({ onFirst, onPrev, onNext, onLast, onTogglePlay, onFlip, playing, atStart, atEnd, retrying }: Props) {
  return (
    <div className="controls">
      <button type="button" disabled={atStart} onClick={onFirst} aria-label="First move" title="First (Home)">
        <Icon d="M6 5h2v14H6zM20 5v14L9 12z" />
      </button>
      <button type="button" disabled={atStart} onClick={onPrev} aria-label="Previous move" title="Previous (←)">
        <Icon d="M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6z" />
      </button>
      <button type="button" className="ctl-play" disabled={atEnd || retrying} aria-pressed={playing} onClick={onTogglePlay} aria-label={playing ? 'Pause' : 'Play'} title="Play / pause (Space)">
        {playing ? <Icon d="M7 5h4v14H7zM13 5h4v14h-4z" /> : <Icon d="M8 5v14l11-7z" />}
      </button>
      <button type="button" disabled={atEnd} onClick={onNext} aria-label="Next move" title="Next (→)">
        <Icon d="M8.6 16.6 10 18l6-6-6-6-1.4 1.4 4.6 4.6z" />
      </button>
      <button type="button" disabled={atEnd} onClick={onLast} aria-label="Last move" title="Last (End)">
        <Icon d="M16 5h2v14h-2zM4 5v14l11-7z" />
      </button>
      <button type="button" className="ctl-flip" onClick={onFlip} aria-label="Flip board" title="Flip board (F)">
        <Icon d="M7 3 3 7h3v10h2V7h3zm10 18 4-4h-3V7h-2v10h-3z" />
      </button>
    </div>
  )
}
