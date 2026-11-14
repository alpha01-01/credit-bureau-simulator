import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type Session = { authenticated: boolean; username?: string }

export function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: () => apiGet<Session>('/auth/session/'),
    staleTime: 60_000,
  })
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      apiPost<Session>('/auth/login/', credentials),
    onSuccess: (session) => {
      client.setQueryData(['session'], session)
      void client.invalidateQueries({ queryKey: ['games'] })
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<Session>('/auth/logout/'),
    onSuccess: (session) => {
      // Update the screens that are showing, then drop everything that was the player's.
      client.setQueryData(['session'], session)
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== 'session' })
    },
  })
}
