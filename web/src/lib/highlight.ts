/** Last-move tint, opaque per square colour so it stays yellow on dark squares instead of muddying them. */
export function highlight(square: string): Record<string, string> {
  const dark = (square.charCodeAt(0) - 97 + Number(square[1])) % 2 === 1
  return { boxShadow: `inset 0 0 0 999px var(--sq-highlight-${dark ? 'dark' : 'light'})` }
}
