/** Analytics and the SQL console (P3.4). */

import { useMutation, useQuery } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type GroupRow = {
  key: string
  label: string
  accounts: number
  balance: string
  arrears_30: number
  default_90: number
  balance_90: string
  arrears_30_share: number
  default_90_share: number
}

export type Analytics = {
  as_of: string | null
  lenders_as_of?: Record<string, string>
  records_start?: string
  default_definition?: string
  live_accounts?: number
  groups: Partial<Record<'lender' | 'product' | 'region' | 'vintage', GroupRow[]>>
  roll_rates: {
    from: string[]
    to: string[]
    counts: Record<string, Record<string, number>>
  } | null
  vintages: {
    quarter: string
    accounts: number
    defaulted: number
    mature: number
    mature_defaulted: number
    default_rate: number | null
    default_rate_so_far: number
  }[]
  age_at_default: { months: string; accounts: number }[]
}

export function useAnalytics(id: number) {
  return useQuery({
    queryKey: [id, 'analytics'],
    queryFn: () => apiGet<Analytics>(`/games/${id}/analytics/`),
  })
}

export type ConsoleInfo = {
  available: boolean
  tables: { table: string; columns: { name: string; type: string }[] }[]
  max_rows: number
  timeout_seconds: number
}

export type ConsoleResult = {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  truncated: boolean
  milliseconds: number
}

export function useConsoleInfo(id: number) {
  return useQuery({
    queryKey: [id, 'console'],
    queryFn: () => apiGet<ConsoleInfo>(`/games/${id}/console/`),
  })
}

/** Run a query. Not a game command: it changes nothing, so nothing is refreshed. */
export function useConsoleQuery(id: number) {
  return useMutation({
    mutationFn: (sql: string) => apiPost<ConsoleResult>(`/games/${id}/console/`, { sql }),
  })
}
