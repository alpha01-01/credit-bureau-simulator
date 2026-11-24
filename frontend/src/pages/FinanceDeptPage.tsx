import { useState } from 'react'

import { useBank, useBills, useBudget, useClose } from '../api/finance'
import { useGameCommand } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Table, Td } from '../components/ui'
import { dateTime, day, money } from '../lib/format'

const BUTTON =
  'rounded border border-brand px-2 py-1 text-xs font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

const BILL_STATUS: Record<string, [string, 'good' | 'warn' | 'bad' | 'neutral']> = {
  RECEIVED: ['awaiting approval', 'warn'],
  APPROVED: ['approved', 'neutral'],
  REJECTED: ['rejected', 'neutral'],
  PAID: ['paid', 'good'],
}

/** Suppliers' bills (P3.8): recorded on arrival, approved, paid on their terms. */
export function BillsPage() {
  const gameId = useGameId()
  const data = useBills(gameId)
  const act = useGameCommand(gameId, '/finance/bills/')
  const [limit, setLimit] = useState('')
  if (data.isPending) return <Loading what="the bills" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  return (
    <>
      {act.error && <Failed error={act.error} />}
      <Card title="Approval">
        <form
          className="flex flex-wrap items-end gap-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            if (limit) act.mutate({ action: 'limit', amount: limit })
          }}
        >
          <p className="max-w-xl text-slate-600">
            Bills up to the limit are approved by delegated authority and paid on their due date
            without you. Bills above it wait for you. A bill paid late costs{' '}
            {Number(d.late_charge_rate) * 100}% for each month, and the hosting company stops
            service when its bill is ten working days overdue.
          </p>
          <label className="flex flex-col">
            Limit (GHS)
            <input
              type="number"
              min="0"
              step="100"
              placeholder={money(d.approval_limit)}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              className="w-36 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button type="submit" className={BUTTON} disabled={act.isPending || !limit}>
            Set the limit
          </button>
        </form>
      </Card>
      <Card title="Bills">
        {d.bills.length === 0 ? (
          <Empty>No bills yet: suppliers bill at each month&apos;s start.</Empty>
        ) : (
          <Table head={['#', 'Supplier', 'For', 'GHS', 'Received', 'Due', 'Status', '']}>
            {d.bills.map((b) => {
              const [label, tone] = BILL_STATUS[b.status]
              const open = b.status === 'RECEIVED' || b.status === 'APPROVED'
              return (
                <tr key={b.number}>
                  <Td>{b.number}</Td>
                  <Td>
                    {b.supplier}
                    <div className="text-xs text-slate-500">ref {b.reference}</div>
                  </Td>
                  <Td>
                    {b.description}
                    {b.same_reference_as !== null && (
                      <div className="text-xs text-amber-800">
                        Same reference as bill {b.same_reference_as}
                      </div>
                    )}
                  </Td>
                  <Td right>{money(b.amount)}</Td>
                  <Td>{day(b.bill_date)}</Td>
                  <Td>{day(b.due_date)}</Td>
                  <Td>
                    <Badge tone={b.overdue ? 'bad' : tone}>
                      {b.overdue ? `${label}, overdue` : label}
                    </Badge>
                    {b.paid_on && (
                      <div className="text-xs text-slate-500">
                        paid {day(b.paid_on)}
                        {Number(b.late_fee) > 0 && `, late charge ${money(b.late_fee)}`}
                      </div>
                    )}
                    {b.approved_by && b.status !== 'REJECTED' && (
                      <div className="text-xs text-slate-500">by {b.approved_by}</div>
                    )}
                  </Td>
                  <Td>
                    {open && (
                      <span className="flex gap-1">
                        {b.status === 'RECEIVED' && (
                          <button
                            type="button"
                            className={BUTTON}
                            disabled={act.isPending}
                            onClick={() => act.mutate({ action: 'approve', number: b.number })}
                          >
                            Approve
                          </button>
                        )}
                        <button
                          type="button"
                          className={BUTTON}
                          disabled={act.isPending}
                          onClick={() => act.mutate({ action: 'reject', number: b.number })}
                        >
                          Reject
                        </button>
                      </span>
                    )}
                  </Td>
                </tr>
              )
            })}
          </Table>
        )}
      </Card>
    </>
  )
}

const LINE_STATUS: Record<string, [string, 'good' | 'warn' | 'bad' | 'neutral']> = {
  MATCHED: ['matched', 'good'],
  OPEN: ['not in the ledger', 'warn'],
  POSTED: ['posted', 'good'],
  QUERIED: ['queried', 'neutral'],
  BANK_ERROR: ['bank error, to be reversed', 'neutral'],
}

/** Bank reconciliation (P3.8): the bank's statement against the ledger. */
export function BankPage() {
  const gameId = useGameId()
  const [period, setPeriod] = useState<string | null>(null)
  const data = useBank(gameId, period)
  const act = useGameCommand(gameId, '/finance/bank/')
  if (data.isPending) return <Loading what="the bank statements" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const s = d.statement
  if (!s)
    return (
      <Empty>
        No statement yet: the bank sends each month&apos;s at the next month&apos;s start.
      </Empty>
    )
  const lineAction = (action: string, line: number) =>
    act.mutate({ action, period: s.period, line })
  return (
    <>
      {act.error && <Failed error={act.error} />}
      <div className="flex flex-wrap gap-1">
        {d.statements.map((x) => (
          <button
            key={x.period}
            type="button"
            onClick={() => setPeriod(x.period)}
            className={`rounded px-2.5 py-1 text-sm ${x.period === s.period ? 'bg-slate-800 text-white' : 'bg-white text-slate-600'}`}
          >
            {x.period.slice(0, 7)} {x.reconciled ? '✓' : ''}
          </button>
        ))}
      </div>
      <Card title={`Reconciliation to ${day(s.period)}`}>
        <Table head={['', 'GHS']}>
          <tr>
            <Td>Balance in the ledger</Td>
            <Td right>{money(s.ledger_balance)}</Td>
          </tr>
          {s.unrecorded.map((x) => (
            <tr key={`${x.period}-${x.line}`}>
              <Td>
                <span className="text-slate-500">On the statement, not in the ledger:</span>{' '}
                {x.description} ({day(x.value_date)})
              </Td>
              <Td right>{money(x.amount)}</Td>
            </tr>
          ))}
          {s.uncleared.map((u) => (
            <tr key={u.reference}>
              <Td>
                <span className="text-slate-500">In the ledger, not yet cleared:</span>{' '}
                {u.description} ({day(u.date)})
              </Td>
              <Td right>{money(String(-Number(u.amount)))}</Td>
            </tr>
          ))}
          <tr className="font-medium">
            <Td>Explained balance</Td>
            <Td right>{money(s.explained_balance)}</Td>
          </tr>
          <tr className="font-medium">
            <Td>Balance on the bank&apos;s statement</Td>
            <Td right>{money(s.closing_balance)}</Td>
          </tr>
        </Table>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          {s.reconciled_at ? (
            <Badge tone="good">Reconciled {dateTime(s.reconciled_at)}</Badge>
          ) : (
            <>
              <button
                type="button"
                className={BUTTON}
                disabled={act.isPending}
                onClick={() => act.mutate({ action: 'complete', period: s.period })}
              >
                Complete the reconciliation
              </button>
              <span className="text-slate-600">
                {s.open_items
                  ? `${s.open_items} statement item(s) to post or query first.`
                  : 'Every item is accounted for.'}
              </span>
            </>
          )}
        </div>
      </Card>
      <Card title={`The bank's statement: ${s.lines.length} lines`}>
        <Table head={['#', 'Date', 'Description', 'Reference', 'GHS', 'Status', '']}>
          {s.lines.map((x) => {
            const [label, tone] = LINE_STATUS[x.status]
            return (
              <tr key={x.line}>
                <Td>{x.line}</Td>
                <Td>{day(x.value_date)}</Td>
                <Td>
                  {x.description}
                  {x.answer && <div className="text-xs text-slate-600">Bank: {x.answer}</div>}
                </Td>
                <Td>{x.reference ?? '—'}</Td>
                <Td right>{money(x.amount)}</Td>
                <Td>
                  <Badge tone={tone}>
                    {x.awaiting_answer ? 'queried, awaiting the bank' : label}
                  </Badge>
                </Td>
                <Td>
                  {x.status === 'OPEN' && (
                    <span className="flex gap-1">
                      <button
                        type="button"
                        className={BUTTON}
                        disabled={act.isPending}
                        onClick={() => lineAction('post', x.line)}
                      >
                        Post to ledger
                      </button>
                      {!x.answer && (
                        <button
                          type="button"
                          className={BUTTON}
                          disabled={act.isPending}
                          onClick={() => lineAction('query', x.line)}
                        >
                          Query
                        </button>
                      )}
                    </span>
                  )}
                </Td>
              </tr>
            )
          })}
        </Table>
      </Card>
    </>
  )
}

/** Budgets against actuals by cost centre (P3.8); the actuals are the ledger's. */
export function BudgetPage() {
  const gameId = useGameId()
  const [month, setMonth] = useState<string | null>(null)
  const data = useBudget(gameId, month)
  const act = useGameCommand(gameId, '/finance/budget/')
  const [editing, setEditing] = useState<{ centre: string; amount: string } | null>(null)
  if (data.isPending) return <Loading what="the budget" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const chosen = d.month.slice(0, 7) + '-01'
  return (
    <>
      {act.error && <Failed error={act.error} />}
      <div className="flex flex-wrap gap-1">
        {d.months.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMonth(m)}
            className={`rounded px-2.5 py-1 text-sm ${m === d.month ? 'bg-slate-800 text-white' : 'bg-white text-slate-600'}`}
          >
            {m.slice(0, 7)}
          </button>
        ))}
      </div>
      <Card title={`Budget against actuals, ${d.month.slice(0, 7)}`}>
        <Table head={['Cost centre', 'Budget', 'Actual', 'Variance', '']}>
          {d.rows.map((r) => (
            <tr key={r.centre}>
              <Td>
                {r.name}
                {r.income && <span className="ml-1 text-xs text-slate-500">(to reach)</span>}
              </Td>
              <Td right>
                {editing?.centre === r.centre ? (
                  <form
                    className="flex justify-end gap-1"
                    onSubmit={(e) => {
                      e.preventDefault()
                      act.mutate(
                        { action: 'set', centre: r.centre, amount: editing.amount, month: chosen },
                        { onSuccess: () => setEditing(null) },
                      )
                    }}
                  >
                    <input
                      type="number"
                      min="0"
                      value={editing.amount}
                      onChange={(e) => setEditing({ centre: r.centre, amount: e.target.value })}
                      className="w-28 rounded border border-slate-300 px-1"
                    />
                    <button type="submit" className={BUTTON}>
                      Save
                    </button>
                  </form>
                ) : r.budget === null ? (
                  '—'
                ) : (
                  money(r.budget)
                )}
              </Td>
              <Td right>{money(r.actual)}</Td>
              <Td right>
                {r.variance === null ? (
                  '—'
                ) : (
                  <span className={Number(r.variance) < 0 ? 'text-red-800' : 'text-emerald-800'}>
                    {money(r.variance)}
                    {r.variance_share !== null && ` (${(r.variance_share * 100).toFixed(0)}%)`}
                  </span>
                )}
              </Td>
              <Td>
                {r.centre !== 'UNALLOCATED' && editing?.centre !== r.centre && (
                  <button
                    type="button"
                    className={BUTTON}
                    onClick={() => setEditing({ centre: r.centre, amount: r.budget ?? '0' })}
                  >
                    Set from this month
                  </button>
                )}
              </Td>
            </tr>
          ))}
          <tr className="font-medium">
            <Td>Revenue less costs</Td>
            <Td right>{''}</Td>
            <Td right>{money(d.result)}</Td>
            <Td right>{''}</Td>
            <Td>{''}</Td>
          </tr>
        </Table>
        <p className="mt-2 text-xs text-slate-500">
          A negative variance is a cost over budget, or revenue short of it. The actuals are the
          ledger&apos;s postings for the month, account by account.
        </p>
        <div className="mt-2">
          {d.reviewed ? (
            <Badge tone="good">Reviewed for the month-end close</Badge>
          ) : (
            <button
              type="button"
              className={BUTTON}
              disabled={act.isPending}
              onClick={() => act.mutate({ action: 'review', month: chosen })}
            >
              Mark reviewed for the close
            </button>
          )}
        </div>
      </Card>
    </>
  )
}

/** The month-end close (P3.8): a checklist, then the month is locked. */
export function ClosePage() {
  const gameId = useGameId()
  const data = useClose(gameId)
  const act = useGameCommand(gameId, '/finance/close/')
  if (data.isPending) return <Loading what="the close" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const ready = d.ended && d.checklist.every((i) => i.done)
  return (
    <>
      {act.error && <Failed error={act.error} />}
      <Card title={`Closing ${d.period.slice(0, 7)}`}>
        {!d.ended && <p className="mb-2 text-sm text-slate-600">The month has not ended yet.</p>}
        <ul className="space-y-1 text-sm">
          {d.checklist.map((i) => (
            <li key={i.code} className="flex items-baseline gap-2">
              <Badge tone={i.done ? 'good' : 'warn'}>{i.done ? 'done' : 'to do'}</Badge>
              {i.title}
              {!i.done && i.how && <span className="text-xs text-slate-500">{i.how}</span>}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className={`mt-3 ${BUTTON}`}
          disabled={act.isPending || !ready}
          onClick={() => act.mutate({ period: d.period })}
        >
          Close {d.period.slice(0, 7)}
        </button>
        <p className="mt-2 text-xs text-slate-500">
          A closed month takes no more postings: anything found later is put right in the month it
          is found.
        </p>
      </Card>
      {d.closed.length > 0 && (
        <Card title="Closed months">
          <ul className="text-sm">
            {d.closed.map((c) => (
              <li key={c.period}>
                {c.period.slice(0, 7)}: closed {dateTime(c.closed_at)}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  )
}
