import { describe, expect, it } from 'vitest'

import {
  cameraAt,
  command,
  fitZoom,
  type FloorData,
  framing,
  layOut,
  MAX_PILE,
  PLANS,
  type PlanCode,
  turned,
} from './office'

const PRD_ROOMS: Record<string, string[]> = {
  GROUND: ['RECEPTION', 'WAITING', 'SUPPORT', 'SALES', 'FINANCE', 'HR', 'CAFETERIA'],
  FIRST: ['DATA_OPERATIONS', 'DATA_ANALYTICS', 'IT', 'PRODUCT', 'SERVER_ROOM', 'TECH_MEETING'],
  SECOND: ['CEO_OFFICE', 'EXECUTIVE', 'BOARDROOM', 'COMPLIANCE', 'EXEC_MEETING'],
  SMALL: ['OPEN_PLAN', 'MEETING', 'SERVER_ROOM', 'KITCHEN'],
  STANDARD: ['RECEPTION', 'OPEN_PLAN', 'CEO_OFFICE', 'MEETING', 'SERVER_ROOM', 'KITCHEN'],
}

function room(code: string, desks = 0, kind: FloorData['rooms'][number]['kind'] = 'DEPARTMENT') {
  return { code, name: code, kind, screen: 'it', summary: `About ${code}.`, desks }
}

function first(overrides: Partial<FloorData> = {}): FloorData {
  return {
    code: 'first',
    name: 'First floor',
    level: 1,
    plan: 'FIRST',
    rooms: [
      room('DATA_OPERATIONS', 6),
      room('DATA_ANALYTICS'),
      room('IT'),
      room('PRODUCT'),
      room('SERVER_ROOM', 0, 'SERVERS'),
      room('TECH_MEETING', 0, 'MEETING'),
    ],
    staff: [
      {
        number: 'E0001',
        name: 'Ama Mensah',
        job_title: 'Senior Data Officer',
        room: 'DATA_OPERATIONS',
        state: 'WORKING',
        item: 41,
        morale: 0.7,
      },
      {
        number: 'E0002',
        name: 'Kofi Boateng',
        job_title: 'Data Officer',
        room: 'DATA_OPERATIONS',
        state: 'IDLE',
        item: null,
        morale: 0.7,
      },
      {
        number: 'E0003',
        name: 'Esi Owusu',
        job_title: 'Junior Data Officer',
        room: 'DATA_OPERATIONS',
        state: 'AWAY',
        item: null,
        morale: 0.7,
      },
    ],
    queue: { open: 30, in_progress: 1, by_type: { MATCH_REVIEW: 30 } },
    systems: { installed: true, down: false, detail: '', files_waiting: 2, capacity: 'STANDARD' },
    ...overrides,
  }
}

/** Does a rectangle lie inside another (both as corner and size)? */
function inside(
  a: { x: number; z: number; w: number; d: number },
  b: { x: number; z: number; w: number; d: number },
) {
  return a.x >= b.x && a.z >= b.z && a.x + a.w <= b.x + b.w && a.z + a.d <= b.z + b.d
}

describe('the plans', () => {
  it("has the PRD's rooms on each floor, inside the floor and not overlapping", () => {
    for (const [code, rooms] of Object.entries(PRD_ROOMS)) {
      const plan = PLANS[code as PlanCode]
      expect(Object.keys(plan.rooms).sort()).toEqual([...rooms].sort())
      const whole = { x: 0, z: 0, w: plan.size[0], d: plan.size[1] }
      const rects = Object.values(plan.rooms)
      for (const r of rects) expect(inside(r, whole)).toBe(true)
      for (const [i, a] of rects.entries())
        for (const b of rects.slice(i + 1)) {
          const apart = a.x + a.w <= b.x || b.x + b.w <= a.x || a.z + a.d <= b.z || b.z + b.d <= a.z
          expect(apart).toBe(true)
        }
    }
  })
})

describe('layOut', () => {
  it('seats the staff in their room, with empty desks to hire into', () => {
    const floor = layOut(first(), 7)
    const ops = floor.desks.filter((d) => d.room === 'DATA_OPERATIONS')
    expect(ops).toHaveLength(6)
    expect(ops.filter((d) => d.person).map((d) => d.person?.name)).toEqual([
      'Ama Mensah',
      'Kofi Boateng',
      'Esi Owusu',
    ])
    expect(ops[0].to).toBe('/games/7/queue/41')
    expect(ops[1].to).toBe('/games/7/staff')
    expect(ops[2].person?.seated).toBe(false) // away on a course
    expect(ops[5].label).toMatch(/room to hire/)
  })

  it('shares the queue across the desks in use, up to a pile limit', () => {
    const floor = layOut(first(), 7)
    const piles = floor.desks.filter((d) => d.person).map((d) => d.pile)
    expect(piles).toEqual([MAX_PILE, MAX_PILE, 0]) // 30 items / 2 desks in use = 15 each
    const light = layOut(first({ queue: { open: 4, in_progress: 0, by_type: {} } }), 7)
    expect(light.desks.filter((d) => d.person).map((d) => d.pile)).toEqual([2, 2, 0])
  })

  it('puts every desk inside its room', () => {
    const floor = layOut(first(), 7)
    const ops = floor.rooms.find((r) => r.code === 'DATA_OPERATIONS')!
    for (const d of floor.desks) {
      expect(Math.abs(d.position[0] - ops.centre[0])).toBeLessThan(ops.size[0] / 2)
      expect(Math.abs(d.position[2] - ops.centre[2])).toBeLessThan(ops.size[1] / 2)
    }
  })

  it('furnishes rooms without desks, each piece opening the room', () => {
    const floor = layOut(first(), 7)
    const racks = floor.fixtures.filter((f) => f.kind === 'rack')
    expect(racks.map((f) => f.room)).toEqual(['SERVER_ROOM', 'SERVER_ROOM'])
    expect(racks[0].to).toBe('/games/7/it')
    expect(floor.fixtures.find((f) => f.room === 'TECH_MEETING')?.kind).toBe('table')
  })

  it("shows the systems' state in the server room's lights", () => {
    expect(layOut(first(), 7).lights).toBe('ok')
    const down = first({
      systems: { installed: true, down: true, detail: 'x', files_waiting: 0, capacity: 'STANDARD' },
    })
    expect(layOut(down, 7).lights).toBe('down')
    const none = first({
      systems: {
        installed: false,
        down: false,
        detail: '',
        files_waiting: 0,
        capacity: 'STANDARD',
      },
    })
    expect(layOut(none, 7).lights).toBe('off')
    expect(layOut(none, 7).summary).toMatch(/No systems yet/)
  })

  it('numbers the rooms for the keyboard and labels each with its line', () => {
    const floor = layOut(first(), 7)
    expect(floor.rooms.map((r) => r.index)).toEqual([1, 2, 3, 4, 5, 6])
    expect(floor.rooms[0].label).toBe('DATA_OPERATIONS: About DATA_OPERATIONS.')
    expect(floor.summary).toMatch(/3 staff here: 1 working, 1 free, 1 away/)
  })

  it("lays a Startup's 45 desks inside its open-plan office", () => {
    const data: FloorData = {
      code: 'office',
      name: 'The office floor',
      level: 0,
      plan: 'STANDARD',
      rooms: [room('OPEN_PLAN', 45), room('SERVER_ROOM', 0, 'SERVERS')],
      staff: [],
    }
    const floor = layOut(data, 7)
    expect(floor.desks).toHaveLength(45)
    const open = floor.rooms[0]
    for (const d of floor.desks) {
      expect(Math.abs(d.position[0] - open.centre[0])).toBeLessThan(open.size[0] / 2)
      expect(Math.abs(d.position[2] - open.centre[2])).toBeLessThan(open.size[1] / 2)
    }
  })
})

describe('the view', () => {
  it('turns in quarter turns, all the way round', () => {
    expect(turned(0, 1)).toBe(1)
    expect(turned(3, 1)).toBe(0)
    expect(turned(0, -1)).toBe(3)
    const a = cameraAt(0, [0, 0, 0])
    const b = cameraAt(2, [0, 0, 0])
    expect(b[0]).toBeCloseTo(-a[0])
    expect(b[2]).toBeCloseTo(-a[2])
    expect(a[0]).toBeGreaterThan(0) // the first turn looks from the front right
    expect(a[2]).toBeGreaterThan(0)
  })

  it('zooms in to a room and back out to the whole floor', () => {
    const floor = layOut(first(), 7)
    const whole = framing(floor, null)
    const server = framing(floor, 'SERVER_ROOM')
    expect(whole.size).toEqual([24, 16])
    expect(server.size).toEqual([5, 5])
    expect(fitZoom(...server.size, 900, 480)).toBeGreaterThan(fitZoom(...whole.size, 900, 480))
    expect(framing(floor, 'NOWHERE')).toEqual(whole)
  })

  it('answers the keyboard', () => {
    expect(command('PageUp')).toEqual({ type: 'floor', by: 1 })
    expect(command('PageDown')).toEqual({ type: 'floor', by: -1 })
    expect(command('ArrowLeft')).toEqual({ type: 'turn', by: -1 })
    expect(command('e')).toEqual({ type: 'turn', by: 1 })
    expect(command('3')).toEqual({ type: 'room', index: 3 })
    expect(command('Escape')).toEqual({ type: 'whole' })
    expect(command('x')).toBeNull()
  })
})
