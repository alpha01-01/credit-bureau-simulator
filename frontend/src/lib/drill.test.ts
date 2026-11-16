import { describe, expect, it } from 'vitest'

import { drillPath } from './drill'

describe('drillPath', () => {
  it('takes a dashboard figure to the records behind it', () => {
    expect(
      drillPath(3, { screen: 'ledger', params: { account: '4000', start: '2027-01-01' } }),
    ).toBe('/games/3/finance/ledger?account=4000&start=2027-01-01')
    expect(drillPath(3, { screen: 'queue', params: { status: 'OPEN' } })).toBe(
      '/games/3/queue?status=OPEN',
    )
    expect(drillPath(3, { screen: 'customers', params: {} })).toBe('/games/3/customers')
  })

  it('opens a single submission by reference', () => {
    expect(
      drillPath(3, { screen: 'submission', params: { reference: 'SUB-202612-ATB-000001' } }),
    ).toBe('/games/3/submissions/SUB-202612-ATB-000001')
  })

  it('takes department notices to their screens', () => {
    expect(drillPath(3, { screen: 'it', params: {} })).toBe('/games/3/it')
    expect(drillPath(3, { screen: 'sales', params: {} })).toBe('/games/3/sales')
    expect(drillPath(3, { screen: 'staff', params: {} })).toBe('/games/3/staff')
    expect(drillPath(3, { screen: 'health', params: {} })).toBe('/games/3/health')
  })
})
