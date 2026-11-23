import { Link, useSearchParams } from 'react-router'

import { useAccounts } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Coded, Empty, Failed, Loading, Page, Shown, Table, Td } from '../components/ui'
import { day, money } from '../lib/format'

/** Credit accounts on file; the dashboard's "Open accounts" figure drills here. */
export function AccountsPage() {
  const gameId = useGameId()
  const [params] = useSearchParams()
  const status = params.get('status') ?? undefined
  const rows = useAccounts(gameId, status)
  return (
    <Page
      title={status === 'open' ? 'Open accounts' : 'Accounts'}
      subtitle="Each account as its provider last reported it, with the customer it belongs to."
    >
      {rows.isPending && <Loading what="accounts" />}
      {rows.isError && <Failed error={rows.error} />}
      {rows.data?.length === 0 && <Empty>No accounts.</Empty>}
      {rows.data && <Shown rows={rows.data} />}
      {rows.data && rows.data.length > 0 && (
        <Table head={['Provider', 'Account', 'Customer', 'Type', 'Opened', 'Amount', 'Status']}>
          {rows.data.map((a) => (
            <tr key={`${a.provider}-${a.account}`}>
              <Td>{a.provider}</Td>
              <Td>{a.account}</Td>
              <Td>
                <Link
                  to={`/games/${gameId}/customers/${a.customer}`}
                  className="text-brand hover:underline"
                >
                  {a.customer}
                </Link>
              </Td>
              <Td>
                <Coded name={a.facility_type_name} code={a.facility_type} />
              </Td>
              <Td>{day(a.opened)}</Td>
              <Td right>{money(a.amount)}</Td>
              <Td>
                <Coded name={a.status_name} code={a.status} />
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}
