export function Welcome() {
  return (
    <div className="welcome">
      <div className="welcome-mark" aria-hidden>♞</div>
      <h1>Free game review,<br />right in your browser</h1>
      <p className="welcome-pitch">Chess.com-style move labels, accuracy, game rating, and a chance to retry your mistakes. Nothing uploaded. Analysis runs locally.</p>
      <ol className="how-it-works">
        <li><span>1</span><div><strong>Pick a game</strong><p>Import from Chess.com or Lichess, or paste a PGN.</p></div></li>
        <li><span>2</span><div><strong>We analyze every move</strong><p>See where the game turned and what you could improve.</p></div></li>
        <li><span>3</span><div><strong>Review and retry mistakes</strong><p>Find a better move on the board and make it stick.</p></div></li>
      </ol>
      <p className="welcome-foot">No account needed · Powered by Stockfish</p>
    </div>
  )
}
