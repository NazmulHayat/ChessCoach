import { Chessboard } from 'react-chessboard'
import { highlight } from '../lib/highlight'
import { Mat } from './BoardArea'

// Final position of the sample game: Légal's mate, 7.Nd5#.
const SAMPLE_MATE = 'r2q1bnr/ppp1kBpp/2np4/3NN3/4P3/8/PPPP1PPP/R1BbK2R b KQ - 2 7'

export function Welcome({ colors }: { colors: { light: string; dark: string } }) {
  return (
    <div className="welcome">
      <h1>Free game review, right in your browser</h1>
      <p className="welcome-pitch">Chess.com-style move labels, accuracy and game rating, judged by your real chances at your rating. Retry your mistakes on the board. Nothing uploaded; Stockfish runs locally.</p>
      <figure className="welcome-board">
        <Mat orientation="white">
          <div className="board">
            <Chessboard
              id="welcome-board"
              position={SAMPLE_MATE}
              arePiecesDraggable={false}
              areArrowsAllowed={false}
              showBoardNotation={false}
              customSquareStyles={{ c3: highlight('c3'), d5: highlight('d5') }}
              customDarkSquareStyle={{ backgroundColor: colors.dark }}
              customLightSquareStyle={{ backgroundColor: colors.light }}
              customBoardStyle={{ borderRadius: '2px' }}
            />
          </div>
        </Mat>
        <figcaption>The sample game ends in Légal’s mate: <strong>7.Nd5#</strong></figcaption>
      </figure>
    </div>
  )
}
