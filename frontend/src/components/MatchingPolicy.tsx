import { useState } from 'react'

import type { MatchingPolicy } from '../api/game'
import { useGameCommand, useMatchingPolicy } from '../api/game'
import { money } from '../lib/format'

const LEVEL_LABEL: Record<string, string> = {
  BASIC: 'Basic',
  STANDARD: 'Standard',
  ADVANCED: 'Advanced',
}

/**
 * Customer matching (P2.4): the tooling the bureau pays for, and its thresholds.
 * Lower thresholds link more records automatically (fewer false splits, more false
 * merges); higher ones send more to the queue and create more new customers.
 */
export function MatchingPolicyCard({ gameId }: { gameId: number }) {
  const policy = useMatchingPolicy(gameId)
  const change = useGameCommand<MatchingPolicy>(gameId, '/matching-policy/')
  // Unsaved edits only; otherwise the saved thresholds are shown.
  const [draft, setDraft] = useState<{ autoLink?: string; review?: string }>({})

  if (!policy.data) return null
  const p = policy.data
  const autoLink = draft.autoLink ?? p.auto_link.toFixed(2)
  const review = draft.review ?? p.review.toFixed(2)
  const dirty = autoLink !== p.auto_link.toFixed(2) || review !== p.review.toFixed(2)
  return (
    <section
      aria-labelledby="matching-title"
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm"
    >
      <h2 id="matching-title" className="font-semibold text-slate-700">
        Customer matching
      </h2>
      <fieldset className="space-y-1" disabled={change.isPending}>
        <legend className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Tooling
        </legend>
        {p.options.map((o) => (
          <label key={o.level} className="flex flex-wrap items-center gap-2">
            <input
              type="radio"
              name="matching-tooling"
              checked={p.tooling === o.level}
              onChange={() => change.mutate({ tooling: o.level })}
            />
            <span className="font-medium">{LEVEL_LABEL[o.level] ?? o.level}</span>
            <span className="text-slate-500">
              {o.description};{' '}
              {Number(o.monthly_cost) ? `${money(o.monthly_cost)} a month` : 'no charge'}
            </span>
          </label>
        ))}
      </fieldset>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          change.mutate(
            { auto_link: Number(autoLink), review: Number(review) },
            { onSuccess: () => setDraft({}) },
          )
        }}
      >
        <label className="flex flex-col text-xs text-slate-500">
          Link automatically at
          <input
            type="number"
            min="0.5"
            max="1"
            step="0.01"
            value={autoLink}
            onChange={(e) => setDraft({ ...draft, autoLink: e.target.value })}
            className="mt-1 w-24 rounded border border-slate-300 px-2 py-1 text-sm text-slate-900"
          />
        </label>
        <label className="flex flex-col text-xs text-slate-500">
          Hold for review from
          <input
            type="number"
            min="0.5"
            max="1"
            step="0.01"
            value={review}
            onChange={(e) => setDraft({ ...draft, review: e.target.value })}
            className="mt-1 w-24 rounded border border-slate-300 px-2 py-1 text-sm text-slate-900"
          />
        </label>
        <button
          type="submit"
          disabled={!dirty || change.isPending}
          className="rounded border border-slate-300 px-3 py-1 font-medium hover:bg-slate-50 disabled:opacity-50"
        >
          Save thresholds
        </button>
      </form>
      <p className="text-xs text-slate-500">
        Records closer than the first number are linked without a reviewer; between the two they
        come to this queue; below, they become new customers. Lower numbers mean fewer duplicate
        customers but more people wrongly merged. Applies to files processed from now on; the
        monthly Data Quality Review shows the result.
      </p>
      {change.isError && (
        <p role="alert" className="text-xs text-red-700">
          {change.error.message}
        </p>
      )}
    </section>
  )
}
