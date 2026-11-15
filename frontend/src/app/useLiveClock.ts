/**
 * The live clock (P2.2): while the game is running, the open game page asks
 * the server for one tick at a time, at the chosen speed. No separate clock
 * process is needed. The server refuses a tick that comes too soon, so two
 * open tabs do not make the game run faster.
 */

import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { apiPost } from '../api/client'
import type { Clock, GameSummary } from '../api/game'

/** Real seconds per tick at 1x (Document 07, Section 5.1: a game hour in 20 seconds). */
export const SECONDS_PER_TICK = 5
/** Other screens are refreshed at most this often while the clock runs. */
const REFRESH_MS = 3000

export function useLiveClock(gameId: number, clock: Clock | null) {
  const client = useQueryClient()
  const running = clock?.status === 'RUNNING'
  const speed = clock?.speed ?? 1

  useEffect(() => {
    if (!running) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let refreshed = 0
    const interval = (SECONDS_PER_TICK * 1000) / speed

    const tick = async () => {
      const started = Date.now()
      try {
        const next = await apiPost<Clock>(`/games/${gameId}/clock/step/`, {})
        if (cancelled) return
        client.setQueryData<GameSummary>([gameId, 'game'], (old) =>
          old ? { ...old, clock: next } : old,
        )
        const now = Date.now()
        if (next.status !== 'RUNNING' || now - refreshed >= REFRESH_MS) {
          refreshed = now
          void client.invalidateQueries({
            queryKey: [gameId],
            predicate: (q) => q.queryKey[1] !== 'game',
          })
        }
        if (next.status !== 'RUNNING') return // stopped: by the player or by an event
      } catch {
        // A failed tick is tried again at the next interval.
      }
      if (!cancelled) {
        timer = setTimeout(tick, Math.max(0, interval - (Date.now() - started)))
      }
    }
    timer = setTimeout(tick, interval)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [client, gameId, running, speed])
}
