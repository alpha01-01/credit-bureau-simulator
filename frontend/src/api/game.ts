/**
 * Typed queries for the game screens. Every query key starts with the game
 * id, so advancing the clock can refresh everything about that game at once.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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
