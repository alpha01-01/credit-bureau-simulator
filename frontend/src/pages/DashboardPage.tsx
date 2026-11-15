import { Link } from 'react-router'

import type { DataAssets, Estimate } from '../api/game'
import { useDashboard, useDataAssets } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Failed, Loading, Page, WhyLink } from '../components/ui'
import { count, day, metricValue, months, percent } from '../lib/format'

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
      <DataAssetsSection gameId={gameId} />
    </Page>
  )
}

/** The bureau's data assets (Document 07, Section 6.2): what it can see and estimate. */
function DataAssetsSection({ gameId }: { gameId: number }) {
  const assets = useDataAssets(gameId)
  return (
    <section aria-labelledby="assets-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="assets-title" className="text-base font-semibold">
          Data assets
        </h2>
        <Link
          to={`/games/${gameId}/reviews`}
          className="text-xs font-medium text-brand underline-offset-2 hover:underline"
        >
          Data Quality Reviews
        </Link>
      </div>
      {assets.isPending ? (
        <Loading what="the data assets" />
      ) : assets.isError ? (
        <Failed error={assets.error} />
      ) : (
        <AssetTiles assets={assets.data} />
      )}
    </section>
  )
}

function AssetTiles({ assets }: { assets: DataAssets }) {
  const tiles: [string, string, string][] = [
    [
      'Coverage',
      percent(assets.coverage.share),
      `${count(assets.coverage.covered)} of ${count(assets.coverage.active_borrowers)} active borrowers at ${day(assets.coverage.period)}`,
    ],
    [
      'Depth',
      months(assets.depth_months),
      `history per account, ${count(assets.accounts)} accounts`,
    ],
    [
      'Freshness',
      assets.freshness_days === null ? '—' : `${assets.freshness_days} days`,
      `since the latest report, median of ${count(assets.open_accounts)} open accounts`,
    ],
    [
      'Accuracy (estimated)',
      estimate(assets.audit.accuracy),
      auditNote(assets.audit.accuracy, 'accounts'),
    ],
    [
      'One person per customer (estimated)',
      estimate(assets.audit.one_person),
      auditNote(assets.audit.one_person, 'customers'),
    ],
  ]
  return (
    <>
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {tiles.map(([label, value, note]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <dt className="text-sm text-slate-500">{label}</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd>
            <dd className="mt-1 text-xs text-slate-500">{note}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-slate-500">
        {assets.source === 'month_end'
          ? `From the month-end review as of ${day(assets.as_of)}.`
          : `As of ${day(assets.as_of)}; refreshed at each month end.`}{' '}
        A bureau never knows its true error rate: accuracy and identity are estimated by checking a
        sample with the providers. The truth is revealed in the monthly review.
      </p>
    </>
  )
}

function estimate(e: Estimate): string {
  if (e.share === null) return '—'
  return `${percent(e.share)} ± ${((e.margin ?? 0) * 100).toFixed(1)} pts`
}

function auditNote(e: Estimate, what: string): string {
  return `sampling audit of ${count(e.sample)} ${what}`
}
