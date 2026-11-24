import { useState } from 'react'
import { Link } from 'react-router'

import { useGameCommand, useSales } from '../api/game'
import type { SalesData } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { dateTime, day, money, percent } from '../lib/format'
import { termsLine } from '../lib/terms'

const STATUS_TONE = {
  PENDING: 'info',
  ACCEPTED: 'good',
  DECLINED: 'bad',
  COUNTERED: 'warn',
  LAPSED: 'neutral',
} as const

const SMALL =
  'rounded border border-slate-300 px-2 py-0.5 text-sm hover:bg-slate-50 disabled:opacity-50'
const FIELD = 'w-28 rounded border border-slate-300 px-1 py-0.5 text-sm'

type Offer = {
  price: string
  term_months: number
  service_level: 'STANDARD' | 'PREMIUM'
  monthly_minimum: string
  discount_rate: string
  discount_threshold: string
}

const BLANK: Offer = {
  price: '',
  term_months: 12,
  service_level: 'STANDARD',
  monthly_minimum: '',
  discount_rate: '',
  discount_threshold: '',
}

function Research({
  p,
  s,
  act,
}: {
  p: SalesData['prospects'][number]
  s: SalesData
  act: ReturnType<typeof useGameCommand>
}) {
  const r = p.research
  if (!r)
    return (
      <button
        type="button"
        className={SMALL}
        disabled={act.isPending}
        onClick={() => act.mutate({ action: 'research', lender: p.code })}
      >
        Research ({s.research_days} days)
      </button>
    )
  if (!r.findings) return <span className="text-xs text-slate-500">due {day(r.ready_on)}</span>
  return (
    <div className="space-y-1 text-xs">
      <p>
        About {r.findings.volume} applications a month; values {r.findings.values}.
      </p>
      {r.meeting ? (
        <p className="text-slate-700">
          Met {day(r.meeting_on)}: “{r.meeting.said}”
          {r.met_recently && <Badge tone="good">goodwill</Badge>}
        </p>
      ) : r.meeting_on ? (
        <p className="text-slate-500">Meeting on {day(r.meeting_on)}</p>
      ) : (
        <button
          type="button"
          className={SMALL}
          disabled={act.isPending}
          onClick={() => act.mutate({ action: 'meet', lender: p.code })}
        >
          Arrange a meeting ({s.meeting_days} days)
        </button>
      )}
    </div>
  )
}

/**
 * Sales (P2.9, P3.9): research a lender's needs, meet it, then negotiate the price,
 * term, service level, a monthly minimum and a volume discount. A signed lender goes on
 * to Onboarding, where each department takes it on in turn.
 */
export function SalesPage() {
  const gameId = useGameId()
  const sales = useSales(gameId)
  const act = useGameCommand(gameId, '/sales/')
  const [lender, setLender] = useState<string | null>(null)
  const [offer, setOffer] = useState<Offer>(BLANK)
  if (sales.isPending) return <Loading what="sales" />
  if (sales.isError) return <Failed error={sales.error} />
  const s = sales.data
  const track =
    s.reputation.enquiries === 0
      ? 'no checks in the last three months to judge us by'
      : `hit rate ${percent(s.reputation.hit_rate)}, right person ${percent(s.reputation.accuracy)}`
  const names = Object.fromEntries(s.prospects.map((p) => [p.code, p.name]))
  for (const sub of s.subscribers) names[sub.code] = sub.name
  const chosen = s.prospects.find((p) => p.code === lender)
  const set = (patch: Partial<Offer>) => setOffer({ ...offer, ...patch })
  const send = () => {
    act.mutate(
      {
        action: 'propose',
        lender,
        price: offer.price || s.list_price,
        term_months: offer.term_months,
        service_level: offer.service_level,
        monthly_minimum: offer.monthly_minimum || '0',
        discount_rate: offer.discount_rate ? String(Number(offer.discount_rate) / 100) : '0',
        discount_threshold: offer.discount_threshold || null,
      },
      { onSuccess: () => setLender(null) },
    )
  }
  return (
    <Page
      title="Sales"
      subtitle={`Lenders answer a proposal in ${s.answer_days} working days. They weigh our reputation with subscribers, now ${s.reputation.score} out of 100 (${track}), against how well the terms suit them; our list price is ${money(s.list_price)} a report.`}
    >
      {act.isError && (
        <p role="alert" className="text-sm text-red-700">
          {act.error.message}
        </p>
      )}
      <Card title="Lenders we could sign">
        {s.prospects.length === 0 ? (
          <Empty>Every lender in the market subscribes or is being taken on.</Empty>
        ) : (
          <Table head={['Lender', 'Type', 'What we know', '']}>
            {s.prospects.map((p) => (
              <tr key={p.code}>
                <Td>
                  {p.name} <span className="text-xs text-slate-500">{p.code}</span>
                </Td>
                <Td>{p.type.toLowerCase().replaceAll('_', ' ')}</Td>
                <Td>
                  <Research p={p} s={s} act={act} />
                </Td>
                <Td>
                  {p.waiting ? (
                    <Badge tone="info">waiting for an answer</Badge>
                  ) : (
                    <button
                      type="button"
                      className={SMALL}
                      onClick={() => {
                        setLender(p.code)
                        setOffer(BLANK)
                      }}
                    >
                      Make an offer
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {chosen && (
        <Card title={`Offer to ${chosen.name}`}>
          <form
            className="grid gap-3 text-sm sm:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
          >
            <label className="space-y-1">
              <span className="block text-slate-600">Price per report (GHS)</span>
              <input
                className={FIELD}
                inputMode="decimal"
                placeholder={s.list_price}
                value={offer.price}
                onChange={(e) => set({ price: e.target.value })}
              />
            </label>
            <label className="space-y-1">
              <span className="block text-slate-600">Term</span>
              <select
                className={FIELD}
                value={offer.term_months}
                onChange={(e) => set({ term_months: Number(e.target.value) })}
              >
                <option value={12}>12 months</option>
                <option value={24}>24 months</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="block text-slate-600">Service level</span>
              <select
                className={FIELD}
                value={offer.service_level}
                onChange={(e) => set({ service_level: e.target.value as Offer['service_level'] })}
              >
                <option value="STANDARD">Standard</option>
                <option value="PREMIUM">Premium (credit for long downtime)</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="block text-slate-600">Monthly minimum (GHS)</span>
              <input
                className={FIELD}
                inputMode="decimal"
                placeholder="none"
                value={offer.monthly_minimum}
                onChange={(e) => set({ monthly_minimum: e.target.value })}
              />
            </label>
            <label className="space-y-1">
              <span className="block text-slate-600">Volume discount (%)</span>
              <input
                className={FIELD}
                inputMode="decimal"
                placeholder="none"
                value={offer.discount_rate}
                onChange={(e) => set({ discount_rate: e.target.value })}
              />
            </label>
            <label className="space-y-1">
              <span className="block text-slate-600">…on reports above (a month)</span>
              <input
                className={FIELD}
                inputMode="numeric"
                placeholder="0"
                value={offer.discount_threshold}
                onChange={(e) => set({ discount_threshold: e.target.value })}
              />
            </label>
            <div className="flex gap-2 sm:col-span-3">
              <button type="submit" className={SMALL} disabled={act.isPending}>
                Send the proposal
              </button>
              <button type="button" className={SMALL} onClick={() => setLender(null)}>
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}
      <Card title="Proposals">
        {s.proposals.length === 0 ? (
          <Empty>No proposals sent yet.</Empty>
        ) : (
          <Table head={['Lender', 'Terms', 'Sent', 'Answer', 'Answered']}>
            {s.proposals.map((p) => (
              <tr key={p.number}>
                <Td>{names[p.lender] ?? p.lender}</Td>
                <Td>{termsLine(p)}</Td>
                <Td>{dateTime(p.sent_at)}</Td>
                <Td>
                  <Badge tone={STATUS_TONE[p.status]}>{p.status.toLowerCase()}</Badge>
                  {p.status === 'COUNTERED' && p.counter_price && (
                    <button
                      type="button"
                      className={`${SMALL} ml-2`}
                      disabled={act.isPending}
                      onClick={() => act.mutate({ action: 'accept_counter', number: p.number })}
                    >
                      Accept {money(p.counter_price)}
                    </button>
                  )}
                  {p.status === 'ACCEPTED' && (
                    <Link
                      to={`/games/${gameId}/onboarding`}
                      className="ml-2 text-xs text-brand underline"
                    >
                      onboarding
                    </Link>
                  )}
                </Td>
                <Td>{dateTime(p.answered_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Subscribers">
        <Table head={['Subscriber', 'Since', 'Terms', '']}>
          {s.subscribers.map((sub) => (
            <tr key={sub.code}>
              <Td>{sub.name}</Td>
              <Td>{day(sub.since)}</Td>
              <Td>
                {sub.price && sub.term_months
                  ? termsLine({
                      price: sub.price,
                      term_months: sub.term_months,
                      service_level: sub.service_level ?? 'STANDARD',
                      monthly_minimum: sub.monthly_minimum ?? '0',
                      discount_rate: sub.discount_rate ?? '0',
                      discount_threshold: sub.discount_threshold ?? null,
                    })
                  : money(sub.price)}
              </Td>
              <Td>{sub.active ? <Badge tone="good">active</Badge> : <Badge>left</Badge>}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </Page>
  )
}
