import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export interface Health {
  status: 'ok'
  service: string
  database: { vendor: string; server_version: string | null }
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<Health>('/health/'),
    retry: false,
  })
}
