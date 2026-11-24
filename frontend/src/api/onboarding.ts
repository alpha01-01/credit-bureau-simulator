/** Taking on a subscriber, department by department (P3.9). */

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { Terms } from './game'

export type Department = 'SALES' | 'COMPLIANCE' | 'IT' | 'FINANCE' | 'SUPPORT'

export type OnboardingStep = {
  position: number
  department: Department
  code: string
  title: string
  status: 'WAITING' | 'READY' | 'ESCALATED' | 'DONE' | 'CANCELLED'
  ready_on: string | null
  due_on: string | null
  progress: number
  days: number
  held: string | null
  waiting_for: Department | null
  waited: number | null
  done_on: string | null
  done_by: string | null
  outcome: string | null
  evidence: {
    sample?: number
    missing?: number
    concern?: boolean
    purpose?: string
    standard?: boolean
  }
}

export type Onboarding = {
  number: number
  lender: string
  name: string
  status: 'IN_PROGRESS' | 'COMPLETE' | 'WITHDRAWN' | 'REFUSED'
  signed_on: string
  give_up_on: string
  live_on: string | null
  ended_on: string | null
  at: Department | null
  terms: Terms & { price: string }
  unbilled: string
  steps: OnboardingStep[]
}

export type OnboardingData = {
  patience_days: number
  decisions: string[]
  onboardings: Onboarding[]
}

export function useOnboarding(id: number) {
  return useQuery({
    queryKey: [id, 'onboarding'],
    queryFn: () => apiGet<OnboardingData>(`/games/${id}/onboarding/`),
  })
}
