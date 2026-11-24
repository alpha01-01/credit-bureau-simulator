/** The Finance department's screens (P3.8): bills, the bank, budgets and the close. */

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export type Bill = {
  number: number
  supplier: string
  reference: string
  description: string
  account: string
  amount: string
  bill_date: string
  due_date: string
  status: 'RECEIVED' | 'APPROVED' | 'REJECTED' | 'PAID'
  approved_by: string | null
  paid_on: string | null
  late_fee: string
  overdue: boolean
  same_reference_as: number | null
}

export type BillsData = { approval_limit: string; late_charge_rate: string; bills: Bill[] }

export type StatementLine = {
  period: string
  line: number
  value_date: string
  description: string
  reference: string | null
  amount: string
  status: 'MATCHED' | 'OPEN' | 'POSTED' | 'QUERIED' | 'BANK_ERROR'
  answer: string | null
  awaiting_answer: boolean
}

export type BankData = {
  statements: { period: string; closing_balance: string; reconciled: boolean }[]
  statement: {
    period: string
    opening_balance: string
    closing_balance: string
    received_at: string
    reconciled_at: string | null
    lines: StatementLine[]
    ledger_balance: string
    difference: string
    uncleared: { reference: string; date: string; description: string; amount: string }[]
    unrecorded: StatementLine[]
    explained_balance: string
    reconciles: boolean
    open_items: number
  } | null
}

export type BudgetData = {
  month: string
  months: string[]
  reviewed: boolean
  revenue: string
  costs: string
  result: string
  rows: {
    centre: string
    name: string
    income: boolean
    budget: string | null
    actual: string
    variance: string | null
    variance_share: number | null
  }[]
}

export type CloseData = {
  closed_through: string | null
  period: string
  ended: boolean
  checklist: { code: string; title: string; done: boolean; how: string }[]
  closed: { period: string; closed_at: string }[]
}

const base = (id: number) => `/games/${id}/finance`

export function useBills(id: number) {
  return useQuery({
    queryKey: [id, 'finance', 'bills'],
    queryFn: () => apiGet<BillsData>(`${base(id)}/bills/`),
  })
}

export function useBank(id: number, period: string | null) {
  return useQuery({
    queryKey: [id, 'finance', 'bank', period],
    queryFn: () => apiGet<BankData>(`${base(id)}/bank/${period ? `?period=${period}` : ''}`),
  })
}

export function useBudget(id: number, month: string | null) {
  return useQuery({
    queryKey: [id, 'finance', 'budget', month],
    queryFn: () => apiGet<BudgetData>(`${base(id)}/budget/${month ? `?month=${month}` : ''}`),
  })
}

export function useClose(id: number) {
  return useQuery({
    queryKey: [id, 'finance', 'close'],
    queryFn: () => apiGet<CloseData>(`${base(id)}/close/`),
  })
}
