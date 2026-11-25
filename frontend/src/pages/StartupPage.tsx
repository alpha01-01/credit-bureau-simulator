import { Link } from 'react-router'

import { useGameCommand } from '../api/game'
import { type StartupData, useStartup } from '../api/managed'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page } from '../components/ui'
import { day, money } from '../lib/format'

const BUTTON =
  'rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

/**
 * Getting started (P3.13): a startup's way from capital to its first paid report. Each
 * step needs the one before it; the decisions that are the chief executive's are taken
 * here, the others on their department's screen.
 */
export function StartupPage() {
  const gameId = useGameId()
  const data = useStartup(gameId)
  const act = useGameCommand(gameId, '/startup/')
  if (data.isPending) return <Loading what="the startup" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const next = d.steps.find((s) => !s.done)
  return (
    <Page
      title="Getting started"
      subtitle={`${d.scenario_name}, ${d.difficulty.toLowerCase()}: from capital to the first paid report.`}
    >
      {act.error && <Failed error={act.error} />}
      <Card title="The way to a working bureau">
        <ol className="space-y-2 text-sm">
          {d.steps.map((s, n) => (
            <li key={s.code} className="flex flex-wrap items-baseline gap-2">
              <span className="w-5 text-right text-slate-400">{n + 1}.</span>
              <Badge tone={s.done ? 'good' : s === next ? 'warn' : 'neutral'}>
                {s.done ? 'done' : s === next ? 'next' : 'to do'}
              </Badge>
              <Link to={`/games/${gameId}/${s.screen}`} className="font-medium hover:underline">
                {s.title}
              </Link>
              <span className="text-slate-600">{s.detail}</span>
            </li>
          ))}
        </ol>
      </Card>

      {!d.office && (
        <Offices
          d={d}
          busy={act.isPending}
          rent={(office) => act.mutate({ action: 'rent_office', office })}
        />
      )}

      <Card title="IT">
        {d.it.set_up ? (
          <p className="text-sm">
            {d.it.ready ? (
              <Badge tone="good">running</Badge>
            ) : (
              <>
                <Badge tone="info">being set up</Badge> ready on {day(d.it.ready_on)}
              </>
            )}
          </p>
        ) : (
          <div className="space-y-2 text-sm">
            <p className="text-slate-700">
              The hosting company sets up servers, network and security for {money(d.it.cost)},
              ready in {d.it.days} working days. Hosting is then billed monthly. High capacity
              processes more files a night and costs more.
            </p>
            {!d.office && (
              <p className="text-slate-500">IT is installed in an office: rent one first.</p>
            )}
            <div className="flex flex-wrap gap-2">
              {d.it.levels.map((level) => (
                <button
                  key={level}
                  type="button"
                  className={BUTTON}
                  disabled={act.isPending || !d.office}
                  onClick={() => act.mutate({ action: 'set_up_it', level })}
                >
                  Set up {level.toLowerCase()} capacity
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card title="Providers">
        <div className="space-y-2 text-sm">
          <p className="text-slate-700">
            The regulations oblige every lender to report to each licensed bureau, but each must be
            onboarded: a data-sharing agreement and a connection. An onboarded provider sends its
            whole book with the next month's files.
          </p>
          {d.onboarded.length > 0 && (
            <p>
              Onboarded: {d.onboarded.map((p) => `${p.name} (since ${day(p.since)})`).join('; ')}
            </p>
          )}
          {!d.it.ready && d.providers.length > 0 && (
            <p className="text-slate-500">
              Providers send their files to the bureau's systems: set up IT first.
            </p>
          )}
          <ul className="space-y-1">
            {d.providers.map((p) => (
              <li key={p.code} className="flex flex-wrap items-center gap-2">
                <span className="min-w-64">
                  {p.name} <span className="text-slate-400">({p.code})</span>
                </span>
                <button
                  type="button"
                  className={BUTTON}
                  disabled={act.isPending || !d.it.ready}
                  onClick={() => act.mutate({ action: 'onboard_provider', provider: p.code })}
                >
                  Onboard
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </Page>
  )
}

function Offices({
  d,
  rent,
  busy,
}: {
  d: StartupData
  rent: (office: string) => void
  busy: boolean
}) {
  return (
    <Card title="Rent an office">
      <p className="text-sm text-slate-700">
        The landlord takes a year's rent in advance; furniture and computers are bought with it. An
        office has so many desks, and staff need one each.
      </p>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        {d.offices.map((o) => (
          <div key={o.code} className="rounded-lg border border-slate-200 p-3 text-sm">
            <p className="font-medium">{o.name}</p>
            <p className="text-slate-600">
              {money(o.monthly_rent)} a month ({money(Number(o.monthly_rent) * 12)} up front),{' '}
              {o.desks} desks; furniture and computers {money(o.fit_out)}
            </p>
            <button
              type="button"
              className={`${BUTTON} mt-2`}
              disabled={busy}
              onClick={() => rent(o.code)}
            >
              Rent it
            </button>
          </div>
        ))}
      </div>
    </Card>
  )
}
