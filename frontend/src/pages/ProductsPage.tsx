import { useGameCommand } from '../api/game'
import { useProducts } from '../api/managed'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page } from '../components/ui'
import { day, money } from '../lib/format'

const BUTTON =
  'rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

const STATUS = {
  AVAILABLE: ['neutral', 'not developed'],
  IN_DEVELOPMENT: ['info', 'in development'],
  LAUNCHED: ['good', 'on sale'],
} as const

/**
 * Product Development (P3.10, managed): a product is developed, at a cost and over
 * time, before it can be sold.
 */
export function ProductsPage() {
  const gameId = useGameId()
  const data = useProducts(gameId)
  const act = useGameCommand(gameId, '/products/')
  if (data.isPending) return <Loading what="products" />
  if (data.isError) return <Failed error={data.error} />
  return (
    <Page
      title="Product Development"
      subtitle="A product must be developed before it can be sold. The work is contracted out and billed when it starts."
    >
      {act.error && <Failed error={act.error} />}
      {data.data.products.map((p) => {
        const [tone, word] = STATUS[p.status]
        return (
          <Card key={p.code} title={p.name}>
            <div className="space-y-2 text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <Badge tone={tone}>{word}</Badge>
                {p.status === 'IN_DEVELOPMENT' && (
                  <span>
                    started {day(p.started_on)}, ready {day(p.ready_on)}
                  </span>
                )}
                {p.status === 'LAUNCHED' && <span>since {day(p.launched_on)}</span>}
              </p>
              <p className="text-slate-700">{p.does}</p>
              {p.status === 'AVAILABLE' && (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-slate-600">
                    {money(p.cost)}, {p.working_days} working days
                  </span>
                  <button
                    type="button"
                    className={BUTTON}
                    disabled={act.isPending}
                    onClick={() => act.mutate({ code: p.code })}
                  >
                    Develop it
                  </button>
                </div>
              )}
            </div>
          </Card>
        )
      })}
    </Page>
  )
}
