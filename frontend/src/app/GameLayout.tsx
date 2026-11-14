import { NavLink, Outlet } from 'react-router'

import { useGame } from '../api/game'
import { ClockBar } from '../components/ClockBar'
import { Failed, Loading } from '../components/ui'
import { useGameId } from './useGameId'

const NAV = [
  ['', 'Briefing'],
  ['dashboard', 'Dashboard'],
  ['submissions', 'Submissions'],
  ['queue', 'Work queue'],
  ['customers', 'Customers'],
  ['enquiries', 'Enquiries'],
  ['finance', 'Finance'],
] as const

export function GameLayout() {
  const gameId = useGameId()
  const game = useGame(gameId)

  if (game.isPending) return <Loading what="the game" />
  if (game.isError) return <Failed error={game.error} />

  const data = game.data
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
      <div className="sticky top-0 z-10 -mx-4 border-b border-slate-200 bg-paper/95 px-4 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-semibold">{data.bureau}</span>
          <ClockBar gameId={gameId} clock={data.clock} />
        </div>
        <nav aria-label="Game" className="mt-3 flex flex-wrap gap-1">
          {NAV.map(([path, label]) => (
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
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </div>
  )
}
