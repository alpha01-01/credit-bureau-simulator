import { Link } from 'react-router'

import { useBriefing } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page } from '../components/ui'
import { drillPath } from '../lib/drill'
import { count, day, percent } from '../lib/format'

export function BriefingPage() {
  const gameId = useGameId()
  const briefing = useBriefing(gameId)
  if (briefing.isPending) return <Loading what="the briefing" />
  if (briefing.isError) return <Failed error={briefing.error} />
  const b = briefing.data
  return (
    <Page
      title="Morning briefing"
      subtitle={`What happened on ${day(b.yesterday)}, and what needs you today.`}
    >
      <div className="grid gap-4 md:grid-cols-4">
        <Card title="Files received">
          <p className="text-2xl font-semibold">{count(b.files_received.length)}</p>
          <p className="text-xs text-slate-500">
            {b.files_received.map((f) => f.provider).join(', ') || 'none'}
          </p>
        </Card>
        <Card title="Records processed">
          <p className="text-2xl font-semibold">{count(b.records.received)}</p>
          <p className="text-xs text-slate-500">
            {count(b.records.accepted)} loaded, {count(b.records.unloadable)} unloadable,{' '}
            {count(b.records.pending)} held for review
          </p>
        </Card>
        <Card title="Work queue">
          <p className="text-2xl font-semibold">{count(b.work.waiting)}</p>
          <p className="text-xs text-slate-500">
            waiting; {count(b.work.resolved_yesterday)} resolved yesterday
          </p>
        </Card>
        <Card title="Enquiries">
          <p className="text-2xl font-semibold">{count(b.enquiries.count)}</p>
          <p className="text-xs text-slate-500">
            hit rate {percent(b.enquiries.count ? b.enquiries.hits / b.enquiries.count : null)}
          </p>
        </Card>
      </div>
      <Card title="Inbox">
        {b.inbox.length === 0 ? (
          <Empty>Nothing needs your attention.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {b.inbox.map((m, i) => (
              <li key={i} className="flex items-start justify-between gap-3 py-2">
                <div>
                  <Badge tone={m.severity === 'ERROR' ? 'bad' : 'warn'}>{m.severity}</Badge>{' '}
                  <span className="font-medium">{m.title}</span>
                  <p className="text-sm text-slate-500">{m.detail}</p>
                </div>
                <Link
                  className="text-sm text-brand hover:underline"
                  to={drillPath(gameId, m.drill)}
                >
                  Open
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  )
}
