import { NavLink, Outlet, useSearchParams } from 'react-router'

import {
  type IncomeStatement,
  type StatementRow,
  useFinance,
  useInvoices,
  useLedger,
} from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, day, money } from '../lib/format'

export function FinanceLayout() {
  const gameId = useGameId()
  const tabs = [
    ['', 'Statements'],
    ['ledger', 'Ledger'],
    ['invoices', 'Invoices'],
  ]
  return (
    <div className="space-y-4">
      <nav aria-label="Finance" className="flex gap-1">
        {tabs.map(([path, label]) => (
          <NavLink
            key={path}
            end={path === ''}
            to={path ? `/games/${gameId}/finance/${path}` : `/games/${gameId}/finance`}
            className={({ isActive }) =>
              `rounded px-2.5 py-1 text-sm ${isActive ? 'bg-slate-800 text-white' : 'bg-white text-slate-600'}`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}

function Rows({ rows }: { rows: StatementRow[] }) {
  return (
    <>
      {rows.map((r) => (
        <tr key={r.code || r.name}>
          <Td>
            <span className="text-slate-400">{r.code}</span> {r.name}
          </Td>
          <Td right>{money(r.amount)}</Td>
        </tr>
      ))}
    </>
  )
}

function Income({ title, s }: { title: string; s: IncomeStatement }) {
  return (
    <Card title={`${title} (${day(s.start)} to ${day(s.end)})`}>
      <Table head={['Account', 'GHS']}>
        <Rows rows={s.income} />
        <tr className="font-medium">
          <Td>Total income</Td>
          <Td right>{money(s.total_income)}</Td>
        </tr>
        <Rows rows={s.expenses} />
        <tr className="font-medium">
          <Td>Total expenses</Td>
          <Td right>{money(s.total_expenses)}</Td>
        </tr>
        <tr className="font-semibold">
          <Td>Net profit</Td>
          <Td right>{money(s.net_profit)}</Td>
        </tr>
      </Table>
    </Card>
  )
}

export function StatementsPage() {
  const gameId = useGameId()
  const finance = useFinance(gameId)
  if (finance.isPending) return <Loading what="the books" />
  if (finance.isError) return <Failed error={finance.error} />
  const f = finance.data
  const sheet = f.balance_sheet
  return (
    <Page
      title="Financial statements"
      subtitle={`From posted journal entries, as of ${day(f.as_of)}.`}
    >
      <div className="grid gap-4 md:grid-cols-4">
        <Card title="Cash at bank">
          <p className="text-xl font-semibold">{money(f.cash.bank)}</p>
        </Card>
        <Card title="Owed by subscribers">
          <p className="text-xl font-semibold">{money(f.cash.receivables)}</p>
          <p className="text-xs text-slate-500">
            {count(f.cash.overdue_invoices)} invoices overdue
          </p>
        </Card>
        <Card title="Taxes owed">
          <p className="text-xl font-semibold">{money(f.cash.taxes_owed)}</p>
        </Card>
        <Card title="Trial balance">
          <p className="text-sm">
            Dr {money(f.trial_balance.total_debit)}
            <br />
            Cr {money(f.trial_balance.total_credit)}
          </p>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Income title="Month to date" s={f.income_month_to_date} />
        <Income title="Year to date" s={f.income_year_to_date} />
      </div>
      <Card title="Balance sheet">
        <Table head={['', 'GHS']}>
          <Rows rows={sheet.assets} />
          <tr className="font-semibold">
            <Td>Total assets</Td>
            <Td right>{money(sheet.total_assets)}</Td>
          </tr>
          <Rows rows={sheet.liabilities} />
          <Rows rows={sheet.equity} />
          <tr className="font-semibold">
            <Td>Total liabilities and equity</Td>
            <Td right>
              {money(String(Number(sheet.total_liabilities) + Number(sheet.total_equity)))}
            </Td>
          </tr>
        </Table>
        <p className="mt-2 text-sm">
          <Badge tone={sheet.balances ? 'good' : 'bad'}>
            {sheet.balances ? 'Balances' : 'Does not balance'}
          </Badge>
        </p>
      </Card>
    </Page>
  )
}

export function LedgerPage() {
  const gameId = useGameId()
  const [params] = useSearchParams()
  const filters = {
    account: params.get('account') ?? undefined,
    start: params.get('start') ?? undefined,
  }
  const entries = useLedger(gameId, filters)
  return (
    <Page
      title="General ledger"
      subtitle={
        filters.account
          ? `Entries on account ${filters.account}${filters.start ? ` from ${day(filters.start)}` : ''}`
          : 'Posted journal entries, newest first. Posted entries are never edited.'
      }
    >
      {entries.isPending && <Loading what="the ledger" />}
      {entries.isError && <Failed error={entries.error} />}
      {entries.data?.length === 0 && <Empty>No entries.</Empty>}
      {entries.data && entries.data.length > 0 && (
        <Table head={['Reference', 'Date', 'Description', 'Account', 'Debit', 'Credit']}>
          {entries.data.flatMap((e) =>
            e.lines.map((l, i) => (
              <tr
                key={`${e.reference}-${i}`}
                className={i === 0 ? 'border-t-2 border-slate-200' : ''}
              >
                <Td>{i === 0 ? e.reference : ''}</Td>
                <Td>{i === 0 ? day(e.date) : ''}</Td>
                <Td>{i === 0 ? e.description : ''}</Td>
                <Td>{l.account}</Td>
                <Td right>{Number(l.debit) ? money(l.debit) : ''}</Td>
                <Td right>{Number(l.credit) ? money(l.credit) : ''}</Td>
              </tr>
            )),
          )}
        </Table>
      )}
    </Page>
  )
}

export function InvoicesPage() {
  const gameId = useGameId()
  const [params] = useSearchParams()
  const unpaid = params.get('unpaid') ?? undefined
  const invoices = useInvoices(gameId, unpaid)
  return (
    <Page
      title="Invoices"
      subtitle={unpaid ? 'Unpaid invoices only.' : 'Monthly usage invoices, newest first.'}
    >
      {invoices.isPending && <Loading what="invoices" />}
      {invoices.isError && <Failed error={invoices.error} />}
      {invoices.data?.length === 0 && <Empty>No invoices.</Empty>}
      {invoices.data && invoices.data.length > 0 && (
        <Table head={['Invoice', 'Subscriber', 'Period', 'Issued', 'Due', 'Total', 'Outstanding']}>
          {invoices.data.map((i) => (
            <tr key={i.number}>
              <Td>{i.number}</Td>
              <Td>{i.subscriber}</Td>
              <Td>{day(i.period)}</Td>
              <Td>{day(i.issued)}</Td>
              <Td>{day(i.due)}</Td>
              <Td right>{money(i.total)}</Td>
              <Td right>
                {Number(i.outstanding) > 0 ? money(i.outstanding) : <Badge tone="good">paid</Badge>}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}
