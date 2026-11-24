import { useState } from 'react'

import { useGameCommand } from '../api/game'
import { useSupport } from '../api/managed'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { day, money, percent } from '../lib/format'

const BUTTON =
  'rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

const sum = (topics: Record<string, number>) => Object.values(topics).reduce((a, b) => a + b, 0)

/**
 * Customer Support (P3.10, managed): tickets from subscribers and data subjects. They
 * rise with outages, report errors and disputes; the agents answer the oldest first.
 */
export function SupportPage() {
  const gameId = useGameId()
  const data = useSupport(gameId)
  const act = useGameCommand(gameId, '/support/')
  const [agents, setAgents] = useState('')
  if (data.isPending) return <Loading what="support" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const most = Math.max(1, ...d.days.map((x) => sum(x.topics)))
  return (
    <Page
      title="Customer Support"
      subtitle={`Subscribers and data subjects raise tickets; outages, wrong reports and disputes bring more. Each agent answers ${d.per_agent} a working day, oldest first. A ticket answered within ${d.response_days} working day is on time, and subscribers judge us partly on that.`}
    >
      {act.error && <Failed error={act.error} />}
      <Card title="The team">
        <div className="flex flex-wrap items-end gap-6 text-sm">
          <div>
            <p className="text-slate-500">Agents</p>
            <p className="text-2xl font-semibold">{d.agents}</p>
            <p className="text-xs text-slate-500">
              {d.capacity} tickets a day · {money(Number(d.agent_monthly) * d.agents)} a month
            </p>
          </div>
          <div>
            <p className="text-slate-500">Waiting</p>
            <p className={`text-2xl font-semibold ${d.waiting > d.capacity ? 'text-red-700' : ''}`}>
              {d.waiting}
            </p>
          </div>
          <div>
            <p className="text-slate-500">Subscribers answered on time (3 months)</p>
            <p className="text-2xl font-semibold">
              {d.satisfaction.score === null ? '—' : percent(d.satisfaction.score)}
            </p>
            <p className="text-xs text-slate-500">
              {d.satisfaction.on_time} on time, {d.satisfaction.late} late
            </p>
          </div>
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              act.mutate({ agents: Number(agents || d.agents) })
            }}
          >
            <label className="space-y-1">
              <span className="block text-slate-600">
                Agents ({d.range[0]}-{d.range[1]}, {money(d.agent_monthly)} each a month)
              </span>
              <input
                className="w-20 rounded border border-slate-300 px-1 py-0.5"
                inputMode="numeric"
                placeholder={String(d.agents)}
                value={agents}
                onChange={(e) => setAgents(e.target.value)}
              />
            </label>
            <button type="submit" className={BUTTON} disabled={act.isPending}>
              Set
            </button>
          </form>
        </div>
      </Card>
      <Card title="Tickets a day, the last 30 days">
        {d.days.length === 0 ? (
          <Empty>No tickets yet.</Empty>
        ) : (
          <div className="flex h-32 items-end gap-1" role="img" aria-label="Tickets each day">
            {d.days.map((x) => {
              const total = sum(x.topics)
              const outage = x.topics.OUTAGE ?? 0
              return (
                <div
                  key={x.day}
                  className="flex h-full flex-1 flex-col justify-end"
                  title={`${day(x.day)}: ${total} (${outage} about an outage)`}
                >
                  <div className="bg-red-400" style={{ height: `${(outage / most) * 100}%` }} />
                  <div
                    className="bg-brand"
                    style={{ height: `${((total - outage) / most) * 100}%` }}
                  />
                </div>
              )
            })}
          </div>
        )}
        <p className="mt-2 text-xs text-slate-500">
          Red: about an outage. Answered in the last 30 days: {d.answered_30d}, {d.on_time_30d} on
          time
          {d.average_days_30d !== null &&
            `, on average after ${d.average_days_30d.toFixed(1)} days`}
          .
        </p>
      </Card>
      <Card title="Latest tickets">
        {d.tickets.length === 0 ? (
          <Empty>No tickets yet.</Empty>
        ) : (
          <Table head={['#', 'From', 'About', 'Opened', 'Due', 'Answered']}>
            {d.tickets.map((t) => (
              <tr key={t.number}>
                <Td>{t.number}</Td>
                <Td>{t.source === 'SUBJECT' ? 'A data subject' : t.subscriber}</Td>
                <Td>{d.topics[t.topic] ?? t.topic}</Td>
                <Td>{day(t.opened_on)}</Td>
                <Td>{day(t.due_on)}</Td>
                <Td>
                  {t.answered_on ? (
                    <Badge tone={t.answered_on <= t.due_on ? 'good' : 'warn'}>
                      {day(t.answered_on)}
                    </Badge>
                  ) : (
                    <Badge tone="info">waiting</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  )
}
