import { Link, useSearchParams } from 'react-router'

import { useEnquiries } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Empty, Failed, Loading, Page, Table, Td, Shown } from '../components/ui'
import { count, dateTime, day } from '../lib/format'

const PRODUCT: Record<string, string> = {
  CONSUMER_REPORT: 'consumer report',
  BUSINESS_REPORT: 'business report',
  BATCH_ENQUIRY: 'batch',
}

export function EnquiriesPage() {
  const gameId = useGameId()
  const [params] = useSearchParams()
  const filters = {
    start: params.get('start') ?? undefined,
    outcome: params.get('outcome') ?? undefined,
  }
  const rows = useEnquiries(gameId, filters)
  const subtitle = [
    filters.outcome === 'NO_HIT' && 'only "no record found"',
    filters.start && `from ${day(filters.start)}`,
  ]
    .filter(Boolean)
    .join(', ')
  return (
    <Page title="Enquiries" subtitle={subtitle || 'Searches by subscribers, newest first.'}>
      {rows.isPending && <Loading what="enquiries" />}
      {rows.isError && <Failed error={rows.error} />}
      {rows.data?.length === 0 && <Empty>No enquiries.</Empty>}
      {rows.data && <Shown rows={rows.data} />}
      {rows.data && rows.data.length > 0 && (
        <Table
          head={[
            'Reference',
            'When',
            'Subscriber',
            'Product',
            'Purpose',
            'Outcome',
            'Customer',
            'Accounts',
            'Score',
          ]}
        >
          {rows.data.map((e) => (
            <tr key={e.reference}>
              <Td>
                <Link
                  className="font-mono text-brand hover:underline"
                  to={`/games/${gameId}/enquiries/${e.reference}`}
                >
                  {e.reference}
                </Link>
              </Td>
              <Td>{dateTime(e.enquired_at)}</Td>
              <Td>{e.subscriber}</Td>
              <Td>{PRODUCT[e.product] ?? e.product}</Td>
              <Td>{e.purpose.replace('_', ' ').toLowerCase()}</Td>
              <Td>
                <Badge tone={e.outcome === 'HIT' ? 'good' : 'warn'}>
                  {e.outcome === 'HIT' ? 'found' : 'no record'}
                </Badge>
              </Td>
              <Td>
                {e.customer ? (
                  <Link
                    className="text-brand hover:underline"
                    to={`/games/${gameId}/customers/${e.customer}`}
                  >
                    {e.customer}
                  </Link>
                ) : (
                  '—'
                )}
              </Td>
              <Td right>{count(e.accounts_reported)}</Td>
              <Td right>{e.score === null ? '—' : `${e.score} ${e.band}`}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}
