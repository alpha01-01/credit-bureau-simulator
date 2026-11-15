import { useEffect } from 'react'
import { useSearchParams } from 'react-router'

import type { Severity } from '../api/game'
import { useFeed, useGame } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Empty, Failed, Loading, Page, WhyLink } from '../components/ui'
import { markSeen } from '../lib/seen'
import { dateTime } from '../lib/format'

const TONE = { CRITICAL: 'bad', WARNING: 'warn', INFO: 'info' } as const
const FILTERS: [Severity | '', string][] = [
  ['', 'All'],
  ['CRITICAL', 'Critical'],
  ['WARNING', 'Warnings'],
  ['INFO', 'Information'],
]

/** The event feed: what just happened, newest first, each with a "Why?" link (P2.2). */
export function EventsPage() {
  const gameId = useGameId()
  const [params, setParams] = useSearchParams()
  const severity = (params.get('severity') || undefined) as Severity | undefined
  const feed = useFeed(gameId, severity)
  const latest = useGame(gameId).data?.clock?.latest_notice ?? null

  useEffect(() => {
    if (latest !== null) markSeen(gameId, latest)
  }, [gameId, latest])

  return (
    <Page
      title="Events"
      subtitle="What has happened, newest first. The clock stops by itself for the kinds you choose under “Stop for…”."
      actions={
        <div role="group" aria-label="Show" className="flex gap-1 text-sm">
          {FILTERS.map(([value, label]) => (
            <button
              key={label}
              type="button"
              aria-pressed={(severity ?? '') === value}
              onClick={() => setParams(value ? { severity: value } : {})}
              className={`rounded px-2 py-1 ${
                (severity ?? '') === value
                  ? 'bg-brand text-white'
                  : 'border border-slate-300 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      }
    >
      {feed.isPending ? (
        <Loading what="events" />
      ) : feed.isError ? (
        <Failed error={feed.error} />
      ) : (
        <>
          <ol className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
            {feed.data.pages
              .flatMap((page) => page.notices)
              .map((n) => (
                <li key={n.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-3">
                  <time
                    dateTime={n.at}
                    className="w-44 shrink-0 text-xs tabular-nums text-slate-500"
                  >
                    {dateTime(n.at)}
                  </time>
                  <Badge tone={TONE[n.severity]}>{n.severity.toLowerCase()}</Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">
                      {n.title}{' '}
                      {n.paused && (
                        <span className="ml-2 text-xs font-normal text-slate-500">
                          (stopped the clock)
                        </span>
                      )}
                    </p>
                    {n.detail && <p className="text-xs text-slate-600">{n.detail}</p>}
                  </div>
                  {n.drill && <WhyLink gameId={gameId} drill={n.drill} label={n.title} />}
                </li>
              ))}
          </ol>
          {feed.data.pages[0].notices.length === 0 && (
            <Empty>Nothing has happened yet. Run the clock.</Empty>
          )}
          {feed.hasNextPage && (
            <button
              type="button"
              onClick={() => void feed.fetchNextPage()}
              disabled={feed.isFetchingNextPage}
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              Older events
            </button>
          )}
        </>
      )}
    </Page>
  )
}
