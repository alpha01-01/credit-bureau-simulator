import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App systems check', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the database reported by the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: 'simb-api',
            database: { vendor: 'postgresql', server_version: '18.1' },
          }),
          { status: 200 },
        ),
      ),
    )

    renderApp()

    expect(await screen.findByText('postgresql 18.1')).toBeInTheDocument()
  })

  it('explains how to start the backend when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 502 })))

    renderApp()

    expect(await screen.findByText(/The API is unreachable/)).toBeInTheDocument()
  })
})
