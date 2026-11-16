import { useState } from 'react'
import { Link } from 'react-router'

import {
  type Assistance,
  type MissionRow,
  useAssistance,
  useGameCommand,
  useMissions,
} from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page } from '../components/ui'

const TOGGLES: [keyof Assistance, string][] = [
  ['assist_accuracy', 'Show estimated accuracy on work items'],
  ['assist_recommend', "Show the bureau's recommended decision"],
  ['pause_all', 'Stop the clock for every event'],
  ['assist_extended_deadlines', 'Extended deadlines (ten working days for work items)'],
]

function Debrief({ debrief }: { debrief: NonNullable<MissionRow['debrief']> }) {
  return (
    <div className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-3 text-sm">
      <p className="font-semibold">Debrief: {debrief.headline}</p>
      <table className="mt-2">
        <tbody>
          {debrief.figures.map(([label, value]) => (
            <tr key={label}>
              <td className="pr-4">{label}</td>
              <td className="text-right tabular-nums">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {debrief.lessons.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </div>
  )
}

function Current({ gameId, mission }: { gameId: number; mission: MissionRow }) {
  const act = useGameCommand<{ last_answer?: { right: boolean } }>(gameId, '/missions/')
  const [value, setValue] = useState('')
  const q = mission.question
  const verdict = act.data?.last_answer
  return (
    <div className="mt-3 space-y-3 text-sm">
      <ul className="space-y-1">
        {mission.objectives?.map((o) => (
          <li key={o.text} className="flex items-start gap-2">
            <span aria-hidden="true">{o.done ? '✓' : '○'}</span>
            <span className={o.done ? 'text-slate-500 line-through' : ''}>
              {o.text}
              {o.progress && <span className="ml-1 text-xs text-slate-500">({o.progress})</span>}
              <span className="sr-only">{o.done ? ' (done)' : ' (to do)'}</span>
            </span>
          </li>
        ))}
      </ul>
      {q && (
        <div className="rounded border border-slate-200 p-3">
          <p className="font-medium">{q.text}</p>
          {q.answered ? (
            <p className="mt-2 text-emerald-700">Answered correctly.</p>
          ) : q.ready ? (
            <form
              className="mt-2 flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                act.mutate({ action: 'answer', code: mission.code, value })
              }}
            >
              <label htmlFor="mission-answer" className="sr-only">
                Your answer
              </label>
              <input
                id="mission-answer"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-36 rounded border border-slate-300 px-1 py-0.5 text-right"
              />
              <span className="text-slate-500">{q.unit}</span>
              <button
                type="submit"
                disabled={act.isPending || !value}
                className="rounded border border-brand px-2 py-1 font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50"
              >
                Answer
              </button>
              {verdict && !verdict.right && (
                <span role="alert" className="text-red-700">
                  Not quite. Look again at the screen the question names.
                </span>
              )}
            </form>
          ) : (
            <p className="mt-2 text-slate-500">Not yet: carry on playing.</p>
          )}
          {act.isError && <Failed error={act.error} />}
        </div>
      )}
      <p>
        Read first:{' '}
        {mission.handbook.map((k, n) => (
          <span key={k}>
            {n > 0 && ', '}
            <Link to={`/games/${gameId}/handbook#${k}`} className="text-brand hover:underline">
              {k.replaceAll('-', ' ')}
            </Link>
          </span>
        ))}
      </p>
    </div>
  )
}

/**
 * The learning campaign (P2.11; Document 07, Section 11): missions M1-M6 in order, each
 * ending in a debrief that reveals what really happened, and the assistance toggles.
 */
export function MissionsPage() {
  const gameId = useGameId()
  const missions = useMissions(gameId)
  const assistance = useAssistance(gameId)
  const toggle = useGameCommand(gameId, '/assistance/')
  const campaign = useGameCommand(gameId, '/missions/')
  if (missions.isPending || assistance.isPending) return <Loading what="the missions" />
  if (missions.isError) return <Failed error={missions.error} />
  if (assistance.isError) return <Failed error={assistance.error} />
  const m = missions.data
  return (
    <Page
      title="Missions"
      subtitle="Short missions that teach the job by doing it. They use the same simulation as the rest of the game."
      actions={
        <button
          type="button"
          disabled={campaign.isPending}
          onClick={() => campaign.mutate({ action: 'campaign', on: !m.campaign })}
          className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {m.campaign ? 'Turn the campaign off' : 'Turn the campaign on'}
        </button>
      }
    >
      {m.missions.map((mission) => (
        <Card key={mission.code} title={`${mission.code} · ${mission.title}`}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge
              tone={
                mission.status === 'DONE'
                  ? 'good'
                  : mission.status === 'CURRENT'
                    ? 'info'
                    : 'neutral'
              }
            >
              {mission.status === 'DONE' ? 'done' : mission.status === 'CURRENT' ? 'now' : 'later'}
            </Badge>
            <span className="text-slate-600">{mission.concept}</span>
          </div>
          {mission.status === 'CURRENT' && <Current gameId={gameId} mission={mission} />}
          {mission.debrief && <Debrief debrief={mission.debrief} />}
        </Card>
      ))}
      <Card title="Assistance">
        <p className="mb-2 text-sm text-slate-600">
          Help that does not change the economics. Turn it off as you grow confident.
        </p>
        <div className="space-y-1 text-sm">
          {TOGGLES.map(([name, label]) => (
            <label key={name} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={assistance.data[name]}
                disabled={toggle.isPending}
                onChange={(e) => toggle.mutate({ name, on: e.target.checked })}
              />
              {label}
            </label>
          ))}
        </div>
        {toggle.isError && <Failed error={toggle.error} />}
      </Card>
    </Page>
  )
}
