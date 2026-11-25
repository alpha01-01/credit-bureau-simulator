/** Customer Support and Product Development, managed by the chief executive (P3.10). */

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { Parameters } from './game'

export type SupportData = {
  agents: number
  per_agent: number
  capacity: number
  agent_monthly: string
  range: [number, number]
  response_days: number
  waiting: number
  satisfaction: { score: number | null; tickets: number; on_time: number; late: number }
  topics: Record<string, string>
  days: { day: string; topics: Record<string, number> }[]
  answered_30d: number
  on_time_30d: number
  average_days_30d: number | null
  tickets: {
    number: number
    source: 'SUBSCRIBER' | 'SUBJECT'
    subscriber: string | null
    topic: string
    opened_on: string
    due_on: string
    answered_on: string | null
  }[]
}

export type ProductsData = {
  products: {
    code: string
    name: string
    does: string
    cost: string
    working_days: number
    status: 'AVAILABLE' | 'IN_DEVELOPMENT' | 'LAUNCHED'
    started_on: string | null
    ready_on: string | null
    launched_on: string | null
  }[]
}

export function useSupport(id: number) {
  return useQuery({
    queryKey: [id, 'support'],
    queryFn: () => apiGet<SupportData>(`/games/${id}/support/`),
  })
}

export function useProducts(id: number) {
  return useQuery({
    queryKey: [id, 'products'],
    queryFn: () => apiGet<ProductsData>(`/games/${id}/products/`),
  })
}

// --- Startup (P3.13) ---------------------------------------------------------------------

export type StartupStep = {
  code: string
  title: string
  done: boolean
  detail: string
  screen: string
}

export type StartupData = {
  startup: boolean
  steps: StartupStep[]
  office: string | null
  desks_free: number
  offices: { code: string; name: string; monthly_rent: string; desks: number; fit_out: string }[]
  it: {
    set_up: boolean
    ready: boolean
    ready_on: string | null
    cost: string
    days: number
    levels: string[]
  }
  providers: { code: string; name: string; type: string }[]
  onboarded: { code: string; name: string; since: string }[]
  scenario: string
  scenario_name: string
  difficulty: string
  parameters: Parameters
  economy: string
  world_economy: string
}

export function useStartup(id: number) {
  return useQuery({
    queryKey: [id, 'startup'],
    queryFn: () => apiGet<StartupData>(`/games/${id}/startup/`),
  })
}
