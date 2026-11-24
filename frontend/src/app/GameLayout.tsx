import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'

import { useGame } from '../api/game'
import { ClockBar } from '../components/ClockBar'
import { RoleSwitcher, ScreenOwner } from '../components/RoleBar'
import { Failed, Loading } from '../components/ui'
import { hasUnseen } from '../lib/seen'
import { useGameId } from './useGameId'
import { useLiveClock } from './useLiveClock'

const NAV = [
  ['', 'Briefing'],
  ['office', 'Office'],
  ['missions', 'Missions'],
  ['events', 'Events'],
  ['economy', 'Economy'],
  ['dashboard', 'Dashboard'],
  ['health', 'Health'],
  ['submissions', 'Submissions'],
  ['providers', 'Providers'],
  ['queue', 'Work queue'],
  ['rules', 'Rules'],
  ['compliance', 'Compliance'],
  ['disputes', 'Disputes'],
  ['customers', 'Customers'],
  ['enquiries', 'Enquiries'],
  ['subscribers', 'Subscribers'],
  ['sales', 'Sales'],
  ['batches', 'Batches'],
  ['onboarding', 'Onboarding'],
  ['staff', 'Staff'],
  ['it', 'IT'],
  ['support', 'Support'],
  ['products', 'Products'],
  ['finance', 'Finance'],
  ['reviews', 'Reviews'],
  ['analytics', 'Analytics'],
  ['console', 'SQL console'],
  ['scorecards', 'Scorecards'],
  ['handbook', 'Handbook'],
] as const

/** The screen a path shows, as the navigation names it; null below a list (an item's page). */
function screenOf(pathname: string, gameId: number): string | null {
  const rest = pathname.replace(`/games/${gameId}`, '').split('/').filter(Boolean)
  if (rest.length === 0) return ''
  if (rest.length === 1 || rest[0] === 'finance') return rest[0]
  return null
}

export function GameLayout() {
  const gameId = useGameId()
  const game = useGame(gameId)
  const location = useLocation()
  useLiveClock(gameId, game.data?.clock ?? null)

  const preparing = game.data && (game.data.setup_status !== 'READY' || !game.data.clock)
  useEffect(() => {
    if (preparing) document.title = `${game.data?.bureau ?? 'Game'}: preparing · SimB`
  }, [preparing, game.data?.bureau])

  if (game.isPending) return <Loading what="the game" />
  if (game.isError) return <Failed error={game.error} />

  const data = game.data
  const screen = screenOf(location.pathname, gameId)
  if (data.setup_status !== 'READY' || !data.clock) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6" role="status">
        <h1 className="text-lg font-semibold">{data.bureau}</h1>
        {data.setup_status === 'FAILED' ? (
          <p className="mt-2 text-sm text-red-700">Setup failed: {data.setup_message}</p>
        ) : (
          <p className="mt-2 text-sm text-slate-600">
            Preparing the bureau's history… {data.setup_message}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="z-10 -mx-4 border-b border-slate-200 bg-paper/95 px-4 py-3 backdrop-blur lg:sticky lg:top-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-semibold">{data.bureau}</span>
          <ClockBar gameId={gameId} clock={data.clock} />
        </div>
        <div className="mt-2">
          <RoleSwitcher gameId={gameId} role={data.clock.role} />
        </div>
        <nav aria-label="Game" className="mt-3 flex flex-wrap gap-1">
          {NAV.filter(([path]) => data.clock?.role.screens.includes(path)).map(([path, label]) => (
            <NavLink
              key={path}
              to={path ? `/games/${gameId}/${path}` : `/games/${gameId}`}
              end={path === ''}
              className={({ isActive }) =>
                `rounded px-2.5 py-1 text-sm ${
                  isActive ? 'bg-brand text-white' : 'text-slate-600 hover:bg-slate-200'
                }`
              }
            >
              {label}
              {path === 'events' && hasUnseen(gameId, data.clock?.latest_notice ?? null) && (
                <span className="ml-1 text-amber-500" aria-label="new events">
                  •
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
      {screen !== null && <ScreenOwner gameId={gameId} screen={screen} role={data.clock.role} />}
      <Outlet />
    </div>
  )
}
