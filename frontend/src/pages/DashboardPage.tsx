import { useDashboard } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Failed, Loading, Page, WhyLink } from '../components/ui'
import { day, metricValue } from '../lib/format'

export function DashboardPage() {
  const gameId = useGameId()
  const dashboard = useDashboard(gameId)
  if (dashboard.isPending) return <Loading what="the dashboard" />
  if (dashboard.isError) return <Failed error={dashboard.error} />
  return (
    <Page
      title="CEO dashboard"
      subtitle={`As of ${day(dashboard.data.as_of)}. Every figure links to the records behind it.`}
    >
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {dashboard.data.metrics.map((m) => (
          <div key={m.key} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <dt className="flex items-center justify-between text-sm text-slate-500">
              {m.label}
              <WhyLink gameId={gameId} drill={m.drill} label={m.label} />
            </dt>
            <dd
              className="mt-1 text-2xl font-semibold tabular-nums"
              data-testid={`metric-${m.key}`}
            >
              {metricValue(m.value, m.unit)}
            </dd>
          </div>
        ))}
      </dl>
    </Page>
  )
}
