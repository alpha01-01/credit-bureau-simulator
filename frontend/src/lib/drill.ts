import type { Drill } from '../api/game'

/** Where a drill-down goes, relative to the game. */
export function drillPath(gameId: number, drill: Drill): string {
  const params = new URLSearchParams(drill.params)
  const base = `/games/${gameId}`
  const screens: Record<string, string> = {
    ledger: `${base}/finance/ledger`,
    invoices: `${base}/finance/invoices`,
    queue: `${base}/queue`,
    enquiries: `${base}/enquiries`,
    customers: `${base}/customers`,
    submissions: `${base}/submissions`,
  }
  if (drill.screen === 'submission') {
    return `${base}/submissions/${drill.params.reference}`
  }
  const path = screens[drill.screen] ?? base
  const rest = params.toString()
  return rest ? `${path}?${rest}` : path
}
