import { type FormEvent, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useCustomer, useCustomers } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, day, money } from '../lib/format'

export function CustomersPage() {
  const gameId = useGameId()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const [text, setText] = useState(q)
  const rows = useCustomers(gameId, q)

  function search(event: FormEvent) {
    event.preventDefault()
    setParams(text ? { q: text } : {})
  }

  return (
    <Page title="Customers" subtitle="The bureau's view: what providers have reported, as loaded.">
      <form onSubmit={search} className="flex gap-2" role="search">
        <label className="sr-only" htmlFor="customer-search">
          Search customers
        </label>
        <input
          id="customer-search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Name, bureau reference or identifier (Ghana Card, TIN)"
          className="w-full max-w-md rounded border border-slate-300 px-2 py-1.5 text-sm"
        />
        <button type="submit" className="rounded bg-brand px-3 py-1.5 text-sm text-white">
          Search
        </button>
      </form>
      {rows.isPending && <Loading what="customers" />}
      {rows.isError && <Failed error={rows.error} />}
      {rows.data?.length === 0 && <Empty>No customers found.</Empty>}
      {rows.data && rows.data.length > 0 && (
        <Table head={['Reference', 'Name', 'Type']}>
          {rows.data.map((c) => (
            <tr key={c.reference} className="hover:bg-slate-50">
              <Td>
                <Link
                  className="font-medium text-brand hover:underline"
                  to={`/games/${gameId}/customers/${c.reference}`}
                >
                  {c.reference}
                </Link>
              </Td>
              <Td>{c.name}</Td>
              <Td>{c.type.toLowerCase()}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}

export function CustomerPage() {
  const gameId = useGameId()
  const { reference = '' } = useParams()
  const customer = useCustomer(gameId, reference)
  if (customer.isPending) return <Loading what="the customer" />
  if (customer.isError) return <Failed error={customer.error} />
  const c = customer.data
  return (
    <Page title={c.name} subtitle={`${c.reference}, ${c.type.toLowerCase()}`}>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Identity">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            {c.date_of_birth && (
              <>
                <dt className="text-slate-500">Born</dt>
                <dd>{day(c.date_of_birth)}</dd>
              </>
            )}
            {c.identifiers.map((i) => (
              <div key={i.value} className="contents">
                <dt className="text-slate-500">{i.type.replace('_', ' ').toLowerCase()}</dt>
                <dd className="font-mono text-xs">{i.value}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="Contacts">
          <ul className="text-sm">
            {c.contacts.map((x) => (
              <li key={x.value}>
                {x.value} {x.primary && <Badge>primary</Badge>}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Provider references">
          <ul className="text-sm">
            {c.provider_links.map((l) => (
              <li key={`${l.provider}-${l.number}`}>
                {l.provider}: <span className="font-mono text-xs">{l.number}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      {c.accounts.map((a) => (
        <Card key={a.account_number} title={`${a.lender}: ${a.account_number}`}>
          <p className="mb-2 text-sm text-slate-600">
            {a.facility_type}, opened {day(a.opened)}, original {money(a.original_amount)}, status{' '}
            <Badge
              tone={
                a.status === 'W' || a.status === 'G' ? 'bad' : a.status === 'A' ? 'info' : 'neutral'
              }
            >
              {a.status}
            </Badge>
          </p>
          <Table head={['Month', 'Balance', 'Arrears', 'Days past due', 'Status', 'Source']}>
            {a.observations.map((o) => (
              <tr key={o.date}>
                <Td>{day(o.date)}</Td>
                <Td right>{money(o.balance)}</Td>
                <Td right>{money(o.arrears)}</Td>
                <Td right>
                  {o.days_past_due > 0 ? <Badge tone="warn">{count(o.days_past_due)}</Badge> : '0'}
                </Td>
                <Td>{o.status}</Td>
                <Td>
                  <span className="text-xs text-slate-500">{o.source}</span>
                </Td>
              </tr>
            ))}
          </Table>
        </Card>
      ))}
      <Card title="Recent enquiries">
        {c.enquiries.length === 0 ? (
          <Empty>No enquiries.</Empty>
        ) : (
          <ul className="text-sm">
            {c.enquiries.map((e) => (
              <li key={e.reference}>
                {dateTime(e.at)}: {e.subscriber} ({e.purpose.replace('_', ' ').toLowerCase()})
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  )
}
