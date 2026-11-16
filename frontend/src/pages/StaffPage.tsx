import { useState } from 'react'

import { useGameCommand, useStaff } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page, Table, Td } from '../components/ui'
import { day, money, percent } from '../lib/format'

const WORK = { MATCH_REVIEW: 'Match', UNLOADABLE_TRIAGE: 'Triage', DISPUTE: 'Disputes' } as const

function skill(skills: Record<string, number>, type: keyof typeof WORK) {
  return skills[type] === undefined ? '—' : percent(skills[type])
}

function moraleTone(m: number) {
  return m >= 0.6 ? 'good' : m >= 0.4 ? 'warn' : 'bad'
}

/**
 * HR (P2.9): the Data Operations team, this month's candidates, pay and training.
 * Morale follows pay against the market and the weight of the queue; people whose
 * morale falls too low may resign.
 */
export function StaffPage() {
  const gameId = useGameId()
  const staff = useStaff(gameId)
  const act = useGameCommand(gameId, '/staff/')
  const [pay, setPay] = useState<Record<string, string>>({})
  if (staff.isPending) return <Loading what="the team" />
  if (staff.isError) return <Failed error={staff.error} />
  const s = staff.data
  const types = Object.keys(WORK) as (keyof typeof WORK)[]
  return (
    <Page
      title="Staff"
      subtitle={`Morale follows pay against the market and how heavy the queue is; below 40% people may resign. A training course costs ${money(s.training_cost)} and takes the person away for a working day.`}
    >
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      <Card title="The team">
        <Table
          head={[
            'Employee',
            'Role',
            ...types.map((t) => WORK[t]),
            'Morale',
            'Salary',
            'Market',
            '',
          ]}
        >
          {s.team.map((e) => (
            <tr key={e.number} className={e.active ? '' : 'text-slate-400'}>
              <Td>
                {e.name} <span className="text-xs text-slate-500">{e.number}</span>
                {!e.active && (
                  <span className="ml-2">
                    <Badge>left</Badge>
                  </span>
                )}
                {e.away && (
                  <span className="ml-2">
                    <Badge tone="info">on a course</Badge>
                  </span>
                )}
              </Td>
              <Td>{e.job_title}</Td>
              {types.map((t) => (
                <Td key={t} right>
                  {skill(e.skills, t)}
                </Td>
              ))}
              <Td right>
                <Badge tone={moraleTone(e.morale)}>{percent(e.morale)}</Badge>
              </Td>
              <Td right>{money(e.salary)}</Td>
              <Td right>{money(e.market_salary)}</Td>
              <Td>
                {e.active && (
                  <div className="flex flex-wrap items-center gap-1">
                    <label className="sr-only" htmlFor={`pay-${e.number}`}>
                      New salary for {e.name}
                    </label>
                    <input
                      id={`pay-${e.number}`}
                      inputMode="decimal"
                      placeholder={e.salary}
                      value={pay[e.number] ?? ''}
                      onChange={(ev) => setPay({ ...pay, [e.number]: ev.target.value })}
                      className="w-24 rounded border border-slate-300 px-1 py-0.5 text-right text-sm"
                    />
                    <button
                      type="button"
                      disabled={act.isPending || !pay[e.number]}
                      onClick={() =>
                        act.mutate({ action: 'salary', employee: e.number, salary: pay[e.number] })
                      }
                      className="rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                    >
                      Set pay
                    </button>
                    <label className="sr-only" htmlFor={`train-${e.number}`}>
                      Train {e.name} in
                    </label>
                    <select
                      id={`train-${e.number}`}
                      disabled={act.isPending || e.away}
                      value=""
                      onChange={(ev) =>
                        ev.target.value &&
                        act.mutate({
                          action: 'train',
                          employee: e.number,
                          work_type: ev.target.value,
                        })
                      }
                      className="rounded border border-slate-300 px-1 py-0.5 text-sm disabled:opacity-50"
                    >
                      <option value="">Train in…</option>
                      {s.training_types.map((t) => (
                        <option key={t} value={t}>
                          {WORK[t as keyof typeof WORK] ?? t}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card
        title={`Looking for work this month (until the end of ${day(s.month).replace(/^\d+ /, '')})`}
      >
        <Table head={['Candidate', 'Role', ...types.map((t) => WORK[t]), 'Asks', '']}>
          {s.candidates.map((c) => (
            <tr key={c.number}>
              <Td>{c.name}</Td>
              <Td>{c.job_title}</Td>
              {types.map((t) => (
                <Td key={t} right>
                  {skill(c.skills, t)}
                </Td>
              ))}
              <Td right>{money(c.asking_salary)}</Td>
              <Td>
                {c.hired ? (
                  <Badge tone="good">hired</Badge>
                ) : (
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ action: 'hire', candidate: c.number })}
                    className="rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                  >
                    Hire
                  </button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
    </Page>
  )
}
