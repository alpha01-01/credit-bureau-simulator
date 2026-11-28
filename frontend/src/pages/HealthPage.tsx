import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'

import { type HealthPart, useGameCommand, useHealth } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, day, money, percent } from '../lib/format'

const TONE = { good: 'good', watch: 'warn', poor: 'bad', unknown: 'neutral' } as const
const VERDICT_TONE: Record<string, 'good' | 'warn' | 'bad'> = {
  CONFIDENT: 'good',
  CONCERNED: 'warn',
  NO_CONFIDENCE: 'bad',
  REMOVED: 'bad',
}

function Score({ part }: { part: HealthPart }) {
  return (
    <Badge tone={TONE[part.rating]}>
      {part.score === null ? 'not measured yet' : `${Math.round(part.score)} · ${part.rating}`}
    </Badge>
  )
}

/**
 * Bureau Health (P2.10; Document 07, Section 10.3): five dimensions, the board's view
 * of them, and the three hard failures with where the bureau stands on each road
 * and the way back.
 */
export function HealthPage() {
  const gameId = useGameId()
  const health = useHealth(gameId)
  const act = useGameCommand(gameId, '/health/')
  const [amount, setAmount] = useState('')
  // The office's boardroom opens the board's reviews (P4.6): /health#board.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash && health.data) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash, health.data])
  if (health.isPending) return <Loading what="the bureau's health" />
  if (health.isError) return <Failed error={health.error} />
  const h = health.data
  const { financial: fin, data_quality: dq, reputation: rep, compliance, team } = h.parts
  return (
    <Page
      title="Bureau Health"
      subtitle={`Overall ${Math.round(h.overall)} out of 100, as of ${day(h.as_of)}. The board's confidence at each quarterly review is this same figure.`}
    >
      {h.ended && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
          <p className="font-semibold text-red-800">{h.ended.title}. The game is over.</p>
          <p className="mt-1 text-red-800">
            The warnings that led here are in the Events feed and below.
          </p>
        </div>
      )}
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Finances">
          <Score part={fin} />
          <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
            <dt>Bank</dt>
            <dd className="text-right">{money(fin.bank)}</dd>
            <dt>A month's costs</dt>
            <dd className="text-right">{money(fin.monthly_costs)}</dd>
            <dt>Runway</dt>
            <dd className="text-right">{fin.runway_months} months</dd>
            <dt>Last three months</dt>
            <dd className="text-right">{money(fin.result_3_months)}</dd>
            <dt>Overdraft used</dt>
            <dd className="text-right">
              {money(fin.overdraft_used)} of {money(fin.overdraft_limit)}
            </dd>
          </dl>
        </Card>
        <Card title="Data quality">
          <Score part={dq} />
          {dq.as_of ? (
            <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
              <dt>Audited accuracy</dt>
              <dd className="text-right">{percent(dq.accuracy)}</dd>
              <dt>Coverage of active borrowers</dt>
              <dd className="text-right">{percent(dq.coverage)}</dd>
              <dt>Freshness</dt>
              <dd className="text-right">
                {dq.freshness_days == null ? '—' : `${dq.freshness_days} days`}
              </dd>
              <dt>Measured</dt>
              <dd className="text-right">{day(dq.as_of)}</dd>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-slate-500">Measured at the first month end.</p>
          )}
        </Card>
        <Card title="Reputation">
          <Score part={rep} />
          <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
            <dt>With subscribers</dt>
            <dd className="text-right">{rep.subscribers}</dd>
            <dt>With providers</dt>
            <dd className="text-right">{rep.providers}</dd>
            <dt>With the regulator</dt>
            <dd className="text-right">{rep.regulator}</dd>
          </dl>
        </Card>
        <Card title="Compliance and team">
          <div className="flex flex-wrap gap-2">
            <Score part={compliance} />
            <Score part={team} />
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
            <dt>Regulator</dt>
            <dd className="text-right">{compliance.standing}</dd>
            <dt>Findings, six months</dt>
            <dd className="text-right">{count(compliance.findings_6_months)}</dd>
            <dt>Staff</dt>
            <dd className="text-right">{count(team.staff)}</dd>
            <dt>Average morale</dt>
            <dd className="text-right">{percent(team.average_morale)}</dd>
            <dt>Resignations, three months</dt>
            <dd className="text-right">{count(team.resignations_3_months)}</dd>
          </dl>
        </Card>
      </div>

      <Card title="The roads to failure">
        <div className="space-y-4">
          {h.failures.map((f) => (
            <div key={f.key}>
              <h3 className="text-sm font-semibold">{f.name}</h3>
              <ol className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                {f.steps.map((s, i) => (
                  <li key={s.code} className="flex items-center gap-1">
                    {i > 0 && <span aria-hidden="true">→</span>}
                    <span
                      className={`rounded px-1.5 py-0.5 ${s.reached ? 'bg-red-50 font-medium text-red-800' : 'bg-slate-50 text-slate-500'}`}
                    >
                      {s.reached && <span className="sr-only">Reached: </span>}
                      {s.label}
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-1 text-sm">
                {f.current ? (
                  <>
                    Now: <strong>{f.current}</strong>.{f.next && <> Next: {f.next}.</>} {f.detail}
                  </>
                ) : (
                  'Not on this road.'
                )}
              </p>
              <p className="mt-1 text-sm text-slate-600">Way back: {f.path_back}</p>
            </div>
          ))}
        </div>
      </Card>

      <section id="board" className="scroll-mt-4">
        <Card title="Quarterly board reviews">
          {h.board_reviews.length === 0 ? (
            <Empty>The board reviews each quarter once the management has run a full one.</Empty>
          ) : (
            <Table head={['Quarter ending', 'Confidence', 'Verdict', 'What it said']}>
              {h.board_reviews.map((r) => (
                <tr key={r.period}>
                  <Td>{day(r.period)}</Td>
                  <Td right>{Math.round(r.confidence)}</Td>
                  <Td>
                    <Badge tone={VERDICT_TONE[r.verdict] ?? 'neutral'}>
                      {r.verdict.toLowerCase().replaceAll('_', ' ')}
                    </Badge>
                  </Td>
                  <Td>{r.detail}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </section>

      <Card title="Ask the shareholders for capital">
        <p className="mb-3 text-sm text-slate-600">
          Up to {money(h.funding.max)}, once a quarter. They agree while the board's confidence at
          its last review is {h.funding.needs_confidence} or more.
        </p>
        {!h.ended && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label htmlFor="funding" className="text-sm">
              Amount
            </label>
            <input
              id="funding"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-36 rounded border border-slate-300 px-1 py-0.5 text-right text-sm"
            />
            <button
              type="button"
              disabled={act.isPending || !amount}
              onClick={() => act.mutate({ action: 'funding', amount })}
              className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              Ask
            </button>
          </div>
        )}
        {h.funding.requests.length > 0 && (
          <Table head={['Asked', 'Amount', 'Answer', 'Why']}>
            {h.funding.requests.map((f) => (
              <tr key={f.number}>
                <Td>{dateTime(f.requested_at)}</Td>
                <Td right>{money(f.amount)}</Td>
                <Td>
                  {f.granted ? (
                    <Badge tone="good">granted</Badge>
                  ) : (
                    <Badge tone="bad">refused</Badge>
                  )}
                </Td>
                <Td>{f.reason}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  )
}
