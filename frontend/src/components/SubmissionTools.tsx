import { useState } from 'react'

import type { FeedbackReport, FileMappingOffer } from '../api/game'
import { useFeedback, useGameCommand } from '../api/game'
import { count, dateTime } from '../lib/format'
import { Badge, Card, Table, Td } from './ui'

/**
 * Template mapping (P2.5): the provider changed its column layout, so the file was
 * rejected (T001). Say which template column each received header is; the mapping
 * is kept for this provider and the file is loaded.
 */
export function MappingForm({
  gameId,
  reference,
  fileName,
  offer,
}: {
  gameId: number
  reference: string
  fileName: string
  offer: FileMappingOffer
}) {
  const save = useGameCommand(gameId, `/submissions/${reference}/files/${fileName}/mapping/`)
  const [chosen, setChosen] = useState<string[]>(offer.suggested)
  const used = chosen.filter(Boolean)
  const repeated = new Set(used.filter((c, i) => used.indexOf(c) !== i))
  const missing = offer.template.filter((c) => !chosen.includes(c))
  const ready = missing.length === 0 && repeated.size === 0
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ columns: chosen })
      }}
    >
      <p className="text-sm text-slate-600">
        <span className="font-medium">{fileName}</span> was rejected because its columns do not
        match the template: the provider has changed its layout. Say which template column each
        received header is. The bureau has suggested what it is sure of; the mapping is kept for
        this provider&apos;s later files.
      </p>
      <div className="max-h-96 overflow-y-auto rounded border border-slate-200">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                #
              </th>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Received header
              </th>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Template column
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {offer.received.map((name, i) => {
              const value = chosen[i]
              const problem = !value || repeated.has(value)
              return (
                <tr key={i} className={problem ? 'bg-amber-50' : undefined}>
                  <Td>{i + 1}</Td>
                  <Td>
                    <code>{name}</code>
                  </Td>
                  <Td>
                    <label className="sr-only" htmlFor={`map-${i}`}>
                      Template column for {name}
                    </label>
                    <select
                      id={`map-${i}`}
                      value={value}
                      onChange={(e) =>
                        setChosen(chosen.map((c, j) => (j === i ? e.target.value : c)))
                      }
                      className="rounded border border-slate-300 px-1 py-0.5"
                    >
                      <option value="">Choose…</option>
                      {offer.template.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    {value && value !== name && value !== offer.suggested[i] && (
                      <span className="ml-2 text-xs text-slate-500">changed</span>
                    )}
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button
          type="submit"
          disabled={!ready || save.isPending}
          className="rounded bg-brand px-3 py-1.5 font-medium text-white disabled:opacity-50"
        >
          Save mapping and load the file
        </button>
        {!ready && (
          <span className="text-slate-600">
            {missing.length > 0 && `Not yet mapped: ${missing.join(', ')}. `}
            {repeated.size > 0 && `Used twice: ${[...repeated].join(', ')}.`}
          </span>
        )}
        {save.isError && (
          <span role="alert" className="text-red-700">
            {save.error.message}
          </span>
        )}
      </div>
    </form>
  )
}

/** The feedback report for the provider: what was rejected and why (P2.5). */
export function FeedbackCard({ gameId, reference }: { gameId: number; reference: string }) {
  const report = useFeedback(gameId, reference)
  const send = useGameCommand<FeedbackReport>(gameId, `/submissions/${reference}/feedback/`)
  if (!report.data) return null
  const r = report.data
  return (
    <Card title="Feedback to the provider">
      <div className="space-y-3 text-sm">
        <p>
          {count(r.files_rejected)} file(s) rejected; {count(r.records_unloadable)} record(s) could
          not be loaded and should be resent; {count(r.records_with_warnings)} loaded with a
          warning.
        </p>
        {r.rules.length > 0 && (
          <Table head={['Rule', 'Problem', 'Records']}>
            {r.rules.map((rule) => (
              <tr key={rule.rule}>
                <Td>{rule.rule}</Td>
                <Td>{rule.description}</Td>
                <Td right>{count(rule.records)}</Td>
              </tr>
            ))}
          </Table>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => send.mutate({})}
            disabled={send.isPending}
            className="rounded border border-slate-300 px-3 py-1 font-medium hover:bg-slate-50 disabled:opacity-50"
          >
            Send to the provider
          </button>
          <a
            href={`/api/v1/games/${gameId}/submissions/${reference}/feedback/?download=csv`}
            className="text-brand hover:underline"
          >
            Download the records to resend (CSV)
          </a>
          {r.sent.length > 0 ? (
            <Badge tone="good">sent {dateTime(r.sent[0])}</Badge>
          ) : (
            <Badge>not sent yet</Badge>
          )}
        </div>
        {send.isError && (
          <p role="alert" className="text-red-700">
            {send.error.message}
          </p>
        )}
      </div>
    </Card>
  )
}
