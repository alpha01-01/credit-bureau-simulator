import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { type Measures, useScorecard, useScorecards } from '../api/analytics'
import { useGameCommand } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, day, dateTime, percent } from '../lib/format'

const TERM_NAMES: Record<string, string> = {
  SHORT: 'Short term',
  MID: 'Mid term',
  LONG: 'Long term',
  ALL: 'All loans',
  COMPOSITE: 'Composite',
}

function measure(m: Measures | null | undefined, key: 'auc' | 'gini' | 'ks'): string {
  const v = m?.[key]
  return v === null || v === undefined ? '—' : v.toFixed(3)
}

/** The scorecard workbench (P3.5): build, compare, deploy. */
export function ScorecardsPage() {
  const gameId = useGameId()
  const data = useScorecards(gameId)
  const act = useGameCommand(gameId, '/scorecards/')
  const [term, setTerm] = useState('SHORT')
  const [window, setWindow] = useState<number | null>(null)
  const [observation, setObservation] = useState('')
  const [chosen, setChosen] = useState<string[] | null>(null)
  if (data.isPending) return <Loading what="the workbench" />
  if (data.isError) return <Failed error={data.error} />
  const { options, models, findings } = data.data
  const windows = options.windows.filter((w) => w.observation_dates.length > 0)
  const months = window ?? windows.at(-1)?.months ?? options.default_window
  const dates = options.windows.find((w) => w.months === months)?.observation_dates ?? []
  const when = dates.includes(observation) ? observation : (dates[0] ?? '')
  const features =
    chosen ?? options.features.filter((f) => f.recommended_for.includes(term)).map((f) => f.name)
  const toggle = (name: string) =>
    setChosen(features.includes(name) ? features.filter((f) => f !== name) : [...features, name])

  return (
    <Page
      title="Scorecard workbench"
      subtitle="Build a scorecard for each term of loan from the bureau's own data, validate it on customers it has not seen, combine them, and put the best into use."
    >
      {findings.length > 0 && (
        <Card title="Compliance findings">
          <ul className="space-y-1 text-sm">
            {findings.map((f) => (
              <li key={f.number}>
                <Badge tone="warn">{f.reference}</Badge> {f.detail}{' '}
                <span className="text-xs text-slate-500">{dateTime(f.raised_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Build a scorecard">
        {windows.length === 0 ? (
          <Empty>
            Not enough history on file yet: a scorecard needs at least one month of history and
            three months of outcomes after its observation date.
          </Empty>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              act.mutate({ action: 'build', term, observation: when, window: months, features })
            }}
          >
            <div className="flex flex-wrap gap-3 text-sm">
              <label className="flex flex-col">
                Term
                <select
                  value={term}
                  onChange={(e) => {
                    setTerm(e.target.value)
                    setChosen(null)
                  }}
                  className="rounded border border-slate-300 px-2 py-1"
                >
                  {options.terms.map((t) => (
                    <option key={t.code} value={t.code}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col">
                Outcome window
                <select
                  value={months}
                  onChange={(e) => setWindow(Number(e.target.value))}
                  className="rounded border border-slate-300 px-2 py-1"
                >
                  {windows.map((w) => (
                    <option key={w.months} value={w.months}>
                      {w.months} months{w.months === 12 ? ' (the default definition)' : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col">
                Observation date
                <select
                  value={when}
                  onChange={(e) => setObservation(e.target.value)}
                  className="rounded border border-slate-300 px-2 py-1"
                >
                  {dates.map((d) => (
                    <option key={d} value={d}>
                      {day(d)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <fieldset>
              <legend className="text-sm font-medium">Characteristics</legend>
              <div className="mt-1 grid gap-1 text-sm sm:grid-cols-2">
                {options.features.map((f) => (
                  <label key={f.name} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={features.includes(f.name)}
                      onChange={() => toggle(f.name)}
                      className="mt-1"
                    />
                    <span>
                      {f.description} {f.restricted && <Badge tone="bad">restricted</Badge>}
                      {f.recommended_for.includes(term) && (
                        <span className="text-xs text-slate-400"> recommended</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={act.isPending || !when || features.length === 0}
                className="rounded bg-brand px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {act.isPending ? 'Building…' : 'Build'}
              </button>
              <button
                type="button"
                disabled={act.isPending || !when}
                onClick={() =>
                  act.mutate({ action: 'composite', observation: when, window: months })
                }
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
              >
                Combine the deployed scorecards into a composite
              </button>
            </div>
          </form>
        )}
        {act.isError && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {act.error.message}
          </p>
        )}
      </Card>

      <Card title="Scorecards">
        {models.length === 0 ? (
          <Empty>No scorecards yet.</Empty>
        ) : (
          <Table head={['#', 'Term', 'Observed', 'Window', 'AUC', 'Gini', 'KS', 'Status', '']}>
            {models.map((m) => (
              <tr key={m.number}>
                <Td>
                  <Link
                    to={`/games/${gameId}/scorecards/${m.number}`}
                    className="text-brand hover:underline"
                  >
                    {m.number}
                  </Link>
                </Td>
                <Td>
                  {TERM_NAMES[m.term] ?? m.term}{' '}
                  {m.restricted_used.length > 0 && (
                    <Badge tone="bad">uses {m.restricted_used.join(', ')}</Badge>
                  )}
                </Td>
                <Td>{day(m.observation)}</Td>
                <Td right>{m.window_months} months</Td>
                <Td right>{measure(m.holdout, 'auc')}</Td>
                <Td right>{measure(m.holdout, 'gini')}</Td>
                <Td right>{measure(m.holdout, 'ks')}</Td>
                <Td>
                  <Badge tone={m.status === 'DEPLOYED' ? 'good' : 'neutral'}>
                    {m.status.toLowerCase()}
                  </Badge>
                </Td>
                <Td>
                  {m.status !== 'DEPLOYED' && m.term !== 'ALL' && (
                    <button
                      type="button"
                      disabled={act.isPending}
                      onClick={() => act.mutate({ action: 'deploy', number: m.number })}
                      className="text-sm text-brand hover:underline"
                    >
                      Deploy
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="mt-2 text-xs text-slate-500">
          AUC, Gini and KS on the holdout: the 30% of customers each scorecard was not fitted on.
        </p>
      </Card>
    </Page>
  )
}

/** One scorecard: its characteristics, validation, fairness, the truth behind it, monitoring. */
export function ScorecardPage() {
  const gameId = useGameId()
  const number = Number(useParams().number)
  const model = useScorecard(gameId, number)
  if (model.isPending) return <Loading what="the scorecard" />
  if (model.isError) return <Failed error={model.error} />
  const m = model.data
  const r = m.results
  const truth = r.truth
  return (
    <Page
      title={`Scorecard ${m.number}: ${TERM_NAMES[m.term] ?? m.term}`}
      subtitle={`Observed ${day(m.observation)}, default within ${m.window_months} months (90+ days past due). Status: ${m.status.toLowerCase()}.`}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Validation">
          <Table head={['', 'Customers', 'In default', 'AUC', 'Gini', 'KS']}>
            {(['train', 'holdout'] as const)
              .filter((k) => r[k])
              .map((k) => (
                <tr key={k}>
                  <Td>{k === 'train' ? 'Fitted on' : 'Holdout'}</Td>
                  <Td right>{count(r[k]?.customers)}</Td>
                  <Td right>{count(r[k]?.bads)}</Td>
                  <Td right>{measure(r[k], 'auc')}</Td>
                  <Td right>{measure(r[k], 'gini')}</Td>
                  <Td right>{measure(r[k], 'ks')}</Td>
                </tr>
              ))}
          </Table>
        </Card>
        {truth && truth.customers !== undefined && (
          <Card title="The truth behind it">
            <p className="text-sm">
              Against the world's true defaults, the holdout's AUC is{' '}
              <strong>{truth.auc_against_truth?.toFixed(3) ?? '—'}</strong> (against the bureau's
              own labels {truth.auc_against_bureau_labels?.toFixed(3) ?? '—'}).
            </p>
            {truth.labels && (
              <ul className="mt-2 text-sm">
                <li>Defaults the bureau saw that were real: {count(truth.labels.both_default)}</li>
                <li>
                  Defaults on file that were not the customer's (merged files, errors):{' '}
                  {count(truth.labels.bureau_only)}
                </li>
                <li>Real defaults the bureau never saw: {count(truth.labels.truth_only)}</li>
              </ul>
            )}
          </Card>
        )}
        {m.monitoring && (
          <Card title="Monitoring">
            <p className="text-sm">
              Population stability (PSI) at {day(m.monitoring.as_of)}:{' '}
              <strong>{m.monitoring.psi.toFixed(3)}</strong>{' '}
              {m.monitoring.drift ? (
                <Badge tone="bad">drifted</Badge>
              ) : (
                <Badge tone="good">stable</Badge>
              )}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Over 0.25: the people being scored no longer look like those the scorecard was built
              on.
            </p>
            {m.monitoring.since_deployment && (
              <p className="mt-2 text-sm">
                Since it went live ({day(m.monitoring.since_deployment.from)}), by score decile:{' '}
                <strong>{m.monitoring.since_deployment.psi.toFixed(3)}</strong>{' '}
                <Badge
                  tone={
                    m.monitoring.since_deployment.shift === 'major'
                      ? 'bad'
                      : m.monitoring.since_deployment.shift === 'moderate'
                        ? 'warn'
                        : 'good'
                  }
                >
                  {m.monitoring.since_deployment.shift === 'stable'
                    ? 'stable'
                    : `${m.monitoring.since_deployment.shift} shift`}
                </Badge>
                <span className="block text-xs text-slate-500">
                  Over 0.1 a shift worth watching, over 0.25 a major one: the population has changed
                  since launch (an economic shock does this).
                </span>
              </p>
            )}
          </Card>
        )}
      </div>

      {r.characteristics && (
        <Card title="Characteristics">
          {r.characteristics.map((c) => (
            <details key={c.feature} className="border-b border-slate-100 py-1 text-sm">
              <summary className="cursor-pointer">
                {c.description}{' '}
                <span className="text-xs text-slate-500">
                  IV {c.iv.toFixed(3)}
                  {c.iv < 0.02 ? ' (not predictive)' : c.iv > 0.3 ? ' (strong)' : ''}
                </span>
              </summary>
              <Table head={['Up to', 'Goods', 'Bads', 'WoE', 'Points']}>
                {c.bins.map((b, i) => (
                  <tr key={i}>
                    <Td>{b.upper === null ? 'and above' : b.upper}</Td>
                    <Td right>{count(b.goods)}</Td>
                    <Td right>{count(b.bads)}</Td>
                    <Td right>{b.woe.toFixed(3)}</Td>
                    <Td right>{b.points}</Td>
                  </tr>
                ))}
              </Table>
            </details>
          ))}
        </Card>
      )}

      {r.weights && (
        <Card title="Composite weights">
          <Table head={['Term', 'Weight on its score', 'Weight for holding that term']}>
            {r.weights.map((w) => (
              <tr key={w.term}>
                <Td>{TERM_NAMES[w.term]}</Td>
                <Td right>{w.log_odds_weight}</Td>
                <Td right>{w.presence_weight}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {r.score_bands && (
          <Card title="Risk bands">
            <Table head={['Band', 'From', 'Customers', 'In default']}>
              {r.score_bands.map((b) => (
                <tr key={b.band}>
                  <Td>
                    {b.band} {b.label}
                  </Td>
                  <Td right>{b.from}</Td>
                  <Td right>{count(b.customers)}</Td>
                  <Td right>{b.bad_rate === null ? '—' : percent(b.bad_rate)}</Td>
                </tr>
              ))}
            </Table>
          </Card>
        )}
        {r.fairness?.groups && (
          <Card title="Fairness">
            {r.fairness.restricted_used.length > 0 && (
              <p role="alert" className="mb-2 text-sm text-red-700">
                Uses {r.fairness.restricted_used.join(', ')}: an attribute that may not be used to
                decide credit. Deploying it brings a Compliance finding.
              </p>
            )}
            {(r.fairness.proxies?.length ?? 0) > 0 && (
              <p className="mb-2 text-sm text-amber-800">
                Possible stand-ins for gender:{' '}
                {r.fairness.proxies?.map((p) => p.feature).join(', ')}.
              </p>
            )}
            <Table head={['Group', 'Customers', 'Mean score', 'Score 600+', 'In default']}>
              {r.fairness.groups.map((g) => (
                <tr key={g.group}>
                  <Td>{g.group}</Td>
                  <Td right>{count(g.customers)}</Td>
                  <Td right>{g.mean_score}</Td>
                  <Td right>{percent(g.score_600_or_more)}</Td>
                  <Td right>{percent(g.default_rate)}</Td>
                </tr>
              ))}
            </Table>
          </Card>
        )}
      </div>
      <Link to={`/games/${gameId}/scorecards`} className="text-sm text-brand hover:underline">
        Back to the workbench
      </Link>
    </Page>
  )
}
