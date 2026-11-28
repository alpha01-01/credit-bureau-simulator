/** The first floor's departments (P4.4): racks, analytics screens, products, IT at the racks. */
import { describe, expect, it } from 'vitest'

import { stage } from './movement'
import { COLOURS, detailsOf, type FloorData, layOut } from './office'

type Staff = FloorData['staff'][number]

function room(
  code: string,
  screen: string,
  desks = 0,
  kind: FloorData['rooms'][number]['kind'] = 'DEPARTMENT',
) {
  return { code, name: code, kind, screen, summary: `About ${code}.`, desks }
}

function team(department: string, n: number, overrides: Partial<Staff> = {}): Staff {
  return {
    number: `${department}-${n}`,
    name: `Team ${n}`,
    job_title: 'Member',
    desk: department,
    room: department,
    place: 'DESK',
    activity: 'FREE',
    doing: 'at their desk',
    item: null,
    morale: null,
    managed: true,
    screen: department === 'IT' ? 'it' : 'products',
    ...overrides,
  }
}

const SYSTEMS: NonNullable<FloorData['systems']> = {
  installed: true,
  down: false,
  detail: '',
  files_waiting: 1,
  capacity: 'STANDARD',
  utilisation: 0.5,
  tonight: { waiting: 1, capacity: 2 },
  storage: { customers: 1200, accounts: 3400 },
  availability: 0.981,
  maintenance: 'Running normally: no outage so far.',
  racks: 2,
}

const RESTORING: Partial<Staff> = {
  place: 'SERVER_ROOM',
  room: 'SERVER_ROOM',
  activity: 'RESTORING',
  doing: 'at the racks, restoring the systems',
}

function first(overrides: Partial<FloorData> = {}): FloorData {
  return {
    code: 'first',
    name: 'First floor',
    level: 1,
    plan: 'FIRST',
    rooms: [
      room('DATA_OPERATIONS', 'queue', 6),
      room('DATA_ANALYTICS', 'analytics', 2),
      room('IT', 'it', 2),
      room('PRODUCT', 'products', 1),
      room('SERVER_ROOM', 'it', 0, 'SERVERS'),
      room('TECH_MEETING', 'reviews', 0, 'MEETING'),
    ],
    staff: [
      team('DATA_ANALYTICS', 1, {
        activity: 'WORKING',
        screen: 'scorecards/1',
        model: { number: 1, term: 'SHORT', status: 'DEPLOYED' },
      }),
      team('DATA_ANALYTICS', 2, {
        activity: 'WORKING',
        screen: 'scorecards/2',
        model: { number: 2, term: 'COMPOSITE', status: 'DRAFT' },
      }),
      team('IT', 1),
      team('IT', 2),
      team('PRODUCT', 1, { activity: 'WORKING', product: 'CREDIT_SCORE' }),
    ],
    queue: { open: 8, in_progress: 0, by_type: {} },
    systems: SYSTEMS,
    analytics: {
      models: [
        { number: 1, term: 'SHORT', status: 'DEPLOYED' },
        { number: 2, term: 'COMPOSITE', status: 'DRAFT' },
      ],
    },
    developments: [
      { code: 'CREDIT_SCORE', name: 'Credit score', progress: 0.4, ready_on: '2027-02-02' },
    ],
    time: '10:00',
    ...overrides,
  }
}

describe('the first floor', () => {
  it('lights each analyst’s screen by their scorecard and opens it', () => {
    const floor = layOut(first(), 16)
    const desks = floor.desks.filter((d) => d.room === 'DATA_ANALYTICS')
    expect(desks.map((d) => d.screen)).toEqual([COLOURS.screenDeployed, COLOURS.screenDraft])
    expect(desks.map((d) => d.to)).toEqual(['/games/16/scorecards/1', '/games/16/scorecards/2'])
    expect(desks.every((d) => d.pile === 0)).toBe(true) // the queue is Data Operations' work
    const analytics = floor.rooms.find((r) => r.code === 'DATA_ANALYTICS')!
    expect(analytics.details).toEqual([
      'Scorecard 1 (short term): deployed',
      'Scorecard 2 (composite): a draft',
    ])
  })

  it('shows each product’s progress on its desk and in the room', () => {
    const floor = layOut(first(), 16)
    const desk = floor.desks.find((d) => d.room === 'PRODUCT')!
    expect(desk.progress).toBe(0.4)
    expect(desk.to).toBe('/games/16/products')
    expect(floor.rooms.find((r) => r.code === 'PRODUCT')!.details).toEqual([
      'Credit score: 40% done, ready on 2 Feb 2027',
    ])
  })

  it('draws a rack for each file a night, and the server room’s four readings', () => {
    const floor = layOut(first(), 16)
    const racks = floor.fixtures.filter((f) => f.kind === 'rack')
    expect(racks).toHaveLength(2)
    expect(racks.every((r) => r.to === '/games/16/it')).toBe(true)
    expect(racks[0].label).toContain('Utilisation: 50%')
    const high = layOut(first({ systems: { ...SYSTEMS, capacity: 'HIGH', racks: 5 } }), 16)
    expect(high.fixtures.filter((f) => f.kind === 'rack')).toHaveLength(5)
    const lines = detailsOf(first().rooms[4], first())
    expect(lines.map((l) => l.split(':')[0])).toEqual([
      'Utilisation',
      'Storage',
      'Availability',
      'Maintenance',
    ])
    expect(lines[1]).toBe('Storage: 1,200 customers, 3,400 credit accounts')
    expect(lines[2]).toBe('Availability: 98.1% over the last 20 working days')
  })

  it('turns the racks red in an outage and stands IT at them, facing their lights', () => {
    const down = first({
      systems: { ...SYSTEMS, down: true, detail: 'The database server failed.' },
      staff: [team('IT', 1, RESTORING), team('IT', 2, RESTORING)],
    })
    const floor = layOut(down, 16)
    expect(floor.lights).toBe('down')
    const racks = floor.fixtures.filter((f) => f.kind === 'rack')
    const at = floor.figures.filter((f) => f.room === 'SERVER_ROOM')
    expect(at).toHaveLength(2)
    at.forEach((f, i) => {
      expect(Math.abs(f.spot[0] - racks[i].position[0])).toBeLessThan(0.5)
      expect(f.spot[2]).toBeGreaterThan(racks[i].position[2]) // in front of the rack
      expect(Math.cos(f.facing)).toBeCloseTo(-1) // facing it
      expect(f.colour).toBe(COLOURS.restoring)
      expect(f.to).toBe('/games/16/it')
    })
    // Their desks stay theirs, empty, while they are away.
    expect(
      floor.desks.filter((d) => d.room === 'IT').every((d) => d.person && !d.person.seated),
    ).toBe(true)
  })

  it('walks IT from their desks to the racks on the next refresh', () => {
    const up = layOut(first({ staff: [team('IT', 1), team('IT', 2)] }), 16)
    const down = layOut(
      first({
        systems: { ...SYSTEMS, down: true },
        staff: [team('IT', 1, RESTORING), team('IT', 2, RESTORING)],
      }),
      16,
    )
    const actors = stage(stage(new Map(), up.figures, up, true), down.figures, down, false)
    for (const key of ['IT-1', 'IT-2']) {
      const a = actors.get(key)!
      expect(a.walking).toBe(true)
      expect(a.path.at(-1)).toEqual(down.figures.find((f) => f.key === key)!.spot)
      expect(a.path).toContainEqual(down.doors.SERVER_ROOM)
    }
  })

  it('opens the room’s own screen from an empty desk outside Data Operations', () => {
    const floor = layOut(first({ staff: [] }), 16)
    const product = floor.desks.find((d) => d.room === 'PRODUCT')!
    expect(product.person).toBeNull()
    expect(product.to).toBe('/games/16/products')
    expect(product.label).not.toContain('room to hire')
    const dataOps = floor.desks.find((d) => d.room === 'DATA_OPERATIONS')!
    expect(dataOps.to).toBe('/games/16/staff')
  })
})
