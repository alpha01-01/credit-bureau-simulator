/** A delivered credit report, and the subscribers' batch files (P3.11). */

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export type ReportAccount = {
  lender: string
  account: string
  facility_type: string
  opened: string | null
  original_amount: string
  status: string
  balance: string | null
  arrears: string | null
  days_past_due: number | null
  last_reported: string | null
  disputed: boolean
}

export type Report = {
  layout?: string
  as_of?: string
  subject?: {
    reference: string
    type: string
    name?: string
    registered_name?: string
    trading_name?: string | null
    registration_number?: string | null
    tin?: string | null
    sector?: string
    registration_date?: string | null
    date_of_birth?: string | null
    identifiers: { type: string; value: string }[]
  }
  summary?: Record<string, number | string>
  accounts?: ReportAccount[]
  facilities?: ReportAccount[]
  dishonoured_cheques?: {
    lender: string
    account_number: string
    cheque_number: string
    date_bounced: string | null
    reason: string
    amount: string
  }[]
  judgments?: {
    plaintiff: string
    court: string
    case_number: string
    filing_date: string | null
    case_type: string
    case_reason: string
    amount: string
  }[]
  score?: { score: number | null; band: string | null; band_label?: string }
}

export type BatchesData = {
  launched: boolean
  price: string
  batches: {
    reference: string
    subscriber: string
    name: string
    received_at: string
    records: number
    hits: number
  }[]
  batch: {
    reference: string
    rows: {
      row: number
      identifier: string
      name: string
      outcome: 'HIT' | 'NO_HIT'
      report: string
      accounts: number
    }[]
    result_file: string
  } | null
}

export function useReport(id: number, reference: string) {
  return useQuery({
    queryKey: [id, 'report', reference],
    queryFn: () =>
      apiGet<{ reference: string; report: Report }>(`/games/${id}/enquiries/${reference}/`),
  })
}

export function useBatches(id: number, reference: string | null) {
  return useQuery({
    queryKey: [id, 'batches', reference],
    queryFn: () =>
      apiGet<BatchesData>(`/games/${id}/batches/${reference ? `?reference=${reference}` : ''}`),
    placeholderData: (previous) => previous, // keep the list on screen while a file loads
  })
}
