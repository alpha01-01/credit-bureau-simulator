import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { apiPost } from '../api/client'
import {
  type Catalogue,
  type GameSummary,
  type Parameters,
  type World,
  useCatalogue,
  useGames,
  useWorlds,
} from '../api/game'
import { formatClock, money } from '../lib/format'
import { Card, Empty, Failed, Loading, Page } from '../components/ui'

const SCENARIO_NAME = { ESTABLISHED: 'Established', STARTUP: 'Startup', SANDBOX: 'Sandbox' }
const DIFFICULTY_NAME = { BEGINNER: 'Beginner', INTERMEDIATE: 'Intermediate', EXPERT: 'Expert' }

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
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-brand"
            >
              <span className="font-medium">
                {g.bureau} <span className="text-slate-400">#{g.id}</span>
                <span className="ml-2 text-xs font-normal text-slate-500">
                  {SCENARIO_NAME[g.scenario]} · {DIFFICULTY_NAME[g.difficulty]}
                </span>
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

type Form = {
  world: number | ''
  scenario: GameSummary['scenario']
  difficulty: GameSummary['difficulty']
  months: number
  cash: string
  quality: number
  economy: string
  scale: string
}

const select = 'mt-1 rounded border border-slate-300 px-2 py-1.5'

function NewGame() {
  const worlds = useWorlds()
  const catalogue = useCatalogue()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState<Form>({
    world: '',
    scenario: 'ESTABLISHED',
    difficulty: 'INTERMEDIATE',
    months: 12,
    cash: '',
    quality: 0,
    economy: '',
    scale: '',
  })
  const set = (change: Partial<Form>) => setForm({ ...form, ...change })
  const create = useMutation({
    mutationFn: () =>
      apiPost<GameSummary>('/games/', {
        world: Number(form.world),
        scenario: form.scenario,
        difficulty: form.difficulty,
        history_months: form.scenario === 'STARTUP' ? 0 : form.months,
        settings:
          form.scenario === 'SANDBOX'
            ? {
                starting_cash: form.cash || null,
                provider_quality: form.quality || null,
                economy: form.economy || null,
                scale: form.scale || null,
              }
            : {},
      }),
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
  if (catalogue.isPending) return <Loading what="the scenarios" />
  if (catalogue.isError) return <Failed error={catalogue.error} />
  const cat = catalogue.data
  const difficulty = cat.difficulties.find((d) => d.code === form.difficulty)
  const chosen = worlds.data?.find((w) => w.id === form.world)
  const economy =
    form.scenario === 'SANDBOX' && form.economy ? form.economy : difficulty?.parameters.economy
  const scale = form.scenario === 'SANDBOX' && form.scale ? form.scale : chosen?.scale
  const needsWorld =
    chosen !== undefined &&
    !worlds.data?.some((w) => w.seed === chosen.seed && w.scale === scale && w.economy === economy)

  return (
    <Card title="New game">
      <form
        className="space-y-4 text-sm"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <fieldset>
          <legend className="font-medium text-slate-700">Scenario</legend>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {cat.scenarios.map((s) => (
              <label
                key={s.code}
                className={`cursor-pointer rounded-lg border p-3 ${
                  form.scenario === s.code
                    ? 'border-brand bg-brand/5'
                    : 'border-slate-200 hover:border-slate-400'
                }`}
              >
                <input
                  type="radio"
                  name="scenario"
                  className="mr-2"
                  checked={form.scenario === s.code}
                  onChange={() => set({ scenario: s.code })}
                />
                <span className="font-medium">{s.name}</span>
                <span className="mt-1 block text-xs text-slate-600">{s.does}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-start gap-4">
          <label>
            <span className="block text-slate-600">Difficulty</span>
            <select
              className={select}
              value={form.difficulty}
              onChange={(e) => set({ difficulty: e.target.value as Form['difficulty'] })}
            >
              {cat.difficulties.map((d) => (
                <option key={d.code} value={d.code}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          {difficulty && (
            <div className="max-w-xl text-xs text-slate-600">
              <p>{difficulty.does}</p>
              <DifficultyFacts
                p={difficulty.parameters}
                startup={form.scenario === 'STARTUP'}
                capital={cat.startup_capital}
              />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label>
            <span className="block text-slate-600">World</span>
            <select
              className={select}
              value={form.world}
              onChange={(e) => set({ world: Number(e.target.value) })}
              required
            >
              <option value="">Choose…</option>
              {worlds.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {worldLabel(w, cat)}
                </option>
              ))}
            </select>
          </label>
          {form.scenario !== 'STARTUP' && (
            <label>
              <span className="block text-slate-600">Bureau history</span>
              <select
                className={select}
                value={form.months}
                onChange={(e) => set({ months: Number(e.target.value) })}
              >
                <option value={12}>12 months (slow to prepare the first time)</option>
                <option value={3}>3 months</option>
                <option value={0}>None: set up the day play begins</option>
              </select>
            </label>
          )}
        </div>

        {form.scenario === 'SANDBOX' && <SandboxSettings form={form} set={set} cat={cat} />}

        {needsWorld && (
          <p className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-900">
            No stored world of seed {chosen.seed} and size {scale} has this economy yet. One will be
            built first with the same history: a few minutes for a full-size world, more if the
            bureau's history must be prepared too.
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={create.isPending || form.world === ''}
            className="rounded bg-brand px-3 py-2 font-medium text-white disabled:opacity-60"
          >
            {create.isPending ? 'Starting…' : 'Start game'}
          </button>
          {create.error && <Failed error={create.error} />}
        </div>
      </form>
    </Card>
  )
}

function worldLabel(w: World, cat: Catalogue): string {
  const name = cat.economies.find((e) => e.code === w.economy) ? economyName(w.economy) : w.economy
  return `World ${w.id} (seed ${w.seed}, ${w.scale}, ${name.toLowerCase()} economy)`
}

function economyName(code: string): string {
  return (
    {
      GENTLE: 'Gentle',
      STANDARD: 'Standard',
      HARSH: 'Harsh',
      INTERMEDIATE_NOW: 'Inflation from the start',
      ADVANCED_NOW: 'Everything from the start',
      STILL: 'Still',
      CUSTOM: 'Custom',
    }[code] ?? code
  )
}

function DifficultyFacts({
  p,
  startup,
  capital,
}: {
  p: Parameters
  startup: boolean
  capital: string
}) {
  const adjustment = Number(p.cash_adjustment)
  const cash = startup
    ? `Capital ${money(Number(capital) + adjustment)}`
    : adjustment === 0
      ? 'Cash as the bureau has it'
      : adjustment > 0
        ? `${money(adjustment)} more cash`
        : `${money(-adjustment)} less cash`
  return (
    <ul className="mt-1 list-disc pl-4">
      <li>{cash}</li>
      <li>Supplier prices ×{Number(p.cost_factor).toFixed(2)}</li>
      <li>
        Work items due in {p.work_item_days} working days; hosting suspended{' '}
        {p.supplier_patience_days} working days after a bill is due
      </li>
      <li>Overdraft {money(p.overdraft_limit)}</li>
      <li>
        The board removes you after{' '}
        {p.board_patience === 1 ? 'one review' : `${p.board_patience} reviews in a row`} with no
        confidence
      </li>
      <li>{economyName(p.economy)} economy</li>
    </ul>
  )
}

function SandboxSettings({
  form,
  set,
  cat,
}: {
  form: Form
  set: (change: Partial<Form>) => void
  cat: Catalogue
}) {
  return (
    <fieldset className="rounded-lg border border-slate-200 p-3">
      <legend className="px-1 font-medium text-slate-700">Sandbox settings</legend>
      <p className="text-xs text-slate-600">
        Left blank, each takes the difficulty's value or the chosen world's.
      </p>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label>
          <span className="block text-slate-600">World size</span>
          <select
            className={select}
            value={form.scale}
            onChange={(e) => set({ scale: e.target.value })}
          >
            <option value="">As the world chosen</option>
            {cat.scales.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="block text-slate-600">Starting cash (GHS)</span>
          <input
            type="number"
            min={0}
            step={50000}
            className={`${select} w-40`}
            value={form.cash}
            onChange={(e) => set({ cash: e.target.value })}
            placeholder="As set up"
          />
        </label>
        <label>
          <span className="block text-slate-600">Providers' data quality</span>
          <select
            className={select}
            value={form.quality}
            onChange={(e) => set({ quality: Number(e.target.value) })}
          >
            {Array.from({ length: cat.max_provider_quality + 1 }, (_, n) => (
              <option key={n} value={n}>
                {n === 0 ? 'As usual' : `${n} step${n > 1 ? 's' : ''} better`}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="block text-slate-600">Economy</span>
          <select
            className={select}
            value={form.economy}
            onChange={(e) => set({ economy: e.target.value })}
          >
            <option value="">The difficulty's</option>
            {cat.economies.map((e) => (
              <option key={e.code} value={e.code}>
                {economyName(e.code)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {form.economy && (
        <p className="mt-2 text-xs text-slate-600">
          {cat.economies.find((e) => e.code === form.economy)?.does}
        </p>
      )}
    </fieldset>
  )
}
