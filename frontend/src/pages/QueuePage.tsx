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

/** A template date (YYYYMMDD) or an ISO date as DD/MM/YYYY; anything else unchanged. */
function day(value: string | null | undefined) {
  const m = value?.match(/^(\d{4})-?(\d{2})-?(\d{2})$/)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : value
}

function MatchEvidence({ item }: { item: WorkItemDetail }) {
  const r = item.record
  const individual = 'FirstName' in r
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Submitted record">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          {individual ? (
            <>
              <Field
                label="Name"
                value={[r.FirstName, r.MiddleNames, r.Surname].filter(Boolean).join(' ')}
              />
              <Field label="Date of birth" value={day(r.DOB)} />
              <Field label="Gender" value={r.Gender} />
              <Field
                label="Ghana Card"
                value={r.NatIDNum}
                highlight={item.evidence.identifier_field === 'NatIDNum'}
              />
              {r.VotersIDNum && (
                <Field
                  label="Voter's ID"
                  value={r.VotersIDNum}
                  highlight={item.evidence.identifier_field === 'VotersIDNum'}
                />
              )}
              {r.PassportNum && (
                <Field
                  label="Passport"
                  value={r.PassportNum}
                  highlight={item.evidence.identifier_field === 'PassportNum'}
                />
              )}
              {r.SSNum && (
                <Field
                  label="SSNIT"
                  value={r.SSNum}
                  highlight={item.evidence.identifier_field === 'SSNum'}
                />
              )}
              <Field label="Mobile" value={r.MobileTel1} />
              <Field label="Employer" value={r.EmpName} />
            </>
          ) : (
            <>
              <Field label="Name" value={r.BusinessName} />
              <Field
                label="Registration no."
                value={r.BusRegNum}
                highlight={item.evidence.identifier_field === 'BusRegNum'}
              />
              <Field
                label="TIN"
                value={r.TINum}
                highlight={item.evidence.identifier_field === 'TINum'}
              />
              <Field label="Registered" value={day(r.RegistrationDate)} />
            </>
          )}
          <Field label="Provider" value={`${item.provider.name}, customer ${r.CustomerID}`} />
          <Field label="Account" value={r.FacilityAccNum} />
        </dl>
      </Card>
      <Card title="Bureau customer holding that identifier">
        {item.candidate ? (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <Field label="Reference" value={item.candidate.reference} />
            <Field label="Name" value={item.candidate.name} />
            {item.candidate.registration_date ? (
              <Field label="Registered" value={day(item.candidate.registration_date)} />
            ) : (
              <Field label="Date of birth" value={day(item.candidate.date_of_birth)} />
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
  const r = item.record
  const prev = item.on_file
  return (
    <div className="grid gap-4">
      <Card title="Why the record was not loaded">
        <Table head={['Rule', 'Field', 'Submitted', 'Proposed correction']}>
          {item.evidence.errors?.map((e) => (
            <tr key={`${e.rule}-${e.field}`}>
              <Td>{e.rule}</Td>
              <Td>{e.field}</Td>
              <Td>
                <code>{e.value || r[e.field]}</code>
              </Td>
              <Td>
                <code>{e.field in item.proposal ? item.proposal[e.field] || '(blank)' : '—'}</code>
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={`Submitted by ${item.provider.name}`}>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <Field label="Account" value={r.FacilityAccNum} />
            <Field label="Status" value={r.FacilityStatusCode} highlight />
            <Field label="Balance" value={r.CurBal} />
            <Field label="Arrears" value={`${r.AmountInArrears || '0'} (${r.NDIA || '0'} days)`} />
            <Field label="Disbursed" value={`${day(r.DisbursementDate)}, ${r.DisbursementAmt}`} />
            <Field label="Matures" value={day(r.MaturityDate)} />
            <Field label="Instalment" value={r.SchdInstalAmount} />
            <Field
              label="Last payment"
              value={r.LastPaymentDate ? `${r.LastPaymentAmount} on ${day(r.LastPaymentDate)}` : ''}
            />
            <Field
              label="Closed"
              value={r.ClosedDate ? `${day(r.ClosedDate)} (reason ${r.ClosureReason || '?'})` : ''}
            />
          </dl>
        </Card>
        <Card title="Bureau's last position">
          {prev ? (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
              <Field label="As at" value={day(prev.reporting_date)} />
              <Field label="Status" value={prev.status} />
              <Field label="Balance" value={prev.balance} />
              <Field label="Arrears" value={`${prev.arrears} (${prev.days_past_due} days)`} />
              <Field label="Disbursed" value={day(prev.disbursement_date)} />
            </dl>
          ) : (
            <Empty>The bureau holds no earlier position for this account.</Empty>
          )}
        </Card>
      </div>
    </div>
  )
}
