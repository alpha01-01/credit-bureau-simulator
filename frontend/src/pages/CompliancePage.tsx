import { useState } from 'react'
import { Link } from 'react-router'

import { useCompliance } from '../api/compliance'
import { useGameCommand } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { day, dateTime } from '../lib/format'
import { KIND_LABEL } from '../lib/findings'

const LEVEL_TONE = ['good', 'warn', 'bad', 'bad', 'bad', 'bad'] as const

const BUTTON =
  'rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

/**
 * Compliance (P3.7): the rules the bureau keeps and what they cite; the monthly return;
 * consent sampling and sanctions; retention; staff access; and the findings to put right.
 */
export function CompliancePage() {
  const gameId = useGameId()
  const data = useCompliance(gameId)
  const act = useGameCommand(gameId, '/compliance/')
  const [subscriber, setSubscriber] = useState('')
  const [month, setMonth] = useState('')
  const [size, setSize] = useState(25)
  if (data.isPending) return <Loading what="compliance" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const code = subscriber || d.subscribers[0]?.code || ''
  const sampleMonth = month || d.sample_months[0] || ''
  const open = d.findings.filter((f) => !f.resolved)

  return (
    <Page
      title="Compliance"
      subtitle="The rules the bureau keeps, and the duties that go with them. A finding not put right by its date goes to the regulator."
    >
      {act.error && <Failed error={act.error} />}

      <Card title="Standing with the regulator">
        <p className="text-sm">
          <Badge tone={LEVEL_TONE[d.regulator.level]}>{d.regulator.standing}</Badge>{' '}
          <Link to={`/games/${gameId}/disputes`} className="text-brand hover:underline">
            The ladder and disputes
          </Link>
        </p>
        {d.regulator.findings.length > 0 && (
          <Table head={['Regulator finding', 'Raised', 'What happened']}>
            {d.regulator.findings.map((f) => (
              <tr key={`${f.kind}-${f.reference}`}>
                <Td>{KIND_LABEL[f.kind] ?? f.kind}</Td>
                <Td>{dateTime(f.raised_at)}</Td>
                <Td>{f.detail}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title={`Findings to put right (${open.length} open)`}>
        {d.findings.length === 0 ? (
          <Empty>No compliance findings.</Empty>
        ) : (
          <Table head={['#', 'Finding', 'What to do', 'By', 'Status']}>
            {d.findings.map((f) => (
              <tr key={f.number}>
                <Td>{f.number}</Td>
                <Td>
                  <span className="font-medium">{KIND_LABEL[f.kind] ?? f.kind}</span>{' '}
                  <span className="text-slate-600">{f.detail}</span>
                </Td>
                <Td>{f.remedy ?? '—'}</Td>
                <Td>{day(f.due_date)}</Td>
                <Td>
                  {f.resolved ? (
                    <Badge tone="good">put right</Badge>
                  ) : f.escalated ? (
                    <Badge tone="bad">reported to the regulator</Badge>
                  ) : (
                    <Badge tone="warn">open</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Monthly return to the Bank of Ghana">
        {d.returns.length === 0 ? (
          <Empty>No return owed yet: the first is owed at the next month&apos;s start.</Empty>
        ) : (
          <Table head={['Month', 'Due', 'Filed', 'Figures']}>
            {d.returns.map((r) => (
              <tr key={r.period}>
                <Td>{r.period.slice(0, 7)}</Td>
                <Td>{day(r.due_date)}</Td>
                <Td>
                  {r.filed_at ? (
                    <>
                      {dateTime(r.filed_at)} by {r.filed_by}{' '}
                      {r.late && <Badge tone="bad">late</Badge>}
                    </>
                  ) : r.work_item !== null ? (
                    <Link
                      to={`/games/${gameId}/queue/${r.work_item}`}
                      className="text-brand hover:underline"
                    >
                      {r.late ? 'Overdue: file it now' : 'File it'}
                    </Link>
                  ) : (
                    'not filed'
                  )}
                </Td>
                <Td>
                  {Object.keys(r.figures).length
                    ? `${r.figures.customers?.toLocaleString()} customers, ${r.figures.accounts?.toLocaleString()} accounts, ${r.figures.enquiries?.toLocaleString()} enquiries`
                    : '—'}
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="mt-2 text-xs text-slate-500">
          Staff file the return from the work queue when they reach it; you can file it yourself.
        </p>
      </Card>

      <Card title="Consent: sample a subscriber's enquiries">
        <p className="mb-2 text-sm text-slate-600">
          Ask a lender for the signed application forms behind some of its enquiries. It answers in
          three working days. Compliance then reads them, {d.officer.forms_per_day} forms a working
          day; forms the lender could not send are a finding.
        </p>
        <p className="mb-2 text-sm" data-testid="compliance-day">
          {d.officer.busy_today
            ? `Today Compliance is on ${d.officer.busy_with}. `
            : 'Compliance is free today for the checks on new subscribers. '}
          {d.officer.days_queued > 0 &&
            `${d.officer.days_queued} working day${d.officer.days_queued === 1 ? '' : 's'} of reviews queued: each holds up the checks on new subscribers by a day.`}
        </p>
        <form
          className="flex flex-wrap items-end gap-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            act.mutate({ action: 'sample', subscriber: code, month: sampleMonth, size })
          }}
        >
          <label className="flex flex-col">
            Subscriber
            <select
              value={code}
              onChange={(e) => setSubscriber(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {d.subscribers.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name} ({s.code}){s.suspended ? ' — suspended' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col">
            Enquiries made in
            <select
              value={sampleMonth}
              onChange={(e) => setMonth(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {d.sample_months.map((m) => (
                <option key={m} value={m}>
                  {m.slice(0, 7)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col">
            Sample size
            <select
              value={size}
              onChange={(e) => setSize(Number(e.target.value))}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {d.sample_sizes.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={act.isPending || !code} className={BUTTON}>
            Ask for the forms
          </button>
        </form>
        {d.consent_checks.length > 0 && (
          <div className="mt-3">
            <Table head={['#', 'Subscriber', 'Month', 'Asked', 'Answer', 'Act']}>
              {d.consent_checks.map((c) => (
                <tr key={c.number}>
                  <Td>{c.number}</Td>
                  <Td>{c.subscriber}</Td>
                  <Td>{c.month.slice(0, 7)}</Td>
                  <Td>{c.size}</Td>
                  <Td>
                    {!c.answered ? (
                      <Badge tone="neutral">awaited</Badge>
                    ) : !c.reviewed ? (
                      <Badge tone="neutral">
                        forms in; {c.review_days_left} day{c.review_days_left === 1 ? '' : 's'} to
                        read
                      </Badge>
                    ) : c.missing.length === 0 ? (
                      <Badge tone="good">all shown</Badge>
                    ) : (
                      <Badge tone="bad">{c.missing.length} without consent</Badge>
                    )}
                  </Td>
                  <Td>
                    {c.reviewed && c.missing.length > 0 && (
                      <span className="flex gap-2">
                        {(['WARNING', 'SUSPENSION'] as const).map((kind) => (
                          <button
                            key={kind}
                            type="button"
                            disabled={act.isPending}
                            className={BUTTON}
                            onClick={() =>
                              act.mutate({ action: 'sanction', subscriber: c.subscriber, kind })
                            }
                          >
                            {kind === 'WARNING' ? 'Warn' : 'Suspend for a month'}
                          </button>
                        ))}
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          </div>
        )}
        {d.sanctions.length > 0 && (
          <p className="mt-2 text-xs text-slate-600">
            Sanctions:{' '}
            {d.sanctions
              .map(
                (s) =>
                  `${s.subscriber} ${s.kind === 'WARNING' ? 'warned' : 'suspended'}${s.active ? ' (in force)' : ''}`,
              )
              .join('; ')}
          </p>
        )}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Retention">
          <p className="mb-2 text-sm text-slate-600">
            Reports keep a closed account for this long after it was last reported. The law allows
            at most {d.retention.legal_years} years.
          </p>
          <div className="flex flex-wrap gap-2">
            {d.retention.choices.map((y) => (
              <button
                key={y}
                type="button"
                disabled={act.isPending || y === d.retention.years}
                onClick={() => act.mutate({ action: 'retention', years: y })}
                className={`rounded border px-3 py-1.5 text-sm ${
                  y === d.retention.years
                    ? 'border-brand bg-brand text-white'
                    : y > d.retention.legal_years
                      ? 'border-red-300 text-red-800 hover:bg-red-50'
                      : 'border-slate-300 hover:bg-slate-50'
                }`}
              >
                {y} years
              </button>
            ))}
          </div>
        </Card>
        <Card title="Access to the bureau's data">
          <p className="text-sm">
            {d.access.staff} staff hold access.{' '}
            {d.access.leavers_with_access.length > 0 ? (
              <span className="text-red-800">
                Leavers still holding it: {d.access.leavers_with_access.join(', ')}.
              </span>
            ) : (
              'No leaver holds access.'
            )}
          </p>
          <button
            type="button"
            disabled={act.isPending || d.access.review_requested}
            onClick={() => act.mutate({ action: 'access_review' })}
            className={`mt-2 ${BUTTON}`}
          >
            {d.access.review_requested ? 'Review asked for' : 'Review access'}
          </button>
          <p className="mt-2 text-xs text-slate-500">
            Due each quarter. Compliance does it on its next working day, before anything else.
          </p>
        </Card>
      </div>

      <Card title="The rules">
        <ul className="space-y-3 text-sm">
          {d.rules.map((r) => (
            <li key={r.code}>
              <p className="font-medium">
                {r.title}{' '}
                {r.status === 'TO_CONFIRM' && <Badge tone="warn">citation to confirm</Badge>}
              </p>
              <p>{r.rule}</p>
              <p className="text-xs text-slate-500">{r.citation}</p>
            </li>
          ))}
        </ul>
      </Card>
    </Page>
  )
}
