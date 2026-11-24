import { useGameCommand } from '../api/game'
import { useOnboarding } from '../api/onboarding'
import type { Onboarding, OnboardingStep } from '../api/onboarding'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Empty, Failed, Loading, Page } from '../components/ui'
import { day, money } from '../lib/format'
import { termsLine } from '../lib/terms'

const BUTTON =
  'rounded border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand hover:text-white disabled:opacity-50'

const DEPARTMENT: Record<string, string> = {
  SALES: 'Sales',
  COMPLIANCE: 'Compliance',
  IT: 'IT',
  FINANCE: 'Finance',
  SUPPORT: 'Support',
}

const STEP_TONE = {
  DONE: 'good',
  READY: 'info',
  ESCALATED: 'warn',
  WAITING: 'neutral',
  CANCELLED: 'neutral',
} as const

const STEP_WORD = {
  DONE: 'done',
  READY: 'in hand',
  ESCALATED: 'needs the head',
  WAITING: 'waiting',
  CANCELLED: 'cancelled',
} as const

const STATUS = {
  IN_PROGRESS: ['info', 'in progress'],
  COMPLETE: ['good', 'onboarded'],
  WITHDRAWN: ['bad', 'walked away'],
  REFUSED: ['bad', 'refused'],
} as const

const DECISION_WORDS: Record<string, string> = {
  APPROVE: 'Approve',
  APPROVE_WITH_WARNING: 'Approve under a warning',
  REFUSE: 'Refuse',
}

function StepCell({ step }: { step: OnboardingStep }) {
  return (
    <li className="min-w-0 flex-1 rounded border border-slate-200 bg-white p-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{DEPARTMENT[step.department]}</span>
        <Badge tone={STEP_TONE[step.status]}>{STEP_WORD[step.status]}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-600">{step.title}</p>
      {step.status === 'DONE' && (
        <p className="mt-1 text-xs">
          {step.outcome} — {step.done_by}, {day(step.done_on)}
        </p>
      )}
      {step.status === 'WAITING' && step.waiting_for && (
        <p className="mt-1 text-xs text-slate-500">Waiting for {DEPARTMENT[step.waiting_for]}</p>
      )}
      {(step.status === 'READY' || step.status === 'ESCALATED') && (
        <div className="mt-1 space-y-0.5 text-xs">
          {step.held && <p className="text-amber-800">{step.held}</p>}
          {step.waited !== null && (
            <p>
              With {DEPARTMENT[step.department]} for {step.waited} working day
              {step.waited === 1 ? '' : 's'}
            </p>
          )}
          {step.status === 'READY' && step.days > 0 && (
            <p className="text-slate-500">
              {step.code === 'CONNECTION' || step.code === 'WELCOME'
                ? `${step.progress} of ${step.days} days' work done; `
                : ''}
              staff expect to finish by {day(step.due_on)}
            </p>
          )}
        </div>
      )}
    </li>
  )
}

function OnboardingCard({
  o,
  decisions,
  act,
}: {
  o: Onboarding
  decisions: string[]
  act: ReturnType<typeof useGameCommand>
}) {
  const [tone, word] = STATUS[o.status]
  const check = o.steps.find((s) => s.code === 'SUBSCRIBER_CHECK')
  const billing = o.steps.find((s) => s.code === 'BILLING')
  const deciding = o.at === 'COMPLIANCE' && check
  const billingNow = o.at === 'FINANCE' && billing
  return (
    <Card title={`${o.name} (${o.lender})`}>
      <div className="space-y-3">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={tone}>{word}</Badge>
          <span>Signed {day(o.signed_on)}</span>
          {o.live_on ? (
            <span>· connected {day(o.live_on)}</span>
          ) : (
            o.status === 'IN_PROGRESS' && (
              <span className="text-amber-800">
                · walks away if not connected by {day(o.give_up_on)}
              </span>
            )
          )}
          {Number(o.unbilled) > 0 && (
            <span className="text-amber-800">· {money(o.unbilled)} of use not yet billed</span>
          )}
        </p>
        <p className="text-sm text-slate-600">Terms: {termsLine(o.terms)}</p>
        <ol className="flex flex-col gap-2 md:flex-row" aria-label="Steps, in order">
          {o.steps.map((s) => (
            <StepCell key={s.position} step={s} />
          ))}
        </ol>
        {deciding && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm">
            <p className="font-medium">Compliance's check</p>
            <p className="mt-1">
              Licensed; purpose: {check.evidence.purpose}. Of {check.evidence.sample} consent forms
              asked for, {check.evidence.missing} could not be found.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {decisions.map((d) => (
                <button
                  key={d}
                  type="button"
                  className={BUTTON}
                  disabled={act.isPending}
                  onClick={() => act.mutate({ action: 'decide', number: o.number, decision: d })}
                >
                  {DECISION_WORDS[d] ?? d}
                </button>
              ))}
            </div>
          </div>
        )}
        {billingNow && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm">
            <p className="font-medium">Finance: billing</p>
            <p className="mt-1">
              {billing.evidence.standard
                ? 'Standard terms: the staff will set up billing.'
                : 'Terms off the price list: check them against the contract, then set up billing.'}
            </p>
            <button
              type="button"
              className={`${BUTTON} mt-2`}
              disabled={act.isPending}
              onClick={() => act.mutate({ action: 'billing', number: o.number })}
            >
              Set up billing
            </button>
          </div>
        )}
      </div>
    </Card>
  )
}

/**
 * Onboarding (P3.9): a new subscriber's way through the company. Sales signs it,
 * Compliance checks it, IT connects it, Finance bills it and Support answers its
 * questions. Each step waits for the one before.
 */
export function OnboardingPage() {
  const gameId = useGameId()
  const data = useOnboarding(gameId)
  const act = useGameCommand(gameId, '/onboarding/')
  if (data.isPending) return <Loading what="onboarding" />
  if (data.isError) return <Failed error={data.error} />
  const d = data.data
  const open = d.onboardings.filter((o) => o.status === 'IN_PROGRESS')
  const ended = d.onboardings.filter((o) => o.status !== 'IN_PROGRESS')
  return (
    <Page
      title="Onboarding"
      subtitle={`Each department does its part in turn, and a step left undone holds up every step after it. A lender not connected within ${d.patience_days} working days of signing walks away.`}
    >
      {act.error && <Failed error={act.error} />}
      {d.onboardings.length === 0 && (
        <Card>
          <Empty>No lender has signed yet. Sales wins them.</Empty>
        </Card>
      )}
      {open.map((o) => (
        <OnboardingCard key={o.number} o={o} decisions={d.decisions} act={act} />
      ))}
      {ended.map((o) => (
        <OnboardingCard key={o.number} o={o} decisions={d.decisions} act={act} />
      ))}
    </Page>
  )
}
