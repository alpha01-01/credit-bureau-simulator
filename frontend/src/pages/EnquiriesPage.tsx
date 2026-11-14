import { Link, useSearchParams } from 'react-router'

import { useEnquiries } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, day } from '../lib/format'

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
      {rows.data && rows.data.length > 0 && (
        <Table
          head={['Reference', 'When', 'Subscriber', 'Purpose', 'Outcome', 'Customer', 'Accounts']}
        >
          {rows.data.map((e) => (
            <tr key={e.reference}>
              <Td>{e.reference}</Td>
              <Td>{dateTime(e.enquired_at)}</Td>
              <Td>{e.subscriber}</Td>
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
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}
