import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { apiPost } from '../api/client'
import { type GameSummary, useGames, useWorlds } from '../api/game'
import { formatClock } from '../lib/format'
import { Card, Empty, Failed, Loading, Page } from '../components/ui'

export function GamesPage() {
  const games = useGames()
  return (
    <Page
      title="Your games"
      subtitle="Each game is a credit bureau operating in a simulated Ghana."
    >
      <NewGame />
      {games.isPending && <Loading what="games" />}
      {games.isError && <Failed error={games.error} />}
      {games.data && games.data.length === 0 && <Empty>No games yet.</Empty>}
      <ul className="space-y-2">
        {games.data?.map((g) => (
          <li key={g.id}>
            <Link
              to={`/games/${g.id}`}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-brand"
            >
              <span className="font-medium">
                {g.bureau} <span className="text-slate-400">#{g.id}</span>
              </span>
              <span className="text-sm text-slate-500">
                {g.clock ? formatClock(g.clock) : g.setup_message || g.setup_status}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  )
}

function NewGame() {
  const worlds = useWorlds()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [world, setWorld] = useState<number | ''>('')
  const [months, setMonths] = useState(12)
  const create = useMutation({
    mutationFn: () =>
      apiPost<GameSummary>('/games/', { world: Number(world), history_months: months }),
    onSuccess: (game) => {
      void client.invalidateQueries({ queryKey: ['games'] })
      navigate(`/games/${game.id}`)
    },
  })

  if (worlds.data?.length === 0) {
    return (
      <Card title="New game">
        <p className="text-sm text-slate-600">
          No world yet. Generate one with{' '}
          <code className="rounded bg-slate-100 px-1">manage.py generate_world --seed 42</code>.
        </p>
      </Card>
    )
  }
  return (
    <Card title="New game">
      <form
        className="flex flex-wrap items-end gap-3 text-sm"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <label>
          <span className="block text-slate-600">World</span>
          <select
            className="mt-1 rounded border border-slate-300 px-2 py-1.5"
            value={world}
            onChange={(e) => setWorld(Number(e.target.value))}
            required
          >
            <option value="">Choose…</option>
            {worlds.data?.map((w) => (
              <option key={w.id} value={w.id}>
                World {w.id} (seed {w.seed}, {w.scale})
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="block text-slate-600">Bureau history</span>
          <select
            className="mt-1 rounded border border-slate-300 px-2 py-1.5"
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
          >
            <option value={12}>Established: 12 months (slow to prepare)</option>
            <option value={3}>3 months</option>
            <option value={0}>None: a new bureau</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={create.isPending || world === ''}
          className="rounded bg-brand px-3 py-2 font-medium text-white disabled:opacity-60"
        >
          {create.isPending ? 'Starting…' : 'Start game'}
        </button>
        {create.error && <Failed error={create.error} />}
      </form>
    </Card>
  )
}
