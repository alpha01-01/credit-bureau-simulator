import { Link } from 'react-router'

import { useGameCommand, useProviders } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, day, money, percent } from '../lib/format'

const COOPERATION_TONE = { cooperative: 'good', lukewarm: 'warn', strained: 'bad' } as const

/**
 * The bureau's providers (P2.6): their recent files and how they cooperate. Feedback
 * and training make their data better over the following months; penalties tighten
 * them up but cost goodwill, and a resentful provider sends its files later.
 */
export function ProvidersPage() {
  const gameId = useGameId()
  const providers = useProviders(gameId)
  const act = useGameCommand(gameId, '/providers/')
  if (providers.isPending) return <Loading what="the providers" />
  if (providers.isError) return <Failed error={providers.error} />
  const p = providers.data
  return (
    <Page
      title="Providers"
      subtitle={`Feedback and training improve a provider's data over the following months. A training session costs ${money(p.training_cost)}. Penalties work too, but providers resent them: a strained one sends its files later.`}
    >
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      {p.providers.map((provider) => (
        <Card key={provider.code} title={`${provider.name} (${provider.code})`}>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
            <Badge tone={COOPERATION_TONE[provider.cooperation]}>{provider.cooperation}</Badge>
            <button
              type="button"
              disabled={act.isPending || provider.trained_this_month}
              onClick={() => act.mutate({ action: 'train', provider: provider.code })}
              className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
            >
              {provider.trained_this_month
                ? 'Training booked this month'
                : 'Book a training session'}
            </button>
            <button
              type="button"
              disabled={act.isPending}
              onClick={() => act.mutate({ action: 'penalise', provider: provider.code })}
              className="rounded border border-red-200 px-2 py-1 text-red-800 hover:bg-red-50 disabled:opacity-50"
            >
              Impose an SLA penalty
            </button>
            {provider.penalties_this_month > 0 && (
              <span className="text-xs text-slate-500">
                {provider.penalties_this_month} penalty(ies) this month
              </span>
            )}
          </div>
          {provider.recent.length === 0 ? (
            <p className="text-sm text-slate-500">No files yet.</p>
          ) : (
            <Table head={['Period', 'Received', 'Days late', 'Records', 'Unloadable', 'Feedback']}>
              {provider.recent.map((s) => (
                <tr key={s.reference}>
                  <Td>
                    <Link
                      to={`/games/${gameId}/submissions/${s.reference}`}
                      className="text-brand hover:underline"
                    >
                      {day(s.period)}
                    </Link>
                  </Td>
                  <Td>{day(s.received_at)}</Td>
                  <Td right>{s.days_late > 0 ? count(s.days_late) : 'on time'}</Td>
                  <Td right>{count(s.records)}</Td>
                  <Td right>{s.records ? percent((s.unloadable ?? 0) / s.records) : '—'}</Td>
                  <Td>{s.feedback_sent ? <Badge tone="good">sent</Badge> : 'not sent'}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      ))}
    </Page>
  )
}
