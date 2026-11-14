import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import {
  type WorkItemDetail,
  useEmployees,
  useGameCommand,
  useWorkItem,
  useWorkItems,
} from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, percent } from '../lib/format'

const TYPE_LABEL: Record<string, string> = {
  MATCH_REVIEW: 'Match review',
  UNLOADABLE_TRIAGE: 'Unloadable triage',
}

const BY_LABEL: Record<string, string> = {
  EMPLOYEE: 'staff',
  PLAYER: 'you',
  HISTORIC: 'former staff',
}

const DECISION_LABEL: Record<string, string> = {
  SAME_CUSTOMER: 'Same customer: link',
  DIFFERENT_CUSTOMER: 'Different customer: create new',
  CORRECT_AND_LOAD: 'Apply correction and load',
  RETURN_TO_PROVIDER: 'Return to provider',
}

export function QueuePage() {
  const gameId = useGameId()
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'OPEN'
  const items = useWorkItems(gameId, status)
  const staff = useEmployees(gameId)
  return (
    <Page
      title="Data Operations work queue"
      subtitle="Records the pipeline could not settle on its own."
    >
      <Card title="Team">
        {staff.data && (
          <Table head={['Employee', 'Role', 'Match skill', 'Triage skill', 'Done today', 'Morale']}>
            {staff.data.map((e) => (
              <tr key={e.number}>
                <Td>{e.name}</Td>
                <Td>{e.job_title}</Td>
                <Td right>{percent(e.skills.MATCH_REVIEW)}</Td>
                <Td right>{percent(e.skills.UNLOADABLE_TRIAGE)}</Td>
                <Td right>{count(e.done_today)}</Td>
                <Td right>{percent(e.morale)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <div role="tablist" aria-label="Item status" className="flex gap-1">
        {['OPEN', 'IN_PROGRESS', 'DONE'].map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={s === status}
            onClick={() => setParams({ status: s })}
            className={`rounded px-2.5 py-1 text-sm ${s === status ? 'bg-brand text-white' : 'bg-white text-slate-600'}`}
          >
            {s === 'OPEN' ? 'Waiting' : s === 'IN_PROGRESS' ? 'Being worked' : 'Done'}
          </button>
        ))}
      </div>
      {items.isPending && <Loading what="work items" />}
      {items.isError && <Failed error={items.error} />}
      {items.data?.length === 0 && <Empty>Nothing here.</Empty>}
      {items.data && items.data.length > 0 && (
        <Table head={['Item', 'Type', 'Difficulty', 'Assigned to', 'Decision', 'By']}>
          {items.data.map((i) => (
            <tr key={i.number} className="hover:bg-slate-50">
              <Td>
                <Link
                  className="font-medium text-brand hover:underline"
                  to={`/games/${gameId}/queue/${i.number}`}
                >
                  #{i.number}
                </Link>
              </Td>
              <Td>{TYPE_LABEL[i.type]}</Td>
              <Td right>{percent(i.difficulty)}</Td>
              <Td>{i.assignee ?? '—'}</Td>
              <Td>{i.decision ? DECISION_LABEL[i.decision] : '—'}</Td>
              <Td>{i.resolved_by ? BY_LABEL[i.resolved_by] : '—'}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}

export function WorkItemPage() {
  const gameId = useGameId()
  const navigate = useNavigate()
  const number = Number(useParams().number)
  const item = useWorkItem(gameId, number)
  const resolve = useGameCommand(gameId, `/work-items/${number}/resolve/`)
  if (item.isPending) return <Loading what="the item" />
  if (item.isError) return <Failed error={item.error} />
  const i = item.data
  const open = i.status !== 'DONE'
  return (
    <Page
      title={`${TYPE_LABEL[i.type]} #${i.number}`}
      subtitle={`Difficulty ${percent(i.difficulty)}`}
    >
      {i.type === 'MATCH_REVIEW' ? <MatchEvidence item={i} /> : <TriageEvidence item={i} />}
      {i.explanation && (
        <Card title="Decision recorded">
          <p className="text-sm">{i.explanation}</p>
        </Card>
      )}
      {open && (
        <Card title="Your decision">
          <div className="flex flex-wrap gap-2">
            {i.allowed_decisions.map((d) => (
              <button
                key={d}
                type="button"
                disabled={resolve.isPending}
                onClick={() =>
                  resolve.mutate(
                    { decision: d },
                    { onSuccess: () => navigate(`/games/${gameId}/queue`) },
                  )
                }
                className="rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50"
              >
                {DECISION_LABEL[d]}
              </button>
            ))}
          </div>
          {resolve.error && <Failed error={resolve.error} />}
          <p className="mt-2 text-xs text-slate-500">
            Decisions are applied as given. You will learn whether you were right from what happens
            next.
          </p>
        </Card>
      )}
    </Page>
  )
}

function Field({
  label,
  value,
  highlight,
}: {
  label: string
  value: string | null | undefined
  highlight?: boolean
}) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className={highlight ? 'font-semibold text-amber-800' : ''}>{value || '—'}</dd>
    </>
  )
}

function MatchEvidence({ item }: { item: WorkItemDetail }) {
  const r = item.record
  const individual = 'FIRST_NAME' in r
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Submitted record">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          {individual ? (
            <>
              <Field label="Name" value={`${r.FIRST_NAME} ${r.MIDDLE_NAMES} ${r.SURNAME}`} />
              <Field label="Date of birth" value={r.DATE_OF_BIRTH} />
              <Field label="Gender" value={r.GENDER} />
              <Field label="Ghana Card" value={r.GHANA_CARD_NUMBER} highlight />
              <Field label="Mobile" value={r.MOBILE_NUMBER} />
            </>
          ) : (
            <>
              <Field label="Name" value={r.REGISTERED_NAME} />
              <Field label="Registration no." value={r.REGISTRATION_NUMBER} highlight />
              <Field label="TIN" value={r.TIN} />
              <Field label="Registered" value={r.REGISTRATION_DATE} />
            </>
          )}
          <Field label="Provider" value={`${r.PROVIDER_CODE} customer ${r.CUSTOMER_NUMBER}`} />
          <Field label="Account" value={r.ACCOUNT_NUMBER} />
        </dl>
      </Card>
      <Card title="Bureau customer holding that identifier">
        {item.candidate ? (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <Field label="Reference" value={item.candidate.reference} />
            <Field label="Name" value={item.candidate.name} />
            {item.candidate.registration_date ? (
              <Field label="Registered" value={item.candidate.registration_date} />
            ) : (
              <Field label="Date of birth" value={item.candidate.date_of_birth} />
            )}
          </dl>
        ) : (
          <Empty>No candidate.</Empty>
        )}
        <p className="mt-3 text-sm">
          Similarity <Badge tone="info">{item.score?.toFixed(2)}</Badge>{' '}
          {item.evidence.reasons?.join('; ')}
        </p>
      </Card>
    </div>
  )
}

function TriageEvidence({ item }: { item: WorkItemDetail }) {
  return (
    <Card title="Why the record was not loaded">
      <Table head={['Rule', 'Field', 'Submitted', 'Proposed correction']}>
        {item.evidence.errors?.map((e) => (
          <tr key={`${e.rule}-${e.field}`}>
            <Td>{e.rule}</Td>
            <Td>{e.field}</Td>
            <Td>
              <code>{e.value || item.record[e.field]}</code>
            </Td>
            <Td>
              <code>{item.proposal[e.field] ?? '—'}</code>
            </Td>
          </tr>
        ))}
      </Table>
      <p className="mt-2 text-xs text-slate-500">
        Account {item.record.ACCOUNT_NUMBER}: balance {item.record.CURRENT_BALANCE}, status{' '}
        {item.record.ACCOUNT_STATUS}, {item.record.DAYS_PAST_DUE} days past due.
      </p>
    </Card>
  )
}
