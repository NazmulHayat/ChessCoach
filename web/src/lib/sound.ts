// Move sounds synthesised with Web Audio (no audio files): a short filtered noise "tap" for a move,
// a sharper double tap for a capture, a tone for check, and chimes for retry results.

let ctx: AudioContext | null = null

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  try {
    ctx ??= new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    if (ctx.state === 'suspended') void ctx.resume()
    return ctx
  } catch {
    return null
  }
}

function tap(ac: AudioContext, at: number, freq: number, gain: number, decay: number) {
  const len = Math.floor(ac.sampleRate * decay)
  const buf = ac.createBuffer(1, len, ac.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 4)
  const src = ac.createBufferSource()
  src.buffer = buf
  const filter = ac.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = freq
  filter.Q.value = 1.2
  const g = ac.createGain()
  g.gain.value = gain
  src.connect(filter).connect(g).connect(ac.destination)
  src.start(at)
}

function tone(ac: AudioContext, at: number, freq: number, dur: number, gain = 0.08) {
  const osc = ac.createOscillator()
  const g = ac.createGain()
  osc.type = 'sine'
  osc.frequency.value = freq
  g.gain.setValueAtTime(0, at)
  g.gain.linearRampToValueAtTime(gain, at + 0.01)
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur)
  osc.connect(g).connect(ac.destination)
  osc.start(at)
  osc.stop(at + dur + 0.02)
}

export type SoundKind = 'move' | 'capture' | 'check' | 'correct' | 'wrong'

export function play(kind: SoundKind) {
  const ac = audio()
  if (!ac) return
  const t = ac.currentTime + 0.005
  switch (kind) {
    case 'move':
      tap(ac, t, 1800, 0.9, 0.07)
      break
    case 'capture':
      tap(ac, t, 2400, 1.0, 0.06)
      tap(ac, t + 0.045, 1300, 0.8, 0.08)
      break
    case 'check':
      tap(ac, t, 1800, 0.9, 0.07)
      tone(ac, t + 0.02, 880, 0.18)
      break
    case 'correct':
      tone(ac, t, 660, 0.16)
      tone(ac, t + 0.11, 990, 0.26)
      break
    case 'wrong':
      tone(ac, t, 300, 0.22, 0.07)
      tone(ac, t + 0.12, 240, 0.28, 0.07)
      break
  }
}

/** Sound for a SAN move: check beats capture beats a plain move. */
export function soundForSan(san: string): SoundKind {
  if (san.includes('+') || san.includes('#')) return 'check'
  return san.includes('x') ? 'capture' : 'move'
}
