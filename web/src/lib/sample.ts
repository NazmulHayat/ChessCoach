// A short, public-domain mating pattern with original sample player names.
export const SAMPLE_PGN = `[Event "ChessCoach sample: a queen sacrifice"]
[Site "Local"]
[Date "????.??.??"]
[White "Alice"]
[Black "Bob"]
[WhiteElo "1500"]
[BlackElo "1500"]
[Result "1-0"]
[TimeControl "600+0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Nc3 Bg4 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# 1-0`

/** What the import screen's board shows: the sample game right after 5. Nxe5!!, a queen sacrifice. */
export const SAMPLE_PREVIEW = {
  fen: 'r2qkbnr/ppp2ppp/2np4/4N3/2B1P1b1/2N5/PPPP1PPP/R1BQK2R b KQkq - 0 5',
  white: { name: 'Alice', elo: 1500, side: 'white', clock: '10:00' },
  black: { name: 'Bob', elo: 1500, side: 'black', clock: '10:00' },
  lastMove: { from: 'f3', to: 'e5' },
  badge: { square: 'e5', label: 'brilliant' },
  whiteShare: 0.69,
  evalText: '69%',
} as const
