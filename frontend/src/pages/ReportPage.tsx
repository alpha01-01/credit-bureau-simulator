import { useParams } from 'react-router'

import { useReport } from '../api/reports'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { day, money } from '../lib/format'

/** A report as it was delivered to the subscriber: consumer (SIMB-R1) or business (SIMB-B1). */
export function ReportPage() {
  const gameId = useGameId()
  const { reference = '' } = useParams()
  const data = useReport(gameId, reference)
  if (data.isPending) return <Loading what="the report" />
  if (data.isError) return <Failed error={data.error} />
  const r = data.data.report
  if (!r.subject) {
    return (
      <Page title={`Enquiry ${reference}`}>
        <Card>
          <Empty>No record was found: no report was delivered.</Empty>
        </Card>
      </Page>
    )
  }
  const business = r.layout === 'SIMB-B1'
  const accounts = r.facilities ?? r.accounts ?? []
  const s = r.subject
  return (
    <Page
      title={business ? 'Business credit report' : 'Consumer credit report'}
      subtitle={`Enquiry ${reference} · layout ${r.layout} · as of ${day(r.as_of)}`}
    >
      <Card title="Subject">
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <dt className="text-slate-500">Name</dt>
          <dd>{s.registered_name ?? s.name}</dd>
          {business ? (
            <>
              <dt className="text-slate-500">Trading as</dt>
              <dd>{s.trading_name ?? '—'}</dd>
              <dt className="text-slate-500">Registration number</dt>
              <dd className="font-mono">{s.registration_number ?? '—'}</dd>
              <dt className="text-slate-500">TIN</dt>
              <dd className="font-mono">{s.tin ?? '—'}</dd>
              <dt className="text-slate-500">Registered</dt>
              <dd>{day(s.registration_date)}</dd>
              <dt className="text-slate-500">Sector</dt>
              <dd>{s.sector || '—'}</dd>
            </>
          ) : (
            <>
              <dt className="text-slate-500">Date of birth</dt>
              <dd>{day(s.date_of_birth)}</dd>
            </>
          )}
          <dt className="text-slate-500">Bureau reference</dt>
          <dd className="font-mono">{s.reference}</dd>
        </dl>
      </Card>
      {r.summary && (
        <Card title="Summary">
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
            {Object.entries(r.summary).map(([k, v]) => (
              <div key={k}>
                <dt className="text-slate-500">{k.replaceAll('_', ' ')}</dt>
                <dd>{k.includes('outstanding') ? money(String(v)) : v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}
      <Card title={business ? 'Facilities' : 'Accounts'}>
        {accounts.length === 0 ? (
          <Empty>None on file.</Empty>
        ) : (
          <Table head={['Lender', 'Account', 'Type', 'Opened', 'Amount', 'Balance', 'Status']}>
            {accounts.map((a) => (
              <tr key={`${a.lender}-${a.account}`}>
                <Td>{a.lender}</Td>
                <Td>
                  <span className="font-mono">{a.account}</span>{' '}
                  {a.disputed && <Badge tone="warn">disputed</Badge>}
                </Td>
                <Td>{a.facility_type}</Td>
                <Td>{day(a.opened)}</Td>
                <Td right>{money(a.original_amount)}</Td>
                <Td right>{money(a.balance)}</Td>
                <Td>
                  {a.status}
                  {(a.days_past_due ?? 0) > 0 && ` · ${a.days_past_due} days past due`}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Dishonoured cheques">
        {(r.dishonoured_cheques ?? []).length === 0 ? (
          <Empty>None on file.</Empty>
        ) : (
          <Table head={['Bank', 'Account', 'Cheque', 'Returned', 'Reason', 'Amount']}>
            {(r.dishonoured_cheques ?? []).map((c) => (
              <tr key={`${c.account_number}-${c.cheque_number}`}>
                <Td>{c.lender}</Td>
                <Td>{c.account_number}</Td>
                <Td>{c.cheque_number}</Td>
                <Td>{day(c.date_bounced)}</Td>
                <Td>{c.reason}</Td>
                <Td right>{money(c.amount)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Court judgments">
        {(r.judgments ?? []).length === 0 ? (
          <Empty>None on file.</Empty>
        ) : (
          <Table head={['Plaintiff', 'Court', 'Case', 'Filed', 'Type', 'Reason', 'Amount']}>
            {(r.judgments ?? []).map((j) => (
              <tr key={j.case_number}>
                <Td>{j.plaintiff}</Td>
                <Td>{j.court}</Td>
                <Td>{j.case_number}</Td>
                <Td>{day(j.filing_date)}</Td>
                <Td>{j.case_type}</Td>
                <Td>{j.case_reason}</Td>
                <Td right>{money(j.amount)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  )
}
