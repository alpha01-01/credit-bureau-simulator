import { Link, useParams, useSearchParams } from 'react-router'

import {
  useGameCommand,
  useRejectionPolicy,
  useSubmission,
  useSubmissions,
  type RejectionPolicy,
} from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, day } from '../lib/format'

/** The bureau's rejection policy: how strictly incoming records are rejected (D18). */
function PolicyControl({ gameId }: { gameId: number }) {
  const policy = useRejectionPolicy(gameId)
  const change = useGameCommand<RejectionPolicy>(gameId, '/rejection-policy/')
  if (!policy.data) return null
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
      <span className="font-medium">Rejection policy</span>
      {policy.data.options.map((o) => (
        <label key={o.code} className="flex items-center gap-1" title={o.description}>
          <input
            type="radio"
            value={o.code}
            name="rejection-policy"
            checked={policy.data.policy === o.code}
            disabled={change.isPending}
            onChange={() => change.mutate({ policy: o.code })}
          />
          {o.code === 'STANDARD' ? 'Standard' : 'Core fields only'}
        </label>
      ))}
      <span className="text-slate-500">
        {policy.data.options.find((o) => o.code === policy.data.policy)?.description}. Applies to
        files processed from now on.
      </span>
      {change.isError && <span className="text-red-700">{String(change.error)}</span>}
    </div>
  )
}

export function SubmissionsPage() {
  const gameId = useGameId()
  const [params] = useSearchParams()
  const filters = {
    provider: params.get('provider') ?? undefined,
    start: params.get('start') ?? undefined,
  }
  const rows = useSubmissions(gameId, filters)
  return (
    <Page
      title="Submissions register"
      subtitle={
        filters.provider || filters.start
          ? `Filtered: ${[filters.provider, filters.start && `from ${day(filters.start)}`].filter(Boolean).join(', ')}`
          : 'Every file providers have sent, newest first.'
      }
    >
      <PolicyControl gameId={gameId} />
      {rows.isPending && <Loading what="submissions" />}
      {rows.isError && <Failed error={rows.error} />}
      {rows.data?.length === 0 && <Empty>No submissions.</Empty>}
      {rows.data && rows.data.length > 0 && (
        <Table
          head={[
            'Reference',
            'Provider',
            'Period',
            'Received',
            'Status',
            'Received',
            'Loaded',
            'Unloadable',
            'Duplicates',
            'Held',
          ]}
        >
          {rows.data.map((s) => (
            <tr key={s.reference} className="hover:bg-slate-50">
              <Td>
                <Link
                  className="font-medium text-brand hover:underline"
                  to={`/games/${gameId}/submissions/${s.reference}`}
                >
                  {s.reference}
                </Link>
              </Td>
              <Td>{s.provider_name}</Td>
              <Td>{day(s.period)}</Td>
              <Td>
                {dateTime(s.received_at)} {s.late && <Badge tone="warn">late</Badge>}
              </Td>
              <Td>
                <Badge
                  tone={
                    s.status === 'PROCESSED' ? 'good' : s.status === 'REJECTED' ? 'bad' : 'info'
                  }
                >
                  {s.status}
                </Badge>
              </Td>
              <Td right>{count(s.received)}</Td>
              <Td right>{count(s.accepted)}</Td>
              <Td right>{count(s.unloadable)}</Td>
              <Td right>{count(s.duplicates)}</Td>
              <Td right>{count(s.pending)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}

export function SubmissionPage() {
  const gameId = useGameId()
  const { reference = '' } = useParams()
  const detail = useSubmission(gameId, reference)
  if (detail.isPending) return <Loading what="the submission" />
  if (detail.isError) return <Failed error={detail.error} />
  const s = detail.data
  return (
    <Page
      title={s.reference}
      subtitle={`${s.provider}, ${day(s.period)} data, received ${dateTime(s.received_at)} (due ${day(s.due_date)})`}
    >
      <Card title="Files">
        <Table head={['File', 'Type', 'Size', 'SHA-256', 'Status']}>
          {s.files.map((f) => (
            <tr key={f.name}>
              <Td>{f.name}</Td>
              <Td>
                {f.kind} / {f.format}
              </Td>
              <Td right>{count(f.size)} bytes</Td>
              <Td>
                <code className="text-xs">{f.sha256.slice(0, 16)}…</code>
              </Td>
              <Td>
                <Badge tone={f.status === 'REJECTED' ? 'bad' : 'good'}>{f.status}</Badge>{' '}
                {f.rejection_reason}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      {s.runs.map((run) => (
        <Card key={run.run_number} title={`Processing run ${run.run_number}`}>
          <p className="mb-3 text-sm text-slate-600">
            {count(run.received)} received = {count(run.accepted)} loaded + {count(run.unloadable)}{' '}
            unloadable + {count(run.duplicates)} duplicates + {count(run.pending)} held for review{' '}
            <Badge tone={run.reconciles ? 'good' : 'bad'}>
              {run.reconciles ? 'reconciles' : 'does not reconcile'}
            </Badge>
            . New customers {count(run.customers_created)}, new accounts{' '}
            {count(run.accounts_created)}.
          </p>
          {run.issues.length > 0 && (
            <Table head={['Rule', 'Severity', 'What', 'Count']}>
              {run.issues.map((i) => (
                <tr key={`${i.rule_code}-${i.severity}`}>
                  <Td>{i.rule_code}</Td>
                  <Td>
                    <Badge tone={i.severity === 'ERROR' ? 'bad' : 'warn'}>{i.severity}</Badge>
                  </Td>
                  <Td>{i.message}</Td>
                  <Td right>{count(i.count)}</Td>
                </tr>
              ))}
            </Table>
          )}
          {run.examples.length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-brand">Example errors (first 50)</summary>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {run.examples.map((e, i) => (
                  <li key={i}>
                    {e.file} row {e.row}: {e.rule} {e.field} {e.value && `"${e.value}"`}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Card>
      ))}
    </Page>
  )
}
