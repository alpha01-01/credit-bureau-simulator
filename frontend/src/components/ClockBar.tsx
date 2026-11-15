import { Link } from 'react-router'

import type { Clock, Notice, PauseRules, Severity } from '../api/game'
import { useGameCommand } from '../api/game'
import { drillPath } from '../lib/drill'
import { dateTime, formatClock } from '../lib/format'

const SPEEDS = [1, 2, 4, 8]
const SEVERITIES: [Severity, string][] = [
  ['CRITICAL', 'Critical events'],
  ['WARNING', 'Warnings'],
  ['INFO', 'Everything'],
]

export function ClockBar({ gameId, clock }: { gameId: number; clock: Clock }) {
  const pause = useGameCommand(gameId, '/clock/pause/')
  const resume = useGameCommand(gameId, '/clock/resume/')
  const speed = useGameCommand(gameId, '/clock/speed/')
  const advance = useGameCommand(gameId, '/clock/advance/')
  const busy = pause.isPending || resume.isPending || speed.isPending || advance.isPending
  const running = clock.status === 'RUNNING'
  const error = [pause, resume, speed, advance].find((m) => m.error)?.error

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div aria-live="polite">
          <span className="font-semibold tabular-nums" data-testid="game-clock">
            {formatClock(clock)}
          </span>
          <span className="ml-2 text-xs text-slate-500">
            {running ? (
              <span className="text-emerald-700">running at {clock.speed}x</span>
            ) : (
              <>next event {dateTime(clock.next_event.at)}</>
            )}
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
        <PauseRulesMenu gameId={gameId} rules={clock.pause_rules} />
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
      {clock.status === 'PAUSED' && clock.stopped_by && (
        <StoppedBanner gameId={gameId} notice={clock.stopped_by} />
      )}
    </div>
  )
}

/** Why the clock stopped by itself (Document 07, Section 5.2). */
function StoppedBanner({ gameId, notice }: { gameId: number; notice: Notice }) {
  const critical = notice.severity === 'CRITICAL'
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded border px-3 py-2 text-sm ${
        critical
          ? 'border-red-200 bg-red-50 text-red-900'
          : 'border-amber-200 bg-amber-50 text-amber-900'
      }`}
    >
      <span>
        <span className="font-semibold">Clock stopped:</span> {notice.title}
      </span>
      {notice.drill && (
        <Link
          to={drillPath(gameId, notice.drill)}
          className="font-medium underline underline-offset-2"
          aria-label={`Why? ${notice.title}`}
        >
          Why?
        </Link>
      )}
      <Link to={`/games/${gameId}/events`} className="text-xs underline underline-offset-2">
        All events
      </Link>
    </div>
  )
}

/** Which events stop the clock: the player's auto-pause rules. */
function PauseRulesMenu({ gameId, rules }: { gameId: number; rules: PauseRules }) {
  const save = useGameCommand(gameId, '/clock/pause-rules/')
  const toggle = (severity: Severity, on: boolean) => {
    const severities = on
      ? [...rules.severities, severity]
      : rules.severities.filter((s) => s !== severity)
    save.mutate({ severities, deadlines: rules.deadlines })
  }
  return (
    <details className="relative">
      <summary className="cursor-pointer list-none rounded border border-slate-300 px-2 py-1 hover:bg-slate-50">
        Stop for…
      </summary>
      <fieldset
        disabled={save.isPending}
        className="absolute right-0 z-20 mt-1 w-60 space-y-1.5 rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-lg"
      >
        <legend className="sr-only">Stop the clock for</legend>
        <p className="text-xs text-slate-500">The clock stops by itself for:</p>
        {SEVERITIES.map(([severity, label]) => (
          <label key={severity} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={rules.severities.includes(severity)}
              onChange={(e) => toggle(severity, e.target.checked)}
            />
            {label}
          </label>
        ))}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={rules.deadlines}
            onChange={(e) =>
              save.mutate({ severities: rules.severities, deadlines: e.target.checked })
            }
          />
          Work due today that no one has taken
        </label>
        {save.error && (
          <p role="alert" className="text-xs text-red-700">
            {save.error.message}
          </p>
        )}
      </fieldset>
    </details>
  )
}
