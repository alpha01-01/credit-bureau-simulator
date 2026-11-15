import { useState } from 'react'
import { Link } from 'react-router'

import { useGameCommand, useOwnRules } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { dateTime } from '../lib/format'

/**
 * The bureau's own rules (P2.5): cleansing rules it writes, applied after the built-in
 * ones, and validation checks it relaxes to a warning. The monthly Data Quality Review
 * measures what each one did against the truth.
 */
export function RulesPage() {
  const gameId = useGameId()
  const rules = useOwnRules(gameId)
  const change = useGameCommand(gameId, '/rules/')
  if (rules.isPending) return <Loading what="the rules" />
  if (rules.isError) return <Failed error={rules.error} />
  const r = rules.data
  return (
    <Page
      title="Rules"
      subtitle={
        <>
          Cleansing and validation rules of your own. They apply to files processed from now on; the{' '}
          <Link to={`/games/${gameId}/reviews`} className="text-brand hover:underline">
            monthly review
          </Link>{' '}
          shows how often each one was right.
        </>
      }
    >
      <Card title="Cleansing rules">
        {r.cleansing.length === 0 ? (
          <Empty>No rules of your own yet.</Empty>
        ) : (
          <Table head={['Rule', 'Field', 'What it does', 'Providers', 'Since', 'On']}>
            {r.cleansing.map((rule) => (
              <tr key={rule.code}>
                <Td>{rule.code}</Td>
                <Td>{rule.field}</Td>
                <Td>
                  {rule.action === 'REPLACE'
                    ? `"${rule.find}" becomes "${rule.replace}"`
                    : `remove "${rule.find}"`}
                </Td>
                <Td>{rule.provider || 'all'}</Td>
                <Td>{dateTime(rule.created_at)}</Td>
                <Td>
                  <label className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={rule.active}
                      disabled={change.isPending}
                      onChange={(e) => change.mutate({ code: rule.code, active: e.target.checked })}
                    />
                    <span className="sr-only">Rule {rule.code} is on</span>
                  </label>
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <NewRule gameId={gameId} providers={r.providers} actions={r.actions} />
      </Card>
      <Card title="Validation checks you may relax">
        <p className="mb-3 text-sm text-slate-600">
          A relaxed check no longer stops a record: it loads as the provider sent it, with a
          warning. More data, but some of it wrong.
        </p>
        <Table head={['Rule', 'Check', 'Setting']}>
          {r.validation.map((v) => (
            <tr key={v.code}>
              <Td>{v.code}</Td>
              <Td>{v.description}</Td>
              <Td>
                <select
                  aria-label={`Setting for ${v.code}`}
                  value={v.setting}
                  disabled={change.isPending}
                  onChange={(e) =>
                    change.mutate({ override: { code: v.code, setting: e.target.value } })
                  }
                  className="rounded border border-slate-300 px-1 py-0.5"
                >
                  <option value="ERROR">Reject the record</option>
                  <option value="WARNING">Load with a warning</option>
                </select>{' '}
                {v.setting === 'WARNING' && <Badge tone="warn">relaxed</Badge>}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      {change.isError && (
        <p role="alert" className="text-sm text-red-700">
          {change.error.message}
        </p>
      )}
    </Page>
  )
}

function NewRule({
  gameId,
  providers,
  actions,
}: {
  gameId: number
  providers: string[]
  actions: { code: string; description: string }[]
}) {
  const add = useGameCommand(gameId, '/rules/')
  const [rule, setRule] = useState({
    field: '',
    action: 'REPLACE',
    find: '',
    replace: '',
    provider: '',
  })
  const set = (key: keyof typeof rule) => (e: { target: { value: string } }) =>
    setRule({ ...rule, [key]: e.target.value })
  const input = 'mt-1 rounded border border-slate-300 px-2 py-1 text-sm text-slate-900'
  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4"
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate({ add: rule }, { onSuccess: () => setRule({ ...rule, find: '', replace: '' }) })
      }}
    >
      <label className="flex flex-col text-xs text-slate-500">
        Field
        <input value={rule.field} onChange={set('field')} placeholder="Gender" className={input} />
      </label>
      <label className="flex flex-col text-xs text-slate-500">
        Action
        <select value={rule.action} onChange={set('action')} className={input}>
          {actions.map((a) => (
            <option key={a.code} value={a.code}>
              {a.description}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col text-xs text-slate-500">
        {rule.action === 'REPLACE' ? 'When the value is' : 'Characters to remove'}
        <input value={rule.find} onChange={set('find')} placeholder="Male" className={input} />
      </label>
      {rule.action === 'REPLACE' && (
        <label className="flex flex-col text-xs text-slate-500">
          Make it
          <input value={rule.replace} onChange={set('replace')} placeholder="M" className={input} />
        </label>
      )}
      <label className="flex flex-col text-xs text-slate-500">
        Providers
        <select value={rule.provider} onChange={set('provider')} className={input}>
          <option value="">All</option>
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={!rule.field || !rule.find || add.isPending}
        className="rounded bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        Add rule
      </button>
      {add.isError && (
        <span role="alert" className="text-sm text-red-700">
          {add.error.message}
        </span>
      )}
    </form>
  )
}
