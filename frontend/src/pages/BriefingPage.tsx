import { Link } from 'react-router'

import { useBriefing, useMissions } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page } from '../components/ui'
import { drillPath } from '../lib/drill'
import { count, day, percent } from '../lib/format'

/** Where to start: the current mission, while the campaign is on (P2.13 onboarding). */
function NextMission({ gameId }: { gameId: number }) {
  const missions = useMissions(gameId)
  const current = missions.data?.missions.find((m) => m.status === 'CURRENT')
  if (!missions.data?.campaign || !current) return null
  const first = current.code === 'M1'
  return (
    <section
      aria-labelledby="next-mission"
      className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm"
    >
      <h2 id="next-mission" className="font-semibold">
        {first ? 'New here? Start with your first mission' : `Your mission: ${current.code}`}
      </h2>
      <p className="mt-1">
        {current.code} {current.title}: {current.concept}.
        {first &&
          ' Run the clock (top of the page) and the first provider file will arrive; the mission tells you what to look for.'}
      </p>
      <Link
        to={`/games/${gameId}/missions`}
        className="mt-2 inline-block font-medium text-brand hover:underline"
      >
        Open the mission
      </Link>
    </section>
  )
}

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
      <NextMission gameId={gameId} />
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
