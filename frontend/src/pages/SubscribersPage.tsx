import { useMarket } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, day, money, percent } from '../lib/format'

function tone(score: number) {
  return score >= 70 ? 'good' : score >= 45 ? 'warn' : 'bad'
}

/**
 * The market (P2.8): the bureau's reputation with subscribers, providers and the
 * regulator, each from its own measured inputs, and the subscribers' contracts,
 * which renew each year only if the bureau has been worth it.
 */
export function SubscribersPage() {
  const gameId = useGameId()
  const market = useMarket(gameId)
  if (market.isPending) return <Loading what="the subscribers" />
  if (market.isError) return <Failed error={market.error} />
  const { reputation: r, subscribers } = market.data
  const audiences: [string, number, string][] = [
    [
      'Subscribers',
      r.subscribers.score,
      `hit rate ${percent(r.subscribers.hit_rate)}, right person ${percent(r.subscribers.accuracy)}, disputes on time ${percent(r.subscribers.disputes_on_time)} (last three months)`,
    ],
    [
      'Providers',
      r.providers.score,
      'how willingly they cooperate: feedback, training, fair enforcement',
    ],
    [
      'Regulator',
      r.regulator.score,
      `${count(r.regulator.findings)} finding(s) in six months; ladder level ${r.regulator.level}`,
    ],
  ]
  return (
    <Page
      title="Subscribers"
      subtitle="Lenders pay for reports while the bureau is worth it. Contracts run a year; at each anniversary a lender renews or leaves."
    >
      <section aria-labelledby="reputation-title" className="space-y-2">
        <h2 id="reputation-title" className="text-base font-semibold">
          Reputation
        </h2>
        <dl className="grid gap-4 sm:grid-cols-3">
          {audiences.map(([who, score, why]) => (
            <div key={who} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <dt className="text-sm text-slate-500">{who}</dt>
              <dd className="mt-1 flex items-center gap-2 text-2xl font-semibold tabular-nums">
                {score} <Badge tone={tone(score)}>/ 100</Badge>
              </dd>
              <dd className="mt-1 text-xs text-slate-500">{why}</dd>
            </div>
          ))}
        </dl>
      </section>
      <Card title="Contracts">
        <Table
          head={[
            'Subscriber',
            'Status',
            'Since',
            'Price',
            'Renews',
            'Renewed',
            'Checks (3 months)',
            'Found',
          ]}
        >
          {subscribers.map((s) => (
            <tr key={s.code}>
              <Td>
                {s.name} ({s.code})
              </Td>
              <Td>
                {s.active ? (
                  <Badge tone="good">active</Badge>
                ) : (
                  <Badge tone="bad">left {day(s.left_on)}</Badge>
                )}
              </Td>
              <Td>{day(s.since)}</Td>
              <Td right>{s.price ? money(s.price) : '—'}</Td>
              <Td>{s.active ? day(s.renews_on) : '—'}</Td>
              <Td right>{count(s.renewals)}</Td>
              <Td right>{count(s.enquiries_3m)}</Td>
              <Td right>{s.enquiries_3m ? percent(s.hits_3m / s.enquiries_3m) : '—'}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </Page>
  )
}
