import { describe, expect, it } from 'vitest'

import { layOut, MAX_PILE, type OfficeData } from './office'

function office(overrides: Partial<OfficeData> = {}): OfficeData {
  return {
    staff: [
      {
        number: 'E0001',
        name: 'Ama Mensah',
        job_title: 'Senior Data Officer',
        state: 'WORKING',
        item: 41,
        morale: 0.7,
      },
      {
        number: 'E0002',
        name: 'Kofi Boateng',
        job_title: 'Data Officer',
        state: 'IDLE',
        item: null,
        morale: 0.7,
      },
      {
        number: 'E0003',
        name: 'Esi Owusu',
        job_title: 'Junior Data Officer',
        state: 'AWAY',
        item: null,
        morale: 0.7,
      },
      {
        number: 'E0004',
        name: 'Yaw Darko',
        job_title: 'Data Officer',
        state: 'GONE',
        item: null,
        morale: 0.2,
      },
    ],
    queue: { open: 9, in_progress: 1, by_type: { MATCH_REVIEW: 9 } },
    systems: { down: false, detail: '', files_waiting: 2, capacity: 'STANDARD' },
    ...overrides,
  }
}

describe('the office floor', () => {
  it('seats the people who are in, and leaves room to hire', () => {
    const floor = layOut(office(), 3)
    const people = floor.desks.filter((d) => d.person)
    expect(people.map((d) => d.person?.number)).toEqual(['E0001', 'E0002', 'E0003'])
    expect(people.map((d) => d.person?.seated)).toEqual([true, true, false])
    expect(floor.desks.length).toBe(6)
    expect(floor.desks[5].person).toBeNull()
    expect(floor.desks[5].to).toBe('/games/3/staff')
  })

  it('opens the item a person is working on, and the staff page for the rest', () => {
    const [working, idle] = layOut(office(), 3).desks
    expect(working.to).toBe('/games/3/queue/41')
    expect(idle.to).toBe('/games/3/staff')
    expect(working.label).toContain('working on an item')
  })

  it('shares the queue across the desks in use, as paper piles', () => {
    const desks = layOut(office(), 3).desks
    expect(desks.map((d) => d.pile)).toEqual([5, 5, 0, 0, 0, 0])
    const flood = layOut(office({ queue: { open: 500, in_progress: 0, by_type: {} } }), 3)
    expect(flood.desks[0].pile).toBe(MAX_PILE)
  })

  it('shows an outage on the server rack, and opens IT from it', () => {
    const down = layOut(
      office({
        systems: { down: true, detail: 'Disk failure.', files_waiting: 3, capacity: 'STANDARD' },
      }),
      3,
    )
    expect(down.rack.down).toBe(true)
    expect(down.rack.label).toContain('Disk failure.')
    expect(down.rack.to).toBe('/games/3/it')
    expect(down.summary).toContain('systems are down')
  })

  it('describes the floor in words, for those who do not see it', () => {
    expect(layOut(office(), 3).summary).toBe(
      '3 staff: 1 working, 1 free, 1 away. 9 item(s) waiting in the queue. The systems are up.',
    )
  })
})
