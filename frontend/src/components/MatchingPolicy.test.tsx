import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MatchingPolicy } from '../api/game'
import { MatchingPolicyCard } from './MatchingPolicy'

const policy: MatchingPolicy = {
  tooling: 'BASIC',
  auto_link: 0.92,
  review: 0.75,
  options: [
    { level: 'BASIC', description: 'Identifiers only', monthly_cost: '0.00' },
    {
      level: 'STANDARD',
      description: 'Fuzzy matching on name and date of birth',
      monthly_cost: '8000.00',
    },
    {
      level: 'ADVANCED',
      description: 'Fuzzy matching with phone numbers',
      monthly_cost: '20000.00',
    },
  ],
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

describe('MatchingPolicyCard', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the tooling with its cost and saves new thresholds', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(json(policy)))
    vi.stubGlobal('fetch', fetch)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MatchingPolicyCard gameId={3} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/GHS 8,000.00 a month/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Save thresholds' })
    expect(save).toBeDisabled() // nothing changed yet

    fireEvent.change(screen.getByLabelText('Link automatically at'), { target: { value: '0.85' } })
    fireEvent.click(save)
    const posted = () =>
      (fetch.mock.calls as [string, RequestInit][]).find(([, init]) => init.method === 'POST')
    await waitFor(() => expect(posted()).toBeDefined())
    const [url, init] = posted()!
    expect(url).toBe('/api/v1/games/3/matching-policy/')
    expect(JSON.parse(init.body as string)).toEqual({ auto_link: 0.85, review: 0.75 })
  })
})
