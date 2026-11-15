import { Link } from 'react-router'

import { useDisputes } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, day } from '../lib/format'

const LEVEL_TONE = ['good', 'warn', 'bad', 'bad', 'bad'] as const

/**
 * Disputes and compliance (P2.7): subjects' disputes with their statutory deadlines,
 * and where the bureau stands on the regulator's escalation ladder.
 */
export function DisputesPage() {
  const gameId = useGameId()
  const data = useDisputes(gameId)
  if (data.isPending) return <Loading what="the disputes" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const r = d.regulator
  return (
    <Page
      title="Disputes and compliance"
      subtitle={`A dispute must be settled within ${d.statutory_working_days} working days. Every one left past its deadline is a finding by the regulator.`}
    >
      <Card title="The regulator">
        <div className="space-y-3 text-sm">
          <p>
            Standing: <Badge tone={LEVEL_TONE[r.level]}>{r.standing}</Badge>{' '}
            <span className="text-slate-600">
              ({count(r.findings_recent)} finding(s) in the last six months)
            </span>
          </p>
          <ol className="flex flex-wrap gap-2 text-xs">
            {r.ladder.map((step) => (
              <li
                key={step.level}
                className={`rounded border px-2 py-1 ${
                  r.level >= step.level
                    ? 'border-red-200 bg-red-50 text-red-900'
                    : 'border-slate-200 text-slate-600'
                }`}
              >
                {step.findings}+ findings: {step.what}
              </li>
            ))}
          </ol>
          <p className="text-xs text-slate-500">
            Findings age out after six months, and the bureau steps back down the ladder.
          </p>
          {r.findings.length > 0 && (
            <Table head={['Finding', 'Raised', 'What happened']}>
              {r.findings.map((f) => (
                <tr key={`${f.kind}-${f.reference}`}>
                  <Td>
                    {f.kind === 'MISSED_DISPUTE_DEADLINE' ? 'Missed dispute deadline' : f.kind}
                  </Td>
                  <Td>{dateTime(f.raised_at)}</Td>
                  <Td>{f.detail}</Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </Card>
      <Card title="Disputes">
        {d.disputes.length === 0 ? (
          <Empty>No disputes yet.</Empty>
        ) : (
          <Table head={['#', 'Subject', 'Claim', 'Accounts', 'Received', 'Due', 'Status']}>
            {d.disputes.map((x) => {
              const late = x.status === 'OPEN' && x.overdue
              return (
                <tr key={x.number}>
                  <Td>
                    {x.work_item !== null ? (
                      <Link
                        to={`/games/${gameId}/queue/${x.work_item}`}
                        className="text-brand hover:underline"
                      >
                        {x.number}
                      </Link>
                    ) : (
                      x.number
                    )}
                  </Td>
                  <Td>{x.subject}</Td>
                  <Td>{x.claim}</Td>
                  <Td>{x.accounts.map((a) => a.join(' ')).join(', ')}</Td>
                  <Td>{dateTime(x.received_at)}</Td>
                  <Td>{day(x.due_date)}</Td>
                  <Td>
                    {x.status === 'OPEN' ? (
                      <Badge tone={late ? 'bad' : 'warn'}>{late ? 'overdue' : 'open'}</Badge>
                    ) : (
                      <Badge tone={x.outcome === 'UPHELD' ? 'good' : 'neutral'}>
                        {x.outcome.toLowerCase()}
                      </Badge>
                    )}
                    {x.corrections > 0 && (
                      <span className="ml-1 text-xs text-slate-500">
                        {x.corrections} correction(s)
                      </span>
                    )}
                  </Td>
                </tr>
              )
            })}
          </Table>
        )}
      </Card>
    </Page>
  )
}
