/**
 * Typed queries for the game screens. Every query key starts with the game
 * id, so advancing the clock can refresh everything about that game at once.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type Clock = {
  game: number
  tick: number
  now: string
  date: string
  weekday: string
  time: string
  status: 'PAUSED' | 'RUNNING'
  speed: number
  next_event: { tick: number; at: string }
  pending_events: number
  reporting_data_through: string
  pause_rules: PauseRules
  stopped_by: Notice | null
  latest_notice: number | null
}

export type Severity = 'INFO' | 'WARNING' | 'CRITICAL'

export type PauseRules = { severities: Severity[]; deadlines: boolean }

/** One entry in the event feed (P2.2). */
export type Notice = {
  id: number
  tick: number
  at: string
  kind: string
  severity: Severity
  title: string
  detail: string
  drill: Drill | null
  deadline: boolean
  paused: boolean
}

export type FeedPage = { notices: Notice[]; more: boolean }

/** A share estimated from a sample, with its 95% margin of error. */
export type Estimate = { share: number | null; margin: number | null; sample: number }

/** What the bureau can see of its data assets (P2.3). */
export type DataAssets = {
  source: 'month_end' | 'now'
  as_of: string
  coverage: { period: string; active_borrowers: number; covered: number; share: number | null }
  accounts: number
  depth_months: number | null
  freshness_days: number | null
  open_accounts: number
  audit: { accuracy: Estimate; one_person: Estimate }
}

type Tally = { total: number; right: number }

export type ReviewSummary = {
  period: string
  match: Tally & { false_merges: number; false_splits: number; other_wrong: number }
  rejected: { total: number; genuine: number }
  consequences: number
}

export type Chain = {
  at: string
  effect: 'MIXED_REPORT' | 'INCOMPLETE_REPORT'
  enquiry: string
  subscriber: string
  accounts: number
  cause: 'DECISION' | 'AUTOMATIC'
  work_item: number | null
  provider: string
  provider_customer: string
  detail: string
}

/** The monthly Data Quality Review: the truth revealed. */
export type Review = {
  period: string
  drill: string[]
  figures: {
    period: string
    match: Tally & {
      false_merges: number
      false_splits: number
      other_wrong: number
      by: Record<string, Tally>
    }
    triage: Tally & {
      genuine_returned: number
      wrongly_loaded: number
      other_wrong: number
      by: Record<string, Tally>
    }
    rejected: {
      total: number
      genuine: number
      rules: { rule: string; description: string; records: number; genuine: number }[]
    }
    assets: {
      visible: Omit<DataAssets, 'source'>
      truth: {
        accuracy: { accounts: number; right: number; share: number | null }
        identity: {
          customers: number
          false_merges: number
          merge_rate: number | null
          people: number
          false_splits: number
          split_rate: number | null
        }
      }
    }
    rules?: {
      cleansing: RuleEffect[]
      relaxed: RuleEffect[]
    }
    matching?: {
      tooling: string
      auto_link: number
      review: number
      methods: Record<
        string,
        {
          links: number
          this_month: number
          wrong_merges: number
          false_splits: number
          wrong_this_month: number
        }
      >
    }
    consequences: {
      mixed_reports: number
      incomplete_reports: number
      from_decisions: number
      automatic: number
      chains: Chain[]
    }
  }
}

/** What one of the bureau's own rules did in a month, measured against the truth. */
export type RuleEffect = {
  code: string
  changes: number
  right: number
  fields: string[]
  description?: string
  active?: boolean
}

export type DrillRow = Record<string, unknown>
export type ReviewDrill = {
  key: string
  kind: 'work_items' | 'records' | 'consequences'
  rows: DrillRow[]
}

export type GameSummary = {
  id: number
  bureau: string
  world: number
  setup_status: 'READY' | 'PREPARING' | 'FAILED'
  setup_message: string
  clock: Clock | null
}

export type World = { id: number; seed: number; scale: string; history_end: string }

export type Drill = { screen: string; params: Record<string, string> }

export type Metric = {
  key: string
  label: string
  value: string | number | null
  unit: string
  drill: Drill
}

export type InboxMessage = {
  severity: 'WARNING' | 'ERROR'
  title: string
  detail: string
  drill: Drill
}

export type Briefing = {
  today: string
  yesterday: string
  files_received: { reference: string; provider: string }[]
  records: { received: number; accepted: number; unloadable: number; pending: number }
  work: { waiting: number; resolved_yesterday: number }
  enquiries: { count: number; hits: number }
  inbox: InboxMessage[]
}

export type SubmissionRow = {
  reference: string
  provider: string
  provider_name: string
  period: string
  received_at: string
  due_date: string
  late: boolean
  status: string
  received: number | null
  accepted: number | null
  unloadable: number | null
  duplicates: number | null
  pending: number | null
}

/** A file rejected for its columns: what arrived, and the bureau's suggested mapping. */
export type FileMappingOffer = { received: string[]; suggested: string[]; template: string[] }

export type FeedbackReport = {
  submission: string
  provider: string
  period: string
  files_rejected: number
  records_unloadable: number
  records_with_warnings: number
  rules: { rule: string; description: string; records: number }[]
  rows: {
    file: string
    row: number
    account: string
    customer: string
    problems: { rule: string; field: string; value: string; message: string }[]
  }[]
  more_rows: number
  sent: string[]
}

export type OwnRules = {
  cleansing: {
    code: string
    field: string
    action: string
    find: string
    replace: string
    provider: string
    active: boolean
    created_at: string
  }[]
  validation: { code: string; description: string; setting: 'ERROR' | 'WARNING' }[]
  actions: { code: string; description: string }[]
  providers: string[]
}

export function useFeedback(id: number, reference: string) {
  return useQuery({
    queryKey: [id, 'feedback', reference],
    queryFn: () => apiGet<FeedbackReport>(`${game(id)}/submissions/${reference}/feedback/`),
  })
}

export function useOwnRules(id: number) {
  return useQuery({
    queryKey: [id, 'rules'],
    queryFn: () => apiGet<OwnRules>(`${game(id)}/rules/`),
  })
}

export type SubmissionDetail = {
  reference: string
  provider: string
  period: string
  template_version: string
  received_at: string
  due_date: string
  late: boolean
  status: string
  files: {
    name: string
    kind: string
    format: string
    size: number
    sha256: string
    status: string
    rejection_reason: string
    mapped: boolean
    mapping: FileMappingOffer | null
  }[]
  runs: {
    run_number: number
    template_version: string
    started_at: string
    completed_at: string
    status: string
    received: number
    accepted: number
    unloadable: number
    duplicates: number
    pending: number
    reconciles: boolean
    customers_created: number
    accounts_created: number
    issues: { rule_code: string; severity: string; message: string; count: number }[]
    examples: { row: number; file: string; rule: string; field: string; value: string }[]
  }[]
}

export type WorkItemRow = {
  number: number
  type: 'MATCH_REVIEW' | 'UNLOADABLE_TRIAGE'
  status: 'OPEN' | 'IN_PROGRESS' | 'DONE'
  difficulty: number
  created_tick: number
  assignee: string | null
  decision: string | null
  resolved_by: string | null
  resolved_tick: number | null
}

export type WorkItemDetail = WorkItemRow & {
  provider: { code: string; name: string }
  on_file: {
    reporting_date: string
    status: string
    balance: string
    arrears: string
    days_past_due: number
    disbursement_date: string | null
  } | null
  record: Record<string, string>
  candidate: {
    reference: string
    name: string | null
    date_of_birth: string | null
    registration_date: string | null
  } | null
  score: number | null
  evidence: {
    identifier_field?: string
    identifier?: string
    reasons?: string[]
    errors?: { rule: string; field: string; value: string }[]
  }
  proposal: Record<string, string>
  allowed_decisions: string[]
  explanation: string | null
}

export type Employee = {
  number: string
  name: string
  job_title: string
  skills: Record<string, number>
  experience: Record<string, number>
  morale: number
  done_today: number
}

export type CustomerRow = { reference: string; type: string; name: string }

export type CustomerDetail = CustomerRow & {
  date_of_birth: string | null
  gender: string | null
  identifiers: { type: string; value: string }[]
  contacts: { value: string; primary: boolean }[]
  provider_links: { provider: string; number: string }[]
  accounts: {
    lender: string
    account_number: string
    facility_type: string
    opened: string | null
    original_amount: string
    status: string
    observations: {
      date: string
      balance: string
      arrears: string
      days_past_due: number
      status: string
      source: string
    }[]
  }[]
  dishonoured_cheques: {
    lender: string
    account_number: string
    cheque_number: string
    date_issued: string
    date_bounced: string
    reason: string
    currency: string
    amount: string
  }[]
  judgments: {
    plaintiff: string
    court: string
    court_type: string
    case_number: string
    filing_date: string
    case_type: string
    case_reason: string
    currency: string
    amount: string
  }[]
  enquiries: { reference: string; subscriber: string; at: string; purpose: string }[]
}

export type EnquiryRow = {
  reference: string
  subscriber: string
  purpose: string
  enquired_at: string
  outcome: 'HIT' | 'NO_HIT'
  customer: string | null
  accounts_reported: number
}

export type StatementRow = { code: string; name: string; amount: string }

export type Finance = {
  as_of: string
  trial_balance: {
    rows: { code: string; name: string; debit: string; credit: string }[]
    total_debit: string
    total_credit: string
  }
  income_month_to_date: IncomeStatement
  income_year_to_date: IncomeStatement
  balance_sheet: {
    assets: StatementRow[]
    liabilities: StatementRow[]
    equity: StatementRow[]
    total_assets: string
    total_liabilities: string
    total_equity: string
    balances: boolean
  }
  cash: { bank: string; receivables: string; overdue_invoices: number; taxes_owed: string }
}

export type IncomeStatement = {
  start: string
  end: string
  income: StatementRow[]
  expenses: StatementRow[]
  total_income: string
  total_expenses: string
  net_profit: string
}

export type JournalRow = {
  reference: string
  date: string
  description: string
  source: string
  lines: { account: string; debit: string; credit: string }[]
}

export type InvoiceRow = {
  number: string
  subscriber: string
  period: string
  issued: string
  due: string
  tax: string
  total: string
  outstanding: string
  tax_rules: string
}

function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== '')
  return entries.length ? `?${new URLSearchParams(entries as [string, string][])}` : ''
}

const game = (id: number) => `/games/${id}`

export function useGames() {
  return useQuery({ queryKey: ['games'], queryFn: () => apiGet<GameSummary[]>('/games/') })
}

export function useWorlds() {
  return useQuery({ queryKey: ['worlds'], queryFn: () => apiGet<World[]>('/worlds/') })
}

export function useGame(id: number) {
  return useQuery({
    queryKey: [id, 'game'],
    queryFn: () => apiGet<GameSummary>(`${game(id)}/`),
    refetchInterval: (q) => {
      const data = q.state.data
      if (!data) return false
      if (data.setup_status === 'PREPARING') return 3000
      return data.clock?.status === 'RUNNING' ? 2000 : false
    },
  })
}

export function useFeed(id: number, severity: Severity | undefined) {
  return useInfiniteQuery({
    queryKey: [id, 'feed', severity ?? 'all'],
    queryFn: ({ pageParam }) => {
      const query = new URLSearchParams()
      if (severity) query.set('severity', severity)
      if (pageParam) query.set('before', String(pageParam))
      const rest = query.toString()
      return apiGet<FeedPage>(`${game(id)}/feed/${rest ? `?${rest}` : ''}`)
    },
    initialPageParam: 0,
    getNextPageParam: (last) => (last.more ? last.notices[last.notices.length - 1]?.id : undefined),
  })
}

export function useDataAssets(id: number) {
  return useQuery({
    queryKey: [id, 'data-assets'],
    queryFn: () => apiGet<DataAssets>(`${game(id)}/data-assets/`),
  })
}

export function useReviews(id: number) {
  return useQuery({
    queryKey: [id, 'reviews'],
    queryFn: () => apiGet<ReviewSummary[]>(`${game(id)}/reviews/`),
  })
}

export function useReview(id: number, period: string) {
  return useQuery({
    queryKey: [id, 'review', period],
    queryFn: () => apiGet<Review>(`${game(id)}/reviews/${period}/`),
  })
}

export function useReviewDrill(id: number, period: string, key: string | null) {
  return useQuery({
    queryKey: [id, 'review', period, 'drill', key],
    queryFn: () =>
      apiGet<ReviewDrill>(
        `${game(id)}/reviews/${period}/drill/?key=${encodeURIComponent(key ?? '')}`,
      ),
    enabled: key !== null,
  })
}

export function useDashboard(id: number) {
  return useQuery({
    queryKey: [id, 'dashboard'],
    queryFn: () => apiGet<{ as_of: string; metrics: Metric[] }>(`${game(id)}/dashboard/`),
  })
}

export function useBriefing(id: number) {
  return useQuery({
    queryKey: [id, 'briefing'],
    queryFn: () => apiGet<Briefing>(`${game(id)}/briefing/`),
  })
}

export function useSubmissions(id: number, params: Record<string, string | undefined>) {
  return useQuery({
    queryKey: [id, 'submissions', params],
    queryFn: () => apiGet<SubmissionRow[]>(`${game(id)}/submissions/${query(params)}`),
  })
}

export function useSubmission(id: number, reference: string) {
  return useQuery({
    queryKey: [id, 'submission', reference],
    queryFn: () => apiGet<SubmissionDetail>(`${game(id)}/submissions/${reference}/`),
  })
}

export function useWorkItems(id: number, status: string | undefined) {
  return useQuery({
    queryKey: [id, 'work-items', status],
    queryFn: () => apiGet<WorkItemRow[]>(`${game(id)}/work-items/${query({ status })}`),
  })
}

export function useWorkItem(id: number, number: number) {
  return useQuery({
    queryKey: [id, 'work-item', number],
    queryFn: () => apiGet<WorkItemDetail>(`${game(id)}/work-items/${number}/`),
  })
}

export function useEmployees(id: number) {
  return useQuery({
    queryKey: [id, 'employees'],
    queryFn: () => apiGet<Employee[]>(`${game(id)}/employees/`),
  })
}

export function useCustomers(id: number, q: string) {
  return useQuery({
    queryKey: [id, 'customers', q],
    queryFn: () => apiGet<CustomerRow[]>(`${game(id)}/customers/${query({ q })}`),
  })
}

export function useCustomer(id: number, reference: string) {
  return useQuery({
    queryKey: [id, 'customer', reference],
    queryFn: () => apiGet<CustomerDetail>(`${game(id)}/customers/${reference}/`),
  })
}

export function useEnquiries(id: number, params: Record<string, string | undefined>) {
  return useQuery({
    queryKey: [id, 'enquiries', params],
    queryFn: () => apiGet<EnquiryRow[]>(`${game(id)}/enquiries/${query(params)}`),
  })
}

export function useFinance(id: number) {
  return useQuery({
    queryKey: [id, 'finance'],
    queryFn: () => apiGet<Finance>(`${game(id)}/finance/`),
  })
}

export function useLedger(id: number, params: Record<string, string | undefined>) {
  return useQuery({
    queryKey: [id, 'ledger', params],
    queryFn: () => apiGet<JournalRow[]>(`${game(id)}/ledger/${query(params)}`),
  })
}

export function useInvoices(id: number, unpaid: string | undefined) {
  return useQuery({
    queryKey: [id, 'invoices', unpaid],
    queryFn: () => apiGet<InvoiceRow[]>(`${game(id)}/invoices/${query({ unpaid })}`),
  })
}

export type MatchingPolicy = {
  tooling: string
  auto_link: number
  review: number
  options: { level: string; description: string; monthly_cost: string }[]
}

export function useMatchingPolicy(id: number) {
  return useQuery({
    queryKey: [id, 'matching-policy'],
    queryFn: () => apiGet<MatchingPolicy>(`${game(id)}/matching-policy/`),
  })
}

export type RejectionPolicy = {
  policy: string
  options: { code: string; description: string }[]
}

export function useRejectionPolicy(id: number) {
  return useQuery({
    queryKey: [id, 'rejection-policy'],
    queryFn: () => apiGet<RejectionPolicy>(`${game(id)}/rejection-policy/`),
  })
}

/** A game command (clock, decision). Refreshes everything about the game afterwards. */
export function useGameCommand<T>(id: number, path: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: unknown) => apiPost<T>(`${game(id)}${path}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: [id] }),
  })
}
