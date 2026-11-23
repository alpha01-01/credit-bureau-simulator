import { useState } from 'react'

import { type GroupRow, useAnalytics } from '../api/analytics'
import { useGameId } from '../app/useGameId'
import { Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, day, money, percent } from '../lib/format'

const DIMENSIONS = [
  ['lender', 'Lender'],
  ['product', 'Product'],
  ['region', 'Region'],
  ['vintage', 'Vintage (quarter opened)'],
] as const

type Dimension = (typeof DIMENSIONS)[number][0]

/** Portfolio analytics: the bureau's own data, by lender, product, region and vintage (P3.4). */
export function AnalyticsPage() {
  const gameId = useGameId()
  const analytics = useAnalytics(gameId)
  const [by, setBy] = useState<Dimension>('lender')
  if (analytics.isPending) return <Loading what="the analytics" />
  if (analytics.isError) return <Failed error={analytics.error} />
  const a = analytics.data
  if (!a.as_of) {
    return (
      <Page title="Analytics" subtitle="The bureau's portfolio, from the data it holds.">
        <Empty>No account has been reported yet.</Empty>
      </Page>
    )
  }
  const rows: GroupRow[] = a.groups[by] ?? []
  const rolls = a.roll_rates
  return (
    <Page
      title="Analytics"
      subtitle={`Each lender as in its latest file: ${count(a.live_accounts)} open accounts. The bureau's own view, errors and all. Default: ${a.default_definition}.`}
    >
      <Card title="The live book">
        {a.lenders_as_of && (
          <p className="mb-2 text-xs text-slate-500">
            Latest files:{' '}
            {Object.entries(a.lenders_as_of)
              .map(([code, d]) => `${code} ${day(d)}`)
              .join(', ')}
          </p>
        )}
        <div className="mb-3 flex flex-wrap gap-1" role="group" aria-label="Group by">
          {DIMENSIONS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={by === key}
              onClick={() => setBy(key)}
              className={`rounded px-2.5 py-1 text-sm ${by === key ? 'bg-brand text-white' : 'text-slate-600 hover:bg-slate-200'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <Table head={['', 'Accounts', 'Balance', '30+ days', '90+ days', 'Balance 90+']}>
          {rows.map((r) => (
            <tr key={r.key}>
              <Td>{r.label}</Td>
              <Td right>{count(r.accounts)}</Td>
              <Td right>{money(r.balance)}</Td>
              <Td right>{percent(r.arrears_30_share)}</Td>
              <Td right>{percent(r.default_90_share)}</Td>
              <Td right>{money(r.balance_90)}</Td>
            </tr>
          ))}
        </Table>
      </Card>

      {rolls && (
        <Card title="Roll rates: each lender's open accounts in its file before last, and where they are now">
          <Table head={['Last month', ...rolls.to, 'Accounts']}>
            {rolls.from.map((from) => {
              const row = rolls.counts[from]
              const total = rolls.to.reduce((n, to) => n + row[to], 0)
              return (
                <tr key={from}>
                  <Td>{from}</Td>
                  {rolls.to.map((to) => (
                    <Td key={to} right>
                      {total ? percent(row[to] / total) : '—'}
                    </Td>
                  ))}
                  <Td right>{count(total)}</Td>
                </tr>
              )
            })}
          </Table>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Vintages: default within 12 months">
          <p className="mb-2 text-xs text-slate-500">
            Accounts opened since the bureau's records began ({day(a.records_start)}): it never saw
            the first months of older ones.
          </p>
          <Table head={['Opened', 'Accounts', 'Default rate', 'So far']}>
            {a.vintages.map((v) => (
              <tr key={v.quarter}>
                <Td>{v.quarter}</Td>
                <Td right>{count(v.accounts)}</Td>
                <Td right>
                  {v.default_rate === null ? 'not yet 12 months' : percent(v.default_rate)}
                </Td>
                <Td right>{percent(v.default_rate_so_far)}</Td>
              </tr>
            ))}
          </Table>
        </Card>
        <Card title="Age at default (months from opening to 90+ days)">
          <Table head={['Months', 'Accounts']}>
            {a.age_at_default.map((g) => (
              <tr key={g.months}>
                <Td>{g.months}</Td>
                <Td right>{count(g.accounts)}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      </div>
    </Page>
  )
}
