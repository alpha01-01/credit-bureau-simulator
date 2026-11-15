import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MappingForm } from './SubmissionTools'

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

describe('MappingForm', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('saves only a complete mapping, then sends it', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(json({ mapped: true })))
    vi.stubGlobal('fetch', fetch)
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <MappingForm
          gameId={3}
          reference="SUB-1"
          fileName="ATB.csv"
          offer={{
            received: ['LastName', 'FirstName', 'DOB'],
            suggested: ['', 'FirstName', 'DOB'],
            template: ['Surname', 'FirstName', 'DOB'],
          }}
        />
      </QueryClientProvider>,
    )
    const save = screen.getByRole('button', { name: 'Save mapping and load the file' })
    expect(save).toBeDisabled()
    expect(screen.getByText(/Not yet mapped: Surname/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Template column for LastName'), {
      target: { value: 'Surname' },
    })
    expect(save).toBeEnabled()
    fireEvent.click(save)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/games/3/submissions/SUB-1/files/ATB.csv/mapping/')
    expect(JSON.parse(init.body as string)).toEqual({ columns: ['Surname', 'FirstName', 'DOB'] })
  })
})
