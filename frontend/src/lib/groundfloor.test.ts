/** The ground floor (P4.5): visitors, Support's tickets, Finance's close, the cafeteria. */
import { describe, expect, it } from 'vitest'

import { stage } from './movement'
import { COLOURS, detailsOf, type FloorData, layOut, MAX_PILE } from './office'

type Staff = FloorData['staff'][number]

function room(
  code: string,
  screen: string,
  desks = 0,
  kind: FloorData['rooms'][number]['kind'] = 'DEPARTMENT',
) {
  return { code, name: code, kind, screen, summary: `About ${code}.`, desks }
}

function member(department: string, desk: string, n: number, o: Partial<Staff> = {}): Staff {
  return {
    number: `${department}-${n}`,
    name: `Team ${n}`,
    job_title: 'Member',
    desk,
    room: desk,
    place: 'DESK',
    activity: 'FREE',
    doing: 'at their desk',
    item: null,
    morale: null,
    managed: true,
    screen: 'staff',
    ...o,
  }
}

function visitor(number: string, at: string, screen = 'disputes'): Staff {
  return {
    number,
    name: 'Ama Serwaa',
    job_title: 'Visitor',
    desk: null,
    room: at,
    place: 'VISIT',
    activity: 'VISITING',
    doing: 'come in person about dispute 3',
    item: null,
    morale: null,
    visitor: true,
    screen,
  }
}

const AGENTS = [1, 2].map((n) =>
  member('CUSTOMER_SUPPORT', 'SUPPORT', n, { activity: 'WORKING', screen: 'support' }),
)

function ground(overrides: Partial<FloorData> = {}): FloorData {
  return {
    code: 'ground',
    name: 'Ground floor',
    level: 0,
    plan: 'GROUND',
    rooms: [
      room('RECEPTION', 'onboarding', 0, 'FACILITY'),
      room('WAITING', 'disputes', 0, 'FACILITY'),
      room('SUPPORT', 'support', 2),
      room('SALES', 'sales', 1),
      room('FINANCE', 'finance', 2),
      room('HR', 'staff', 1),
      room('CAFETERIA', 'staff', 0, 'FACILITY'),
    ],
    staff: [
      ...AGENTS,
      member('SALES', 'SALES', 1, { screen: 'sales' }),
      member('FINANCE', 'FINANCE', 1, { screen: 'close', progress: 0.6 }),
      member('FINANCE', 'FINANCE', 2, { screen: 'close', progress: 0.6 }),
      member('HR', 'HR', 1),
    ],
    visits: [],
    tickets: {
      open: 6,
      overdue: 0,
      today: 6,
      outage_today: 0,
      agents: 2,
      per_day: 30,
      satisfaction: 0.92,
    },
    prospects: [],
    close: {
      period: '2027-01-31',
      ended: true,
      done: 3,
      total: 5,
      items: [
        { title: "The month's usage invoiced", done: true },
        { title: 'Salaries paid', done: true },
        { title: 'Every bill received approved or rejected', done: true },
        { title: 'The bank statement reconciled', done: false },
        { title: 'Budget against actuals reviewed', done: false },
      ],
    },
    welfare: {
      staff: 3,
      day: '08:00-17:00',
      lunch: '12:00-13:00',
      morale: 0.66,
      lowest: { name: 'Kofi Asante', morale: 0.38 },
      low: 1,
      at_risk: 1,
      pay: 0.97,
      below_market: 2,
      queue_per_person: 12,
      heavy: false,
      done_today: 7,
      on_course: 0,
    },
    time: '10:00',
    ...overrides,
  }
}

describe('the ground floor', () => {
  it('stands a visitor at reception, then in the waiting area, in their own colour', () => {
    const signing = layOut(ground({ staff: [...AGENTS, visitor('V-D3', 'RECEPTION')] }), 16)
    const at = signing.figures.find((f) => f.key === 'V-D3')!
    expect(at.room).toBe('RECEPTION')
    expect(at.pose).toBe('standing')
    expect(at.colour).toBe(COLOURS.visitor)
    expect(at.to).toBe('/games/16/disputes')
    expect(signing.summary).toContain('1 visitor(s) in the building.')
    expect(signing.summary).not.toContain('staff work here') // visitors are not staff

    const waiting = layOut(ground({ staff: [...AGENTS, visitor('V-D3', 'WAITING')] }), 16)
    expect(waiting.figures.find((f) => f.key === 'V-D3')!.room).toBe('WAITING')
    expect(waiting.people.map((p) => p.key)).toContain('V-D3') // in the text list too
  })

  it('walks a visitor in from the stairs, and out again when the visit ends', () => {
    const before = layOut(ground(), 16)
    const arrived = layOut(ground({ staff: [...ground().staff, visitor('V-D3', 'RECEPTION')] }), 16)
    const actors = stage(
      stage(new Map(), before.figures, before, true),
      arrived.figures,
      arrived,
      false,
    )
    const walk = actors.get('V-D3')!
    expect(walk.walking).toBe(true)
    expect(walk.path[0]).toEqual(arrived.stairs)
    expect(walk.path).toContainEqual(arrived.doors.RECEPTION)
    // The dispute is settled: the visitor leaves by the stairs.
    const gone = stage(actors, before.figures, before, false).get('V-D3')!
    expect(gone.leaving).toBe(true)
    expect(gone.path.at(-1)).toEqual(before.stairs)
  })

  it('lists reception’s book for the day when looked at closely', () => {
    const book = ['Ama Serwaa, about dispute 3, came at 10:00: in the waiting area']
    const shown = ground({ visits: book })
    expect(detailsOf(shown.rooms[0], shown)).toEqual(book)
    expect(detailsOf(ground().rooms[0], ground())).toEqual(['No visitors yet today.'])
  })

  it('shares the open tickets out across the Support desks, so a wave shows', () => {
    const calm = layOut(ground(), 16)
    const piles = (f: ReturnType<typeof layOut>) =>
      f.desks.filter((d) => d.room === 'SUPPORT').map((d) => d.pile)
    expect(piles(calm)).toEqual([3, 3])
    const wave = layOut(
      ground({ tickets: { ...ground().tickets!, open: 19, today: 19, outage_today: 15 } }),
      16,
    )
    expect(piles(wave)).toEqual([10, 10])
    const flood = layOut(ground({ tickets: { ...ground().tickets!, open: 90 } }), 16)
    expect(piles(flood)).toEqual([MAX_PILE, MAX_PILE])
    // No agents: nobody answers, and the tickets pile up on the empty desks.
    const none = layOut(ground({ staff: [] }), 16)
    expect(none.desks.filter((d) => d.room === 'SUPPORT').every((d) => !d.person)).toBe(true)
    expect(piles(none)).toEqual([3, 3])
    // Only Support's desks carry tickets.
    expect(calm.desks.filter((d) => d.room !== 'SUPPORT').every((d) => d.pile === 0)).toBe(true)
    const support = ground()
    expect(detailsOf(support.rooms[2], support)).toEqual([
      'Open tickets: 6, 0 past their time',
      'Today: 6 came in',
      'Agents: 2, answering 30 a day, oldest first',
      'Answered on time: 92% over three months',
    ])
  })

  it('shows the month’s close on Finance’s desks and its checklist', () => {
    const floor = layOut(ground(), 16)
    const finance = floor.desks.filter((d) => d.room === 'FINANCE')
    expect(finance.map((d) => d.progress)).toEqual([0.6, 0.6])
    expect(finance.every((d) => d.to === '/games/16/close')).toBe(true)
    const shown = ground()
    expect(detailsOf(shown.rooms[4], shown)).toEqual([
      'Closing January 2027: 3 of 5 done',
      "Done: The month's usage invoiced",
      'Done: Salaries paid',
      'Done: Every bill received approved or rejected',
      'To do: The bank statement reconciled',
      'To do: Budget against actuals reviewed',
    ])
  })

  it('gives the staff’s welfare when the cafeteria is looked at closely', () => {
    const shown = ground()
    const lines = detailsOf(shown.rooms[6], shown)
    expect(lines.map((l) => l.split(':')[0])).toEqual([
      'Morale',
      'Taking breaks for low morale (below 0.5)',
      'Pay',
      'Workload',
      'Hours',
    ])
    expect(lines[0]).toBe('Morale: 0.66 on average across 3 staff; lowest Kofi Asante (0.38)')
    expect(lines[2]).toBe('Pay: 97% of the market rate on average; 2 below it')
    expect(lines[4]).toContain('7 item(s) done today')
    const empty = ground({ welfare: { staff: 0, day: '08:00-17:00', lunch: '12:00-13:00' } })
    expect(detailsOf(empty.rooms[6], empty)[0]).toBe('Nobody on the payroll yet.')
  })

  it('opens a 2D screen from every object on the floor', () => {
    const floor = layOut(ground({ staff: [...ground().staff, visitor('V-D3', 'WAITING')] }), 16)
    const to = (room: string) => floor.desks.filter((d) => d.room === room).map((d) => d.to)
    expect(to('SUPPORT')).toEqual(['/games/16/support', '/games/16/support'])
    expect(to('SALES')).toEqual(['/games/16/sales'])
    expect(to('HR')).toEqual(['/games/16/staff'])
    const fixtures = Object.fromEntries(floor.fixtures.map((f) => [f.key, [f.kind, f.to]]))
    expect(fixtures).toEqual({
      'RECEPTION-0': ['counter', '/games/16/onboarding'],
      'WAITING-0': ['sofa', '/games/16/disputes'],
      'WAITING-1': ['sofa', '/games/16/disputes'],
      'CAFETERIA-0': ['table', '/games/16/staff'],
      'CAFETERIA-1': ['table', '/games/16/staff'],
      'CAFETERIA-2': ['table', '/games/16/staff'],
    })
    expect(floor.rooms.every((r) => r.to.startsWith('/games/16/'))).toBe(true)
    expect(floor.figures.every((f) => f.to.startsWith('/games/16/'))).toBe(true)
  })
})
