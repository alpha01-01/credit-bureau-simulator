import type { Clock } from '../api/game'
import { useGameCommand } from '../api/game'
import { dateTime, formatClock } from '../lib/format'

const SPEEDS = [1, 2, 4, 8]

export function ClockBar({ gameId, clock }: { gameId: number; clock: Clock }) {
  const pause = useGameCommand(gameId, '/clock/pause/')
  const resume = useGameCommand(gameId, '/clock/resume/')
  const speed = useGameCommand(gameId, '/clock/speed/')
  const advance = useGameCommand(gameId, '/clock/advance/')
  const busy = pause.isPending || resume.isPending || speed.isPending || advance.isPending
  const running = clock.status === 'RUNNING'
  const error = [pause, resume, speed, advance].find((m) => m.error)?.error

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <div aria-live="polite">
        <span className="font-semibold tabular-nums" data-testid="game-clock">
          {formatClock(clock)}
        </span>
        <span className="ml-2 text-xs text-slate-500">
          next event {dateTime(clock.next_event.at)}
        </span>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={busy}
          onClick={() => (running ? pause : resume).mutate({})}
          className="rounded border border-slate-300 px-2 py-1 font-medium hover:bg-slate-50 disabled:opacity-50"
        >
          {running ? 'Pause' : 'Run'}
        </button>
        <label className="sr-only" htmlFor="speed">
          Speed
        </label>
        <select
          id="speed"
          value={clock.speed}
          disabled={busy}
          onChange={(e) => speed.mutate({ speed: Number(e.target.value) })}
          className="rounded border border-slate-300 px-1 py-1"
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-1" role="group" aria-label="Advance the clock">
        {[
          ['hour', '+1 hour'],
          ['day', 'End of day'],
          ['next_event', 'Next event'],
        ].map(([unit, label]) => (
          <button
            key={unit}
            type="button"
            disabled={busy || running}
            onClick={() => advance.mutate({ unit, count: 1 })}
            className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
          >
            {label}
          </button>
        ))}
      </div>
      {busy && (
        <span role="status" className="text-xs text-slate-500">
          Working…
        </span>
      )}
      {error && (
        <span role="alert" className="text-xs text-red-700">
          {error.message}
        </span>
      )}
    </div>
  )
}
