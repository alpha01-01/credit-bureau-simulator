import { Link, useParams, useSearchParams } from 'react-router'

import type { DrillRow, Review, ReviewDrill } from '../api/game'
import { useReview, useReviewDrill, useReviews } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page, Table, Td } from '../components/ui'
import { count, dateTime, months, percent } from '../lib/format'

const RESOLVERS: Record<string, string> = {
  EMPLOYEE: 'Your team',
  PLAYER: 'You',
  HISTORIC: 'Former staff',
}

function monthName(period: string): string {
  return new Date(`${period}-01T00:00:00Z`).toLocaleDateString('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** The list of monthly reviews. */
export function ReviewsPage() {
  const gameId = useGameId()
  const reviews = useReviews(gameId)
  return (
    <Page
      title="Data Quality Reviews"
      subtitle="At the end of each month the game reveals what really happened to your data."
    >
      {reviews.isPending ? (
        <Loading what="the reviews" />
      ) : reviews.isError ? (
        <Failed error={reviews.error} />
      ) : reviews.data.length === 0 ? (
        <Empty>The first review appears at the end of your first month.</Empty>
      ) : (
        <Table
          head={[
            'Month',
            'Match decisions right',
            'False merges',
            'Records not loaded',
            'Wrong reports',
          ]}
        >
          {reviews.data.map((r) => (
            <tr key={r.period}>
              <Td>
                <Link
                  to={`/games/${gameId}/reviews/${r.period}`}
                  className="font-medium text-brand hover:underline"
                >
                  {monthName(r.period)}
                </Link>
              </Td>
              <Td right>
                {count(r.match.right)} of {count(r.match.total)}
              </Td>
              <Td right>{count(r.match.false_merges)}</Td>
              <Td right>
                {count(r.rejected.total)} ({count(r.rejected.genuine)} genuine)
              </Td>
              <Td right>{count(r.consequences)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Page>
  )
}

/** One month's review: every figure opens the records behind it. */
export function ReviewPage() {
  const gameId = useGameId()
  const { period = '' } = useParams()
  const review = useReview(gameId, period)
  const [params, setParams] = useSearchParams()
  const shown = params.get('show')

  if (review.isPending) return <Loading what="the review" />
  if (review.isError) return <Failed error={review.error} />
  const r = review.data
  const can = new Set(r.drill)

  const fig: FigureContext = { can, shown, show: (k) => setParams({ show: k }) }

  return (
    <Page
      title={`Data Quality Review: ${monthName(r.period)}`}
      subtitle="What really happened. Click a number to see the records behind it."
      actions={
        <Link to={`/games/${gameId}/reviews`} className="text-sm text-brand hover:underline">
          All reviews
        </Link>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Decisions r={r} fig={fig} />
        <Rejected r={r} fig={fig} />
      </div>
      <Assets r={r} />
      <Matching r={r} />
      <Chains r={r} gameId={gameId} fig={fig} />
      {shown && <DrillPanel gameId={gameId} period={period} k={shown} />}
    </Page>
  )
}

type FigureContext = { can: Set<string>; shown: string | null; show: (key: string) => void }

/** Labelled figures, each opening its records. */
function FigureList({
  fig,
  title,
  items,
}: {
  fig: FigureContext
  title: string
  items: [string, number, string][]
}) {
  return (
    <div>
      <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</h3>
      <dl className="mt-1 grid grid-cols-[4rem_1fr] gap-x-2 gap-y-0.5">
        {items.map(([k, n, label]) => (
          <div key={k} className="contents">
            <dt className="text-right">
              <Figure fig={fig} k={k} n={n} label={label} />
            </dt>
            <dd>{label}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** A figure: a number that opens its records, when it has any. */
function Figure({ fig, k, n, label }: { fig: FigureContext; k: string; n: number; label: string }) {
  if (n === 0 || !fig.can.has(k))
    return <span className="font-semibold tabular-nums">{count(n)}</span>
  return (
    <button
      type="button"
      onClick={() => fig.show(k)}
      aria-pressed={fig.shown === k}
      aria-label={`${count(n)} ${label}: show the records`}
      className={`rounded px-1 font-semibold tabular-nums underline decoration-dotted underline-offset-4 ${
        fig.shown === k ? 'bg-brand text-white' : 'text-brand hover:bg-slate-100'
      }`}
    >
      {count(n)}
    </button>
  )
}

function Decisions({ r, fig }: { r: Review; fig: FigureContext }) {
  const m = r.figures.match
  const t = r.figures.triage
  return (
    <Card title="Decisions">
      <div className="space-y-3 text-sm">
        <FigureList
          fig={fig}
          title="Match reviews"
          items={[
            ['match.all', m.total, 'resolved'],
            ['match.right', m.right, 'right'],
            ['match.false_merge', m.false_merges, 'false merges: two people made one'],
            ['match.false_split', m.false_splits, 'false splits: one person made two'],
            ['match.other_wrong', m.other_wrong, 'otherwise wrong'],
          ]}
        />
        <FigureList
          fig={fig}
          title="Triage of unloadable records"
          items={[
            ['triage.all', t.total, 'decided'],
            ['triage.right', t.right, 'right'],
            [
              'triage.genuine_returned',
              t.genuine_returned,
              'genuine records sent back to the provider',
            ],
            ['triage.wrongly_loaded', t.wrongly_loaded, 'wrong corrections loaded'],
            ['triage.other_wrong', t.other_wrong, 'otherwise wrong'],
          ]}
        />
        <ByResolver title="Who decided" tallies={{ ...m.by }} other={t.by} />
      </div>
    </Card>
  )
}

function ByResolver({
  title,
  tallies,
  other,
}: {
  title: string
  tallies: Record<string, { total: number; right: number }>
  other: Record<string, { total: number; right: number }>
}) {
  const who = [...new Set([...Object.keys(tallies), ...Object.keys(other)])].sort()
  if (who.length === 0) return null
  return (
    <table className="w-full text-xs">
      <caption className="text-left font-medium text-slate-600">{title}</caption>
      <thead className="text-slate-500">
        <tr>
          <th scope="col" className="py-1 text-left font-normal" />
          <th scope="col" className="py-1 text-right font-normal">
            Matches right
          </th>
          <th scope="col" className="py-1 text-right font-normal">
            Triage right
          </th>
        </tr>
      </thead>
      <tbody>
        {who.map((w) => (
          <tr key={w}>
            <th scope="row" className="py-0.5 text-left font-normal">
              {RESOLVERS[w] ?? w}
            </th>
            <td className="text-right tabular-nums">
              {tallies[w] ? `${tallies[w].right} of ${tallies[w].total}` : '—'}
            </td>
            <td className="text-right tabular-nums">
              {other[w] ? `${other[w].right} of ${other[w].total}` : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Rejected({ r, fig }: { r: Review; fig: FigureContext }) {
  const rej = r.figures.rejected
  return (
    <Card title="Records not loaded">
      {rej.total === 0 ? (
        <p className="text-sm text-slate-500">Every record from this month's files was loaded.</p>
      ) : (
        <div className="space-y-2 text-sm">
          <p>
            {count(rej.total)} records were not loaded; {count(rej.genuine)} of them described real
            accounts (the rest were rows a provider really did send twice).
          </p>
          <table className="w-full text-xs">
            <thead className="text-slate-500">
              <tr>
                <th scope="col" className="py-1 text-left font-normal">
                  Stopped by
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  Genuine
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  Really repeated
                </th>
              </tr>
            </thead>
            <tbody>
              {rej.rules.map((rule) => (
                <tr key={rule.rule} className="align-top">
                  <th scope="row" className="py-1 pr-2 text-left font-normal">
                    <span className="font-mono">{rule.rule}</span> {rule.description}
                  </th>
                  <td className="text-right">
                    <Figure
                      fig={fig}
                      k={`rejected.${rule.rule}.genuine`}
                      n={rule.genuine}
                      label="genuine records"
                    />
                  </td>
                  <td className="text-right">
                    <Figure
                      fig={fig}
                      k={`rejected.${rule.rule}.repeated`}
                      n={rule.records - rule.genuine}
                      label="repeated rows"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function Assets({ r }: { r: Review }) {
  const { visible: v, truth: t } = r.figures.assets
  const est = (share: number | null, margin: number | null) =>
    share === null ? '—' : `${percent(share)} ± ${((margin ?? 0) * 100).toFixed(1)} pts`
  const rows: [string, string, string][] = [
    ['Coverage', percent(v.coverage.share), 'seen directly'],
    ['Depth', months(v.depth_months), 'seen directly'],
    ['Freshness', v.freshness_days === null ? '—' : `${v.freshness_days} days`, 'seen directly'],
    [
      'Accuracy',
      est(v.audit.accuracy.share, v.audit.accuracy.margin),
      `${percent(t.accuracy.share)}: ${count(t.accuracy.right)} of ${count(t.accuracy.accounts)} accounts right`,
    ],
    [
      'One person per customer',
      est(v.audit.one_person.share, v.audit.one_person.margin),
      `${count(t.identity.false_merges)} of ${count(t.identity.customers)} customers are two or more people (${percent(t.identity.merge_rate)})`,
    ],
    [
      'One customer per person',
      'not estimated',
      `${count(t.identity.false_splits)} of ${count(t.identity.people)} people are held as two or more customers (${percent(t.identity.split_rate)})`,
    ],
  ]
  return (
    <Card title="Your data, as it really is">
      <Table head={['Asset', 'What you saw', 'The truth']}>
        {rows.map(([asset, seen, truth]) => (
          <tr key={asset}>
            <Td>{asset}</Td>
            <Td>{seen}</Td>
            <Td>{truth}</Td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

const METHOD_LABEL: Record<string, string> = {
  IDENTIFIER: 'An identifier matched',
  FUZZY: 'Fuzzy match, linked automatically',
  REVIEW_SAME: 'A reviewer said: same customer',
  REVIEW_NEW: 'A reviewer said: different customer',
  NEW: 'Nothing matched: new customer',
  BEFORE_P2_4: 'Linked before matching was recorded',
}

/** How the bureau linked provider customers, and how often each way was wrong. */
function Matching({ r }: { r: Review }) {
  const m = r.figures.matching
  if (!m) return null
  const rows = Object.entries(m.methods).sort((a, b) => b[1].links - a[1].links)
  return (
    <Card title="How customers were matched">
      <p className="mb-2 text-sm text-slate-600">
        Tooling {m.tooling.toLowerCase()}; linked automatically at {m.auto_link.toFixed(2)}, held
        for review from {m.review.toFixed(2)}. A wrong merge put a second person on a customer; a
        false split made a new customer for someone already on file.
      </p>
      <Table head={['How', 'Links (this month)', 'Wrong merges', 'False splits']}>
        {rows.map(([method, t]) => (
          <tr key={method}>
            <Td>{METHOD_LABEL[method] ?? method}</Td>
            <Td right>
              {count(t.links)} ({count(t.this_month)})
            </Td>
            <Td right>{count(t.wrong_merges)}</Td>
            <Td right>{count(t.false_splits)}</Td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

function Chains({ r, gameId, fig }: { r: Review; gameId: number; fig: FigureContext }) {
  const c = r.figures.consequences
  return (
    <Card title="What the mistakes caused">
      {c.chains.length === 0 ? (
        <p className="text-sm text-slate-500">No report went out wrong this month.</p>
      ) : (
        <div className="space-y-3 text-sm">
          <p>
            <Figure
              fig={fig}
              k="consequences"
              n={c.mixed_reports + c.incomplete_reports}
              label="wrong reports"
            />{' '}
            reports went to subscribers wrong: {count(c.mixed_reports)} showed someone else's
            accounts and {count(c.incomplete_reports)} left some of the applicant's out.{' '}
            {count(c.from_decisions)} of the causes were decisions on work items;{' '}
            {count(c.automatic)} were the automatic matching rules.
          </p>
          <ol className="space-y-2">
            {c.chains.map((chain, i) => (
              <li key={i} className="rounded border border-slate-200 p-2">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <time dateTime={chain.at}>{dateTime(chain.at)}</time>
                  <Badge tone={chain.effect === 'MIXED_REPORT' ? 'bad' : 'warn'}>
                    {chain.effect === 'MIXED_REPORT' ? 'mixed report' : 'incomplete report'}
                  </Badge>
                  <span>
                    enquiry {chain.enquiry} by {chain.subscriber}
                  </span>
                </div>
                <p className="mt-1">{chain.detail}</p>
                {chain.work_item !== null && (
                  <Link
                    to={`/games/${gameId}/queue/${chain.work_item}`}
                    className="text-xs text-brand hover:underline"
                  >
                    Open work item {chain.work_item}
                  </Link>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  )
}

const LABELS: Record<string, string> = {
  'match.all': 'All match decisions',
  'match.right': 'Right match decisions',
  'match.false_merge': 'False merges',
  'match.false_split': 'False splits',
  'match.other_wrong': 'Other wrong match decisions',
  'triage.all': 'All triage decisions',
  'triage.right': 'Right triage decisions',
  'triage.genuine_returned': 'Genuine records returned to the provider',
  'triage.wrongly_loaded': 'Wrong corrections loaded',
  consequences: 'Wrong reports',
}

function DrillPanel({ gameId, period, k }: { gameId: number; period: string; k: string }) {
  const drill = useReviewDrill(gameId, period, k)
  const title = LABELS[k] ?? k.replace(/^rejected\.(\w+)\.(\w+)$/, 'Not loaded ($1): $2 records')
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="text-base font-semibold">{title}</h2>
      {drill.isPending ? (
        <Loading what="the records" />
      ) : drill.isError ? (
        <Failed error={drill.error} />
      ) : (
        <DrillTable gameId={gameId} drill={drill.data} />
      )}
    </section>
  )
}

function DrillTable({ gameId, drill }: { gameId: number; drill: ReviewDrill }) {
  const text = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
  if (drill.kind === 'work_items') {
    return (
      <Table head={['Item', 'Decided', 'Right answer', 'By', 'Why the right answer', 'Record']}>
        {drill.rows.map((row: DrillRow) => (
          <tr key={text(row.item)}>
            <Td>
              <Link
                to={`/games/${gameId}/queue/${text(row.item)}`}
                className="text-brand hover:underline"
              >
                {text(row.item)}
              </Link>
            </Td>
            <Td>
              {text(row.decision)}{' '}
              {row.correct ? <Badge tone="good">right</Badge> : <Badge tone="bad">wrong</Badge>}
            </Td>
            <Td>{text(row.correct_decision)}</Td>
            <Td>{text(row.employee ?? RESOLVERS[text(row.resolved_by)])}</Td>
            <Td>{text(row.why_right)}</Td>
            <Td>
              <Link
                to={`/games/${gameId}/submissions/${text(row.submission)}`}
                className="text-brand hover:underline"
              >
                {text(row.submission)}
              </Link>{' '}
              row {text(row.row)}
            </Td>
          </tr>
        ))}
      </Table>
    )
  }
  if (drill.kind === 'records') {
    return (
      <Table head={['Submission', 'File', 'Row', 'Name', 'Errors']}>
        {drill.rows.map((row: DrillRow) => (
          <tr key={`${text(row.file)}-${text(row.row)}`}>
            <Td>
              <Link
                to={`/games/${gameId}/submissions/${text(row.submission)}`}
                className="text-brand hover:underline"
              >
                {text(row.submission)}
              </Link>
            </Td>
            <Td>{text(row.file)}</Td>
            <Td right>{text(row.row)}</Td>
            <Td>{text(row.name)}</Td>
            <Td>
              {(row.errors as { rule: string; field: string; value: string }[])
                .map((e) => `${e.rule} ${e.field}${e.value ? ` "${e.value}"` : ''}`)
                .join('; ') || 'repeated row'}
            </Td>
          </tr>
        ))}
      </Table>
    )
  }
  return (
    <Table head={['When', 'Report', 'What was wrong, and why']}>
      {drill.rows.map((row: DrillRow, i: number) => (
        <tr key={i}>
          <Td>{dateTime(text(row.at))}</Td>
          <Td>{text(row.enquiry)}</Td>
          <Td>{text(row.detail)}</Td>
        </tr>
      ))}
    </Table>
  )
}
