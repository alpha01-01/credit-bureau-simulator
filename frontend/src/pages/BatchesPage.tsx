import { useState } from 'react'
import { Link } from 'react-router'

import { useBatches } from '../api/reports'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { dateTime, money } from '../lib/format'

/**
 * Batch enquiries (P3.11): subscribers' files of applicants, each record searched as a
 * single enquiry would be, with a result file sent back.
 */
export function BatchesPage() {
  const gameId = useGameId()
  const [chosen, setChosen] = useState<string | null>(null)
  const data = useBatches(gameId, chosen)
  if (data.isPending) return <Loading what="batch files" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  return (
    <Page
      title="Batch enquiries"
      subtitle={
        d.launched
          ? `Subscribers send files of applicants; each record is searched as a single enquiry and billed at ${money(d.price)}.`
          : 'Batch enquiries have not been developed yet (Products).'
      }
    >
      <Card title="Files received">
        {d.batches.length === 0 ? (
          <Empty>No batch files yet.</Empty>
        ) : (
          <Table head={['File', 'Subscriber', 'Received', 'Records', 'Found', '']}>
            {d.batches.map((b) => (
              <tr key={b.reference}>
                <Td>
                  <span className="font-mono">{b.reference}</span>
                </Td>
                <Td>{b.name}</Td>
                <Td>{dateTime(b.received_at)}</Td>
                <Td right>{b.records}</Td>
                <Td right>{b.hits}</Td>
                <Td>
                  <button
                    type="button"
                    className="rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50"
                    onClick={() => setChosen(b.reference)}
                  >
                    Open
                  </button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {d.batch && (
        <Card title={`File ${d.batch.reference}`}>
          <a
            className="text-sm text-brand underline"
            download={`${d.batch.reference}-result.csv`}
            href={`data:text/csv;charset=utf-8,${encodeURIComponent(d.batch.result_file)}`}
          >
            Download the result file
          </a>
          <Table head={['Row', 'Ghana Card', 'Name', 'Outcome', 'Report', 'Accounts']}>
            {d.batch.rows.map((r) => (
              <tr key={r.row}>
                <Td>{r.row}</Td>
                <Td>
                  <span className="font-mono">{r.identifier}</span>
                </Td>
                <Td>{r.name}</Td>
                <Td>
                  <Badge tone={r.outcome === 'HIT' ? 'good' : 'warn'}>
                    {r.outcome === 'HIT' ? 'found' : 'no record'}
                  </Badge>
                </Td>
                <Td>
                  <Link
                    className="font-mono text-brand hover:underline"
                    to={`/games/${gameId}/enquiries/${r.report}`}
                  >
                    {r.report}
                  </Link>
                </Td>
                <Td right>{r.accounts}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </Page>
  )
}
