import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { apiGet } from '../api/client'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'

type EconomyData = {
  staged: boolean
  stage: 'INITIAL' | 'INTERMEDIATE' | 'ADVANCED'
  price_factor: string
  wage_factor: string
  rules: Record<string, string>
  months: {
    period: string
    stage: string
    inflation: number
    policy_rate: number | null
    growth: number | null
    price_index: number
    wage_index: number
    events: string[]
  }[]
}

const STAGE = {
  INITIAL: ['neutral', 'Initial: costs and prices'],
  INTERMEDIATE: ['warn', 'Intermediate: inflation, interest rates, wages'],
  ADVANCED: ['bad', 'Advanced: cycles and shocks'],
} as const

const EVENT: Record<string, string> = {
  SHOCK: 'shock',
  INTERMEDIATE: 'inflation begins',
  ADVANCED: 'advanced stage',
}

const pct = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)}%`)

function Why({ rule }: { rule: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span>
      <button
        type="button"
        className="text-xs text-brand underline"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Why?
      </button>
      {open && <span className="mt-1 block text-xs font-normal text-slate-600">{rule}</span>}
    </span>
  )
}

/**
 * The economy (P3.12): the published indicators only, never the world's own state.
 * Each figure has the rule that sets it.
 */
export function EconomyPage() {
  const gameId = useGameId()
  const data = useQuery({
    queryKey: [gameId, 'economy'],
    queryFn: () => apiGet<EconomyData>(`/games/${gameId}/economy/`),
  })
  if (data.isPending) return <Loading what="the economy" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const [tone, label] = STAGE[d.stage]
  const latest = d.months[d.months.length - 1]
  return (
    <Page
      title="Economy"
      subtitle="Published figures, released at the start of each month for the month before."
    >
      {!d.staged && (
        <p className="text-sm text-slate-600">
          This world was made before the economy had stages: prices, rates and wages hold still in
          it. A game in a newer world goes through all of them.
        </p>
      )}
      <Card title="Where things stand">
        <div className="flex flex-wrap items-start gap-6 text-sm">
          <div>
            <p className="text-slate-500">Stage</p>
            <Badge tone={tone}>{label}</Badge>
            <div>
              <Why rule={d.rules.stage} />
            </div>
          </div>
          <div>
            <p className="text-slate-500">Prices since play began</p>
            <p className="text-xl font-semibold">×{Number(d.price_factor).toFixed(3)}</p>
            <Why rule={d.rules.inflation} />
          </div>
          <div>
            <p className="text-slate-500">Wages since play began</p>
            <p className="text-xl font-semibold">×{Number(d.wage_factor).toFixed(3)}</p>
            <Why rule={d.rules.wages} />
          </div>
          {latest && (
            <>
              <div>
                <p className="text-slate-500">Policy rate</p>
                <p className="text-xl font-semibold">{pct(latest.policy_rate)}</p>
                <Why rule={d.rules.policy_rate} />
              </div>
              <div>
                <p className="text-slate-500">Growth</p>
                <p className="text-xl font-semibold">{pct(latest.growth)}</p>
                <Why rule={d.rules.growth} />
              </div>
            </>
          )}
        </div>
      </Card>
      <Card title="Month by month">
        {d.months.length === 0 ? (
          <Empty>Nothing published yet.</Empty>
        ) : (
          <Table head={['Month', 'Inflation', 'Policy rate', 'Growth', 'Prices', 'Wages', '']}>
            {[...d.months].reverse().map((m) => (
              <tr key={m.period}>
                <Td>{m.period.slice(0, 7)}</Td>
                <Td right>{pct(m.inflation)}</Td>
                <Td right>{pct(m.policy_rate)}</Td>
                <Td right>{pct(m.growth)}</Td>
                <Td right>×{m.price_index.toFixed(3)}</Td>
                <Td right>×{m.wage_index.toFixed(3)}</Td>
                <Td>
                  {m.events.map((e) => (
                    <Badge key={e} tone={e === 'SHOCK' ? 'bad' : 'warn'}>
                      {EVENT[e] ?? e}
                    </Badge>
                  ))}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  )
}
