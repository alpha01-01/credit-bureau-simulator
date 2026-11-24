/** The Compliance screen (P3.7): the rules, the monthly return, consent, retention, access. */

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export type ComplianceData = {
  today: string
  rules: { code: string; title: string; rule: string; citation: string; status: string }[]
  returns: {
    period: string
    due_date: string
    filed_at: string | null
    filed_by: string | null
    figures: Record<string, number>
    late: boolean
    work_item: number | null
  }[]
  subscribers: { code: string; name: string; suspended: boolean; sanctions: number }[]
  sample_months: string[]
  sample_sizes: number[]
  consent_checks: {
    number: number
    subscriber: string
    month: string
    size: number
    answered: boolean
    missing: string[]
    answer_tick: number
  }[]
  sanctions: {
    number: number
    subscriber: string
    kind: 'WARNING' | 'SUSPENSION'
    tick: number
    until_tick: number | null
    active: boolean
  }[]
  retention: { years: number; legal_years: number; choices: number[] }
  access: { staff: number; leavers_with_access: string[] }
  findings: {
    number: number
    kind: string
    reference: string
    detail: string
    remedy: string | null
    raised_at: string
    due_date: string | null
    resolved: boolean
    escalated: boolean
  }[]
  regulator: {
    level: number
    standing: string
    findings: { kind: string; reference: string; raised_at: string; detail: string }[]
  }
}

export function useCompliance(id: number) {
  return useQuery({
    queryKey: [id, 'compliance'],
    queryFn: () => apiGet<ComplianceData>(`/games/${id}/compliance/`),
  })
}
