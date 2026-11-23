import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Clock, Notice } from '../api/game'
import { EventsPage } from '../pages/EventsPage'
import { ClockBar } from './ClockBar'

const cashLow: Notice = {
  id: 7,
  tick: 1,
  at: '2027-01-04T08:00:00Z',
  kind: 'CASH_LOW',
  severity: 'CRITICAL',
  title: "Cash is below one month's payroll",
  detail: 'The bank holds GHS 1,000.00.',
  drill: { screen: 'ledger', params: { account: '1010' } },
  deadline: false,
  paused: true,
}

const clock: Clock = {
  game: 3,
  tick: 1,
  now: '2027-01-04T08:15:00Z',
  date: '2027-01-04',
  weekday: 'Monday',
  time: '08:15',
  status: 'PAUSED',
  ended_reason: '',
  speed: 1,
  next_event: { tick: 2, at: '2027-01-04T08:15:00Z' },
  pending_events: 3,
  reporting_data_through: '2027-01-31',
  pause_rules: { severities: ['CRITICAL'], deadlines: true },
  stopped_by: cashLow,
  latest_notice: 7,
  role: { code: 'CEO', title: 'Chief Executive', screens: [''], ready: true, ready_at: null },
}

function wrap(children: ReactNode, path = '/games/3') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/games/:gameId/*" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

describe('ClockBar', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('says why the clock stopped, with a link to the records', () => {
    wrap(<ClockBar gameId={3} clock={clock} />)
    const banner = screen.getByRole('alert')
    expect(banner).toHaveTextContent("Clock stopped: Cash is below one month's payroll")
    expect(screen.getByRole('link', { name: /Why\? Cash is below/ })).toHaveAttribute(
      'href',
      '/games/3/finance/ledger?account=1010',
    )
  })

  it('ends the game with no controls, and points to what happened', () => {
    wrap(<ClockBar gameId={3} clock={{ ...clock, status: 'ENDED', ended_reason: 'INSOLVENT' }} />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The game is over: the bureau is insolvent.',
    )
    expect(screen.queryByRole('button', { name: 'Run' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See what happened' })).toHaveAttribute(
      'href',
      '/games/3/health',
    )
  })

  it('shows no banner when the player paused the clock', () => {
    wrap(<ClockBar gameId={3} clock={{ ...clock, stopped_by: null }} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('changes the pause rules', async () => {
    const fetch = vi.fn().mockResolvedValue(json(clock))
    vi.stubGlobal('fetch', fetch)
    wrap(<ClockBar gameId={3} clock={clock} />)
    fireEvent.click(screen.getByText('Stop for…'))
    fireEvent.click(screen.getByLabelText('Warnings'))
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/games/3/clock/pause-rules/')
    expect(JSON.parse(init.body as string)).toEqual({
      severities: ['CRITICAL', 'WARNING'],
      deadlines: true,
    })
  })
})

describe('EventsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists what happened, newest first, each with a Why? link', async () => {
    const arrived: Notice = {
      ...cashLow,
      id: 6,
      kind: 'FILES_ARRIVED',
      severity: 'INFO',
      title: 'Files arrived from Atlas Bank',
      detail: '',
      drill: { screen: 'submission', params: { reference: 'SUB-1' } },
      paused: false,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.includes('/feed/')
            ? json({ notices: [cashLow, arrived], more: false })
            : json({
                id: 3,
                bureau: 'B',
                world: 1,
                setup_status: 'READY',
                setup_message: '',
                clock,
              }),
        ),
      ),
    )
    wrap(<EventsPage />, '/games/3/events')
    const items = await screen.findAllByRole('listitem')
    expect(items[0]).toHaveTextContent("Cash is below one month's payroll (stopped the clock)")
    expect(items[1]).toHaveTextContent('Files arrived from Atlas Bank')
    expect(screen.getAllByRole('link', { name: /^Why\?/ })[1]).toHaveAttribute(
      'href',
      '/games/3/submissions/SUB-1',
    )
  })
})
