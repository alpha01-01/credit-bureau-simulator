import { useGameCommand, useIt } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, money } from '../lib/format'

const RESPONSE = { VENDOR: 'vendor called', BACKUP: 'restored from backup', '': 'no response' }

/**
 * IT (P2.9): overnight processing capacity and outages. While systems are down,
 * lenders cannot check the bureau and the overnight batch does not run, so files
 * wait and the data in reports grows older.
 */
export function ItPage() {
  const gameId = useGameId()
  const it = useIt(gameId)
  const act = useGameCommand(gameId, '/it/')
  if (it.isPending) return <Loading what="IT" />
  if (it.isError) return <Failed error={it.error} />
  const d = it.data
  const current = d.incidents.find((i) => i.active)
  return (
    <Page
      title="IT"
      subtitle="The overnight batch loads providers' files. Files beyond the night's capacity wait for the next night; an outage stops both the batch and lenders' checks."
    >
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      {current && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
          <p className="font-semibold text-red-800">Systems are down</p>
          <p className="mt-1 text-red-800">{current.detail}</p>
          {current.response ? (
            <p className="mt-2">Responding: {RESPONSE[current.response]}.</p>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ action: 'respond', response: 'VENDOR' })}
                className="rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
              >
                Call the vendor ({money(d.vendor_cost)}, back within two hours)
              </button>
              <button
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ action: 'respond', response: 'BACKUP' })}
                className="rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
              >
                Restore from backup (free, back within a working day)
              </button>
            </div>
          )}
        </div>
      )}
      <Card title="Overnight capacity">
        <p className="mb-3 text-sm">
          {count(d.files_waiting)} file(s) waiting for the overnight batch.
        </p>
        <Table head={['Level', 'Files a night', 'Extra cost a month', '']}>
          {d.levels.map((l) => (
            <tr key={l.level}>
              <Td>{l.level.toLowerCase()}</Td>
              <Td right>{l.files_per_night}</Td>
              <Td right>{money(l.monthly_cost)}</Td>
              <Td>
                {d.capacity === l.level ? (
                  <Badge tone="good">in use</Badge>
                ) : (
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ action: 'capacity', level: l.level })}
                    className="rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                  >
                    Switch
                  </button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="Outages">
        {d.incidents.length === 0 ? (
          <Empty>No outages so far.</Empty>
        ) : (
          <Table head={['#', 'What happened', 'Response', 'Working hours down']}>
            {d.incidents.map((i) => (
              <tr key={i.number}>
                <Td>{i.number}</Td>
                <Td>{i.detail}</Td>
                <Td>{RESPONSE[i.response]}</Td>
                <Td right>{i.active ? 'still down' : i.hours}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  )
}
