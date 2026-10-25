import { describe, expect, it } from 'vitest'
import { SearchAccumulator, UciEngine, fieldsFromSearch, parseInfo, type EngineTransport } from './uci'

function search(lines: string[]): SearchAccumulator {
  const acc = new SearchAccumulator()
  for (const l of lines) acc.feed(l)
  return acc
}

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const BLACK_TO_MOVE = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

describe('parseInfo', () => {
  it('reads depth, multipv, score and pv', () => {
    const i = parseInfo('info depth 17 seldepth 22 multipv 2 score cp -35 nodes 123 nps 1000 hashfull 5 time 9 pv e7e5 g1f3 b8c6')
    expect(i).toEqual({ multipv: 2, depth: 17, kind: 'cp', value: -35, pv: ['e7e5', 'g1f3', 'b8c6'] })
  })
  it('handles bounds, mate and strings', () => {
    expect(parseInfo('info depth 9 score cp 20 upperbound nodes 5 pv e2e4')).toMatchObject({ kind: 'cp', value: 20, pv: ['e2e4'] })
    expect(parseInfo('info depth 5 multipv 1 score mate -3 pv a1a2')).toMatchObject({ kind: 'mate', value: -3 })
    expect(parseInfo('info string NNUE evaluation using nn.nnue')).toEqual({ multipv: 1 })
    expect(parseInfo('bestmove e2e4 ponder e7e5')).toBeNull()
  })
})

describe('fieldsFromSearch', () => {
  it('takes the last merged line per multipv, white-relative by side to move', () => {
    const acc = search([
      'info depth 16 multipv 1 score cp 30 pv e2e4 e7e5',
      'info depth 16 multipv 2 score cp 20 pv d2d4',
      'info depth 17 currmove e2e4 currmovenumber 1',
      'info depth 17 multipv 1 score cp 41 pv e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1',
      'info depth 17 multipv 2 score cp 33 pv d2d4 d7d5',
      'bestmove e2e4 ponder e7e5',
    ])
    expect(fieldsFromSearch(START, acc)).toEqual({
      eval_cp_white: 41, mate_white: null, eval_cp_stm: 41, mate_stm: null, eval_depth: 17,
      best_uci: 'e2e4', pv_uci: ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6', 'b5a4', 'g8f6'],
      second_uci: 'd2d4', second_cp_stm: 33, second_mate_stm: null,
    })
  })
  it('flips the sign for black to move and reads mate scores', () => {
    const acc = search(['info depth 12 multipv 1 score mate 2 pv d8h4', 'info depth 12 multipv 2 score cp -150 pv e7e5', 'bestmove d8h4'])
    const f = fieldsFromSearch(BLACK_TO_MOVE, acc)
    expect(f).toMatchObject({ mate_stm: 2, mate_white: -2, eval_cp_stm: null, eval_cp_white: null, second_cp_stm: -150 })
  })
  it('leaves second_* empty when there is one legal move', () => {
    const f = fieldsFromSearch(START, search(['info depth 20 multipv 1 score cp 5 pv e2e4', 'bestmove e2e4']))
    expect(f).toMatchObject({ second_uci: null, second_cp_stm: null, second_mate_stm: null })
  })
  it('matches python-chess on terminal positions (mate 0 / cp 0 at depth 0, no move)', () => {
    const mated = fieldsFromSearch('rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3', search(['info depth 0 score mate 0', 'bestmove (none)']))
    expect(mated).toEqual({
      eval_cp_white: null, mate_white: 0, eval_cp_stm: null, mate_stm: 0, eval_depth: 0,
      best_uci: null, pv_uci: [], second_uci: null, second_cp_stm: null, second_mate_stm: null,
    })
    expect(Object.is(mated.mate_white, -0)).toBe(false)
    const stale = fieldsFromSearch('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', search(['info depth 0 score cp 0', 'bestmove (none)']))
    expect(stale).toMatchObject({ eval_cp_white: 0, eval_cp_stm: 0, mate_stm: null, eval_depth: 0, best_uci: null })
    expect(Object.is(stale.eval_cp_white, -0)).toBe(false)
  })
})

// The real WASM engine, driven through the same UciEngine code path the browser workers use.
describe('Stockfish 18 lite (node)', () => {
  it('analyses real positions', async () => {
    const pkg = 'stockfish' // the npm package's node loader (CommonJS), untyped
    const mod = await import(/* @vite-ignore */ pkg)
    const initEngine = (mod.default ?? mod) as (name: string) => Promise<{ sendCommand(c: string): void; listener?: (l: string) => void }>
    const raw = await initEngine('lite-single')
    const listeners: ((l: string) => void)[] = []
    raw.listener = (l) => listeners.forEach((fn) => fn(l))
    const transport: EngineTransport = { send: (c) => raw.sendCommand(c), onLine: (fn) => listeners.push(fn) }
    const eng = new UciEngine(transport)
    await eng.init(16, 2)
    const fens = [
      START,
      BLACK_TO_MOVE,
      '6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1', // mate in 1
      'rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3', // checkmated
      '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', // stalemate
    ]
    const out = []
    for (const fen of fens) out.push(await eng.analyse(fen, 10))
    expect(out[0].eval_depth).toBe(10)
    expect(out[0].best_uci).toMatch(/^[a-h][1-8][a-h][1-8]/)
    expect(out[0].second_uci).not.toBeNull()
    expect(Math.abs(out[0].eval_cp_stm!)).toBeLessThan(100)
    expect(out[1].eval_cp_white).toBe(-out[1].eval_cp_stm!)
    expect(out[2]).toMatchObject({ mate_stm: 1, mate_white: 1, best_uci: 'd1d8' })
    expect(out[3]).toMatchObject({ mate_stm: 0, mate_white: 0, best_uci: null, eval_depth: 0 })
    expect(out[4]).toMatchObject({ eval_cp_stm: 0, eval_cp_white: 0, best_uci: null })
  }, 120_000)
})
