/**
 * The newest event this browser has shown, per game, so the navigation can say
 * when there is something new. A convenience only: losing it is harmless.
 */

const key = (gameId: number) => `simb.events.seen.${gameId}`

export function lastSeen(gameId: number): number {
  try {
    return Number(localStorage.getItem(key(gameId)) ?? 0) || 0
  } catch {
    return 0
  }
}

export function markSeen(gameId: number, noticeId: number): void {
  try {
    if (noticeId > lastSeen(gameId)) localStorage.setItem(key(gameId), String(noticeId))
  } catch {
    // storage unavailable: the "new" marker just stays
  }
}

export function hasUnseen(gameId: number, latest: number | null): boolean {
  return latest !== null && latest > lastSeen(gameId)
}
