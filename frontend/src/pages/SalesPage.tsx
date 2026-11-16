import { useState } from 'react'

import { useGameCommand, useSales } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { dateTime, day, money, percent } from '../lib/format'

const STATUS_TONE = { PENDING: 'info', ACCEPTED: 'good', DECLINED: 'bad' } as const

/**
 * Sales (P2.9): proposals to lenders that do not subscribe yet. A lender weighs our
 * reputation with subscribers (do we find the right people?) against the price.
 */
export function SalesPage() {
  const gameId = useGameId()
  const sales = useSales(gameId)
  const act = useGameCommand(gameId, '/sales/')
  const [price, setPrice] = useState<Record<string, string>>({})
  if (sales.isPending) return <Loading what="sales" />
  if (sales.isError) return <Failed error={sales.error} />
  const s = sales.data
  const track =
    s.reputation.enquiries === 0
      ? 'no checks in the last three months to judge us by'
      : `hit rate ${percent(s.reputation.hit_rate)}, right person ${percent(s.reputation.accuracy)}`
  const names = Object.fromEntries(s.prospects.map((p) => [p.code, p.name]))
  return (
    <Page
      title="Sales"
      subtitle={`Lenders answer a proposal in ${s.answer_days} working days. They weigh our reputation with subscribers, now ${s.reputation.score} out of 100 (${track}), against the price; our list price is ${money(s.list_price)} a report.`}
    >
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      <Card title="Lenders we could sign">
        {s.prospects.length === 0 ? (
          <Empty>Every lender in the market subscribes.</Empty>
        ) : (
          <Table head={['Lender', 'Type', 'Price per report', '']}>
            {s.prospects.map((p) => (
              <tr key={p.code}>
                <Td>
                  {p.name} <span className="text-xs text-slate-500">{p.code}</span>
                </Td>
                <Td>{p.type.toLowerCase().replaceAll('_', ' ')}</Td>
                <Td right>
                  <label className="sr-only" htmlFor={`price-${p.code}`}>
                    Price per report for {p.name}
                  </label>
                  <input
                    id={`price-${p.code}`}
                    inputMode="decimal"
                    disabled={p.waiting}
                    placeholder={s.list_price}
                    value={price[p.code] ?? ''}
                    onChange={(e) => setPrice({ ...price, [p.code]: e.target.value })}
                    className="w-24 rounded border border-slate-300 px-1 py-0.5 text-right text-sm"
                  />
                </Td>
                <Td>
                  {p.waiting ? (
                    <Badge tone="info">waiting for an answer</Badge>
                  ) : (
                    <button
                      type="button"
                      disabled={act.isPending}
                      onClick={() =>
                        act.mutate({ lender: p.code, price: price[p.code] || s.list_price })
                      }
                      className="rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                    >
                      Send a proposal
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Proposals">
        {s.proposals.length === 0 ? (
          <Empty>No proposals sent yet.</Empty>
        ) : (
          <Table head={['Lender', 'Price', 'Sent', 'Answer', 'Answered']}>
            {s.proposals.map((p) => (
              <tr key={p.number}>
                <Td>{names[p.lender] ?? p.lender}</Td>
                <Td right>{money(p.price)}</Td>
                <Td>{dateTime(p.sent_at)}</Td>
                <Td>
                  <Badge tone={STATUS_TONE[p.status]}>{p.status.toLowerCase()}</Badge>
                </Td>
                <Td>{dateTime(p.answered_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Subscribers">
        <Table head={['Subscriber', 'Since', 'Price per report', '']}>
          {s.subscribers.map((sub) => (
            <tr key={sub.code}>
              <Td>{sub.name}</Td>
              <Td>{day(sub.since)}</Td>
              <Td right>{money(sub.price)}</Td>
              <Td>{sub.active ? <Badge tone="good">active</Badge> : <Badge>left</Badge>}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </Page>
  )
}
