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

// --- Scorecards (P3.5) ---------------------------------------------------------------------

export type Measures = {
  customers: number
  bads: number
  auc: number | null
  gini: number | null
  ks: number | null
}

export type ScoreModelSummary = {
  number: number
  term: string
  status: 'DRAFT' | 'DEPLOYED' | 'RETIRED'
  observation: string
  window_months: number
  features: string[]
  holdout: Measures | null
  restricted_used: string[]
}

export type ScorecardsData = {
  options: {
    terms: { code: string; label: string }[]
    features: {
      name: string
      description: string
      recommended_for: string[]
      restricted: boolean
    }[]
    windows: { months: number; observation_dates: string[] }[]
    default_window: number
  }
  models: ScoreModelSummary[]
  findings: {
    number: number
    kind: string
    reference: string
    detail: string
    raised_at: string
    resolved_tick: number | null
  }[]
}

export type Characteristic = {
  feature: string
  description: string
  iv: number
  coefficient: number
  bins: { upper: number | null; goods: number; bads: number; woe: number; points: number }[]
}

export type ScoreModelDetail = ScoreModelSummary & {
  results: {
    characteristics?: Characteristic[]
    train?: Measures
    holdout?: Measures
    score_bands?: {
      band: string
      label: string
      from: number
      customers: number
      bad_rate: number | null
    }[]
    fairness?: {
      restricted_used: string[]
      proxies?: { feature: string; iv_for_gender: number }[]
      groups?: {
        group: string
        customers: number
        mean_score: number
        score_600_or_more: number
        default_rate: number
      }[]
    }
    truth?: {
      customers?: number
      true_defaults?: number
      auc_against_truth?: number | null
      auc_against_bureau_labels?: number | null
      labels?: { both_default: number; bureau_only: number; truth_only: number; neither: number }
    }
    components?: { number: number; term: string }[]
    weights?: { term: string; log_odds_weight: number; presence_weight: number }[]
    each_term_on_everyone?: Record<string, number | null>
  }
  monitoring: {
    as_of: string
    customers: number
    psi: number
    drift: boolean
    shift?: 'stable' | 'moderate' | 'major'
    development: number[]
    now: number[]
    since_deployment?: {
      from: string
      psi: number
      shift: 'stable' | 'moderate' | 'major'
    } | null
  } | null
}

export function useScorecards(id: number) {
  return useQuery({
    queryKey: [id, 'scorecards'],
    queryFn: () => apiGet<ScorecardsData>(`/games/${id}/scorecards/`),
  })
}

export function useScorecard(id: number, number: number) {
  return useQuery({
    queryKey: [id, 'scorecards', number],
    queryFn: () => apiGet<ScoreModelDetail>(`/games/${id}/scorecards/${number}/`),
  })
}
