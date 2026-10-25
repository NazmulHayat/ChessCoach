// Original Web Audio synthesis: no third-party recordings or network requests.
let ctx: AudioContext | null = null
let noise: AudioBuffer | null = null

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  try {
    ctx ??= new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    if (ctx.state === 'suspended') void ctx.resume().catch(() => {})
    return ctx
  } catch {
    return null
  }
}

function tone(ac: AudioContext, out: AudioNode, at: number, freq: number, dur: number, gain = .07) {
  const osc = ac.createOscillator()
  const g = ac.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(freq, at)
  g.gain.setValueAtTime(0, at)
  g.gain.linearRampToValueAtTime(gain, at + .006)
  g.gain.exponentialRampToValueAtTime(.0001, at + dur)
  osc.connect(g).connect(out)
  osc.start(at)
  osc.stop(at + dur + .02)
  osc.onended = () => { osc.disconnect(); g.disconnect() }
}

function tap(ac: AudioContext, out: AudioNode, at: number, freq = 850, gain = .45) {
  if (!noise) {
    noise = ac.createBuffer(1, Math.ceil(ac.sampleRate * .08), ac.sampleRate)
    const data = noise.getChannelData(0)
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  }
  const src = ac.createBufferSource()
  src.buffer = noise
  const filter = ac.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = freq
  filter.Q.value = 1.4
  const g = ac.createGain()
  g.gain.setValueAtTime(0, at)
  g.gain.linearRampToValueAtTime(gain, at + .003)
  g.gain.exponentialRampToValueAtTime(.0001, at + .075)
  src.connect(filter).connect(g).connect(out)
  src.start(at)
  src.onended = () => { src.disconnect(); filter.disconnect(); g.disconnect() }
  tone(ac, out, at, 280, .06, .12)
}

export type SoundKind = 'move' | 'capture' | 'check' | 'castle' | 'promote' | 'end' | 'illegal' | 'correct' | 'wrong'

export function play(kind: SoundKind, volume = 70) {
  if (!Number.isFinite(volume) || volume <= 0) return
  const ac = audio()
  if (!ac) return
  const out = ac.createGain()
  out.gain.value = Math.min(100, volume) / 100
  out.connect(ac.destination)
  const t = ac.currentTime + .005
  switch (kind) {
    case 'move':
      tap(ac, out, t)
      break
    case 'capture':
      tap(ac, out, t, 1150, .6)
      tap(ac, out, t + .045, 650, .35)
      break
    case 'check':
      tap(ac, out, t)
      tone(ac, out, t + .04, 740, .2)
      break
    case 'castle':
      tap(ac, out, t)
      tap(ac, out, t + .09, 650, .35)
      break
    case 'promote':
      tap(ac, out, t)
      tone(ac, out, t + .06, 660, .22)
      tone(ac, out, t + .16, 880, .3)
      break
    case 'end':
      for (const [i, f] of [440, 550, 660].entries()) tone(ac, out, t + i * .1, f, .4, .05)
      break
    case 'illegal':
      tone(ac, out, t, 190, .1, .06)
      tone(ac, out, t + .08, 190, .1, .04)
      break
    case 'correct':
      tone(ac, out, t, 550, .18)
      tone(ac, out, t + .12, 825, .3)
      break
    case 'wrong':
      tone(ac, out, t, 330, .18, .05)
      tone(ac, out, t + .12, 275, .24, .05)
      break
  }
  // Every source ends within .65s; release the master node too.
  setTimeout(() => out.disconnect(), 1000)
}

export function soundForSan(san: string): SoundKind {
  if (san.includes('=')) return 'promote'
  if (san.startsWith('O-O')) return 'castle'
  if (san.includes('+') || san.includes('#')) return 'check'
  return san.includes('x') ? 'capture' : 'move'
}
