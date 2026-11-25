import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { useHandbook } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Badge, Card, Failed, Loading, Page } from '../components/ui'

/**
 * The Bureau Handbook (v1 P2.11, v2 P3.14; Document 07, Section 11.4): each concept the player meets,
 * with how it works in the Ghanaian market and the law it rests on.
 */
export function HandbookPage() {
  const gameId = useGameId()
  const handbook = useHandbook(gameId)
  const { hash } = useLocation()
  const [search, setSearch] = useState('')
  useEffect(() => {
    if (hash && handbook.data) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash, handbook.data])
  if (handbook.isPending) return <Loading what="the Handbook" />
  if (handbook.isError) return <Failed error={handbook.error} />
  const needle = search.trim().toLowerCase()
  const entries = handbook.data.entries.filter(
    (e) => !needle || `${e.title} ${e.body} ${e.in_practice}`.toLowerCase().includes(needle),
  )
  return (
    <Page title="Bureau Handbook" subtitle={handbook.data.disclaimer}>
      <div>
        <label htmlFor="handbook-search" className="sr-only">
          Search the Handbook
        </label>
        <input
          id="handbook-search"
          type="search"
          placeholder="Search the Handbook"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-sm rounded border border-slate-300 px-2 py-1 text-sm"
        />
      </div>
      {entries.map((e) => (
        <section key={e.key} id={e.key} className="scroll-mt-40">
          <Card title={e.title}>
            <div className="space-y-2 text-sm">
              {(e.added !== 'v1' || (e.regulatory && !e.reviewed)) && (
                <div className="flex flex-wrap gap-2">
                  {e.added !== 'v1' && <Badge tone="info">New in {e.added}</Badge>}
                  {e.regulatory && !e.reviewed && (
                    <Badge tone="warn">Regulatory content awaiting the owner's review</Badge>
                  )}
                </div>
              )}
              <p>{e.body}</p>
              <p>
                <span className="font-medium">In practice: </span>
                {e.in_practice}
              </p>
              {e.citations.length > 0 && (
                <ul className="text-xs text-slate-600">
                  {e.citations.map((c) => (
                    <li key={`${c.instrument}-${c.provision}`}>
                      {c.instrument}, {c.provision}
                      {c.reference && ` (reference ${c.reference})`}
                      {c.status !== 'CONFIRMED' && ': to be confirmed against the text'}
                    </li>
                  ))}
                </ul>
              )}
              {e.screen && (
                <Link
                  to={`/games/${gameId}/${e.screen}`}
                  className="text-xs text-brand hover:underline"
                >
                  See it in the game
                </Link>
              )}
            </div>
          </Card>
        </section>
      ))}
    </Page>
  )
}
