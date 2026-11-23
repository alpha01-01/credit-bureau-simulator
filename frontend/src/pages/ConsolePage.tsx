import { useState } from 'react'

import { useConsoleInfo, useConsoleQuery } from '../api/analytics'
import { useGameId } from '../app/useGameId'
import { Card, Failed, Loading, Page, Table, Td } from '../components/ui'

const EXAMPLES = [
  [
    'Accounts by lender',
    'SELECT lender, count(*) AS accounts, sum(original_amount) AS lent\nFROM accounts\nGROUP BY lender\nORDER BY accounts DESC',
  ],
  [
    'Arrears last month',
    'SELECT a.lender, count(*) FILTER (WHERE o.days_past_due >= 30) AS in_arrears, count(*) AS reported\nFROM observations o JOIN accounts a ON a.id = o.account_id\nWHERE o.reporting_date = (SELECT max(reporting_date) FROM observations)\nGROUP BY a.lender',
  ],
  [
    'Customers with the most accounts',
    'SELECT c.customer_reference, count(*) AS accounts\nFROM accounts a JOIN customers c ON c.id = a.customer_id\nGROUP BY c.customer_reference\nORDER BY accounts DESC\nLIMIT 20',
  ],
  [
    'Revenue in the ledger',
    "SELECT account_name, sum(credit) - sum(debit) AS amount\nFROM journal_lines\nWHERE account_code LIKE '4%'\nGROUP BY account_name",
  ],
] as const

/** Read-only SQL over the bureau's own data (P3.4). */
export function ConsolePage() {
  const gameId = useGameId()
  const info = useConsoleInfo(gameId)
  const query = useConsoleQuery(gameId)
  const [sql, setSql] = useState<string>(EXAMPLES[0][1])
  if (info.isPending) return <Loading what="the console" />
  if (info.isError) return <Failed error={info.error} />
  const result = query.data
  return (
    <Page
      title="SQL console"
      subtitle={`Read-only SQL over this bureau's own data. One SELECT at a time; at most ${info.data.max_rows} rows; stopped after ${info.data.timeout_seconds} seconds.`}
    >
      {!info.data.available && (
        <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
          The console is not set up on this server yet: a database administrator must create its
          role once (README, “The SQL console”).
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <div className="space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              query.mutate(sql)
            }}
            className="space-y-2"
          >
            <label htmlFor="sql" className="text-sm font-medium">
              Query
            </label>
            <textarea
              id="sql"
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) query.mutate(sql)
              }}
              rows={8}
              spellCheck={false}
              className="w-full rounded border border-slate-300 bg-white p-2 font-mono text-sm"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={query.isPending || !info.data.available}
                className="rounded bg-brand px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {query.isPending ? 'Running…' : 'Run (Ctrl+Enter)'}
              </button>
              {EXAMPLES.map(([label, text]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setSql(text)}
                  className="rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-200"
                >
                  {label}
                </button>
              ))}
            </div>
          </form>
          {query.isError && (
            <p role="alert" className="text-sm text-red-700">
              {query.error.message}
            </p>
          )}
          {result && (
            <div className="space-y-1">
              <p className="text-xs text-slate-500">
                {result.rows.length.toLocaleString('en-GB')} row(s) in {result.milliseconds} ms
                {result.truncated && `; only the first ${info.data.max_rows} are shown`}.
              </p>
              <Table head={result.columns}>
                {result.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((value, j) => (
                      <Td key={j} right={typeof value === 'number'}>
                        {value === null ? (
                          <span className="text-slate-400">null</span>
                        ) : (
                          String(value)
                        )}
                      </Td>
                    ))}
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </div>
        <Card title="Tables">
          <ul className="space-y-1 text-sm">
            {info.data.tables.map((t) => (
              <li key={t.table}>
                <details>
                  <summary className="cursor-pointer font-mono">{t.table}</summary>
                  <ul className="ml-3 text-xs text-slate-600">
                    {t.columns.map((c) => (
                      <li key={c.name}>
                        <span className="font-mono">{c.name}</span> {c.type}
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </Page>
  )
}
