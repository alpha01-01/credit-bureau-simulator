import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Review } from '../api/game'
import { ReviewPage } from './ReviewPage'

const tally = { total: 0, right: 0 }
const review: Review = {
  period: '2027-01',
  drill: ['match.all', 'match.right', 'match.false_merge', 'rejected.F001.genuine'],
  figures: {
    period: '2027-01-31',
    match: {
      total: 13,
      right: 10,
      false_merges: 2,
      false_splits: 0,
      other_wrong: 1,
      by: { EMPLOYEE: { total: 13, right: 10 } },
    },
    triage: { ...tally, genuine_returned: 0, wrongly_loaded: 0, other_wrong: 0, by: {} },
    rejected: {
      total: 5,
      genuine: 5,
      rules: [{ rule: 'F001', description: 'Mandatory field is blank', records: 5, genuine: 5 }],
    },
    assets: {
      visible: {
        as_of: '2027-01-29',
        coverage: { period: '2026-12-31', active_borrowers: 278, covered: 167, share: 0.6007 },
        accounts: 238,
        depth_months: 1,
        freshness_days: 29,
        open_accounts: 211,
        audit: {
          accuracy: { share: 0.99, margin: 0.0196, sample: 100 },
          one_person: { share: 1, margin: 0.0196, sample: 100 },
        },
      },
      truth: {
        accuracy: { accounts: 238, right: 236, share: 0.9916 },
        identity: {
          customers: 177,
          false_merges: 2,
          merge_rate: 0.0113,
          people: 175,
          false_splits: 3,
          split_rate: 0.0171,
        },
      },
    },
    consequences: {
      mixed_reports: 0,
      incomplete_reports: 0,
      from_decisions: 0,
      automatic: 0,
      chains: [],
    },
  },
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

describe('ReviewPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reveals the truth and opens the records behind a figure', async () => {
    const fetch = vi.fn((url: string) =>
      Promise.resolve(
        url.includes('/drill/')
          ? json({
              key: 'match.false_merge',
              kind: 'work_items',
              rows: [
                {
                  item: 7,
                  decision: 'SAME_CUSTOMER',
                  correct_decision: 'DIFFERENT_CUSTOMER',
                  correct: false,
                  resolved_by: 'EMPLOYEE',
                  employee: 'Ama Mensah',
                  why_right: 'record is world person 1; candidate is world person 2',
                  submission: 'SUB-1',
                  row: 4,
                },
              ],
            })
          : json(review),
      ),
    )
    vi.stubGlobal('fetch', fetch)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/games/3/reviews/2027-01']}>
          <Routes>
            <Route path="/games/:gameId/reviews/:period" element={<ReviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Data Quality Review: January 2027' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/2 of 177 customers are two or more people/)).toBeInTheDocument()
    // A figure with no records behind it is plain text, not a button.
    expect(screen.queryByRole('button', { name: /false splits/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^2 false merges/ }))
    expect(await screen.findByText('Ama Mensah')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/games/3/reviews/2027-01/drill/?key=match.false_merge',
      expect.anything(),
    )
    expect(screen.getByRole('link', { name: '7' })).toHaveAttribute('href', '/games/3/queue/7')
  })
})
