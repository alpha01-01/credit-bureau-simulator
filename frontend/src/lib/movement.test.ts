import { describe, expect, it } from 'vitest'

import { crowded, daylight, LONGEST_WALK, poseOf, route, stage, step, type Actor } from './movement'
import { type Floor, type FloorData, layOut, type Point } from './office'

type Staff = FloorData['staff'][number]

function room(code: string, desks = 0, kind: FloorData['rooms'][number]['kind'] = 'DEPARTMENT') {
  return { code, name: code, kind, screen: 'it', summary: `About ${code}.`, desks }
}

function person(number: string, overrides: Partial<Staff> = {}): Staff {
  return {
    number,
    name: `Person ${number}`,
    job_title: 'Data Officer',
    desk: 'DATA_OPERATIONS',
    room: 'DATA_OPERATIONS',
    place: 'DESK',
    activity: 'FREE',
    doing: 'at their desk, nothing to do',
    item: null,
    morale: 0.7,
    ...overrides,
  }
}

const IN_REVIEW: Partial<Staff> = {
  room: 'TECH_MEETING',
  place: 'MEETING_ROOM',
  activity: 'DATA_QUALITY_REVIEW',
  doing: 'in the Data Quality Review',
}

function first(staff: Staff[], overrides: Partial<FloorData> = {}): Floor {
  return layOut(
    {
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
      staff,
      time: '10:00',
      ...overrides,
    },
    16,
  )
}

/** Runs a scene's walks to their end, a frame at a time, recording who was where. */
function play(actors: Map<string, Actor>, seconds = LONGEST_WALK + 1) {
  const seen = new Map<string, { at: Point; pose: string }[]>()
  for (let t = 0; t < seconds; t += 1 / 60) {
    for (const [key, a] of actors) {
      if (!step(a, 1 / 60)) actors.delete(key)
      else seen.set(key, [...(seen.get(key) ?? []), { at: [...a.at], pose: poseOf(a) }])
    }
  }
  return seen
}

const near = (a: Point, b: Point, within = 0.05) => Math.hypot(a[0] - b[0], a[2] - b[2]) < within
const spotOf = (floor: Floor, key: string) => floor.figures.find((f) => f.key === key)!.spot

describe('figures', () => {
  it('seats people at their desks facing the screen, and stands visitors facing the room', () => {
    const floor = first([person('E1'), person('E2', IN_REVIEW)])
    const seated = floor.figures.find((f) => f.key === 'E1')!
    const desk = floor.desks.find((d) => d.key === 'E1')!
    expect(seated.pose).toBe('seated')
    expect(seated.spot[0]).toBeCloseTo(desk.position[0])
    expect(seated.spot[2]).toBeGreaterThan(desk.position[2]) // on the chair, behind the desk
    expect(Math.cos(seated.facing)).toBeCloseTo(-1) // towards the screen, at -z
    const standing = floor.figures.find((f) => f.key === 'E2')!
    expect(standing).toMatchObject({ pose: 'standing', room: 'TECH_MEETING' })
    expect(floor.figures.map((f) => f.key)).toEqual(['E1', 'E2'])
  })

  it('leaves out those who are not on the floor', () => {
    const out = person('E3', { room: null, place: 'OUT', activity: 'TRAINING' })
    expect(first([person('E1'), out]).figures.map((f) => f.key)).toEqual(['E1'])
  })

  it('gives every room a door inside it, and the floor its stairs at the front', () => {
    const floor = first([])
    for (const r of floor.rooms) {
      const d = floor.doors[r.code]
      expect(Math.abs(d[0] - r.centre[0])).toBeLessThanOrEqual(r.size[0] / 2)
      expect(Math.abs(d[2] - r.centre[2])).toBeLessThanOrEqual(r.size[1] / 2)
    }
    expect(floor.stairs[2]).toBeGreaterThan(floor.size[1] / 2)
  })
})

describe('walking', () => {
  it('puts everyone in place at once on the first look at a floor', () => {
    const floor = first([person('E1'), person('E2', IN_REVIEW)])
    const actors = stage(new Map(), floor.figures, floor, true)
    for (const a of actors.values()) {
      expect(a.walking).toBe(false)
      expect(a.at).toEqual(spotOf(floor, a.key))
    }
  })

  it('walks a hire in from the stairs and sits them down at their desk', () => {
    const before = first([person('E1')])
    const after = first([person('E1'), person('E2')])
    const actors = stage(
      stage(new Map(), before.figures, before, true),
      after.figures,
      after,
      false,
    )
    const hire = actors.get('E2')!
    expect(hire.walking).toBe(true)
    expect(hire.at).toEqual(after.stairs)
    expect(actors.get('E1')!.walking).toBe(false) // nobody else moves
    const seen = play(actors).get('E2')!
    expect(seen.some((s) => s.pose === 'walking')).toBe(true)
    expect(seen.at(-1)!.pose).toBe('seated')
    expect(seen.at(-1)!.at).toEqual(spotOf(after, 'E2'))
    // Through the door of Data Operations on the way.
    expect(seen.some((s) => near(s.at, after.doors.DATA_OPERATIONS, 0.1))).toBe(true)
  })

  it('walks someone to the Data Quality Review in the meeting room, and back afterwards', () => {
    const atDesk = first([person('E1')])
    const inReview = first([person('E1', IN_REVIEW)])
    let actors = stage(new Map(), atDesk.figures, atDesk, true)

    actors = stage(actors, inReview.figures, inReview, false)
    expect(actors.get('E1')!.path).toEqual([
      spotOf(atDesk, 'E1'),
      inReview.doors.DATA_OPERATIONS,
      inReview.doors.TECH_MEETING,
      spotOf(inReview, 'E1'),
    ])
    let seen = play(actors).get('E1')!
    expect(seen[0].pose).toBe('walking')
    expect(seen.at(-1)).toEqual({ at: spotOf(inReview, 'E1'), pose: 'standing' })

    actors = stage(actors, atDesk.figures, atDesk, false)
    seen = play(actors).get('E1')!
    expect(seen.some((s) => near(s.at, atDesk.doors.TECH_MEETING, 0.1))).toBe(true)
    expect(seen.at(-1)).toEqual({ at: spotOf(atDesk, 'E1'), pose: 'seated' })
  })

  it('walks everyone out by the stairs after hours, and then no longer draws them', () => {
    const day = first([person('E1'), person('E2')])
    const night = first([person('E1', { room: null, place: 'OUT', activity: 'AFTER_HOURS' })], {
      after_hours: true,
    })
    const actors = stage(stage(new Map(), day.figures, day, true), night.figures, night, false)
    expect([...actors.values()].every((a) => a.leaving && a.walking)).toBe(true)
    expect(actors.get('E1')!.path.at(-1)).toEqual(night.stairs)
    play(actors)
    expect(actors.size).toBe(0)
  })

  it('turns someone round mid-walk from where they are drawn', () => {
    const atDesk = first([person('E1')])
    const inReview = first([person('E1', IN_REVIEW)])
    const actors = stage(
      stage(new Map(), atDesk.figures, atDesk, true),
      inReview.figures,
      inReview,
      false,
    )
    const a = actors.get('E1')!
    step(a, 1)
    const midway: Point = [...a.at]
    const back = stage(actors, atDesk.figures, atDesk, false).get('E1')!
    expect(back.path[0]).toEqual(midway)
    expect(back.path.at(-1)).toEqual(spotOf(atDesk, 'E1'))
  })

  it('finishes every walk within the longest walk allowed', () => {
    const floor = first([])
    const far = route({ spot: [-11, 0, -7], room: 'DATA_OPERATIONS' }, null, floor)
    const a = walkOf(far)
    expect(a.length).toBeGreaterThan(LONGEST_WALK * 2.2) // faster than walking pace
    for (let t = 0; t < LONGEST_WALK + 0.05; t += 0.05) step(a, 0.05)
    expect(a.walking).toBe(false)
  })
})

/** An actor already on a walk, for the timing test. */
function walkOf(path: Point[]): Actor {
  const length = path
    .slice(1)
    .reduce((n, p, i) => n + Math.hypot(p[0] - path[i][0], p[2] - path[i][2]), 0)
  return {
    key: 'X',
    figure: {
      key: 'X',
      room: 'DATA_OPERATIONS',
      spot: path[0],
      pose: 'standing',
      facing: 0,
      colour: '#000',
      label: '',
      to: '',
    },
    path,
    length,
    travelled: 0,
    speed: Math.max(2.2, length / LONGEST_WALK),
    leaving: true,
    at: [...path[0]],
    heading: 0,
    walking: true,
  }
}

describe('the light', () => {
  it('is brightest at midday, lower at either end of the day, and dark after hours', () => {
    const morning = daylight('08:00', false)
    const noon = daylight('12:30', false)
    const evening = daylight('16:45', false)
    const night = daylight('17:00', true)
    expect(noon.sun).toBeGreaterThan(morning.sun)
    expect(noon.sun).toBeGreaterThan(evening.sun)
    expect(noon.sunAt[1]).toBeGreaterThan(morning.sunAt[1])
    expect(Math.sign(morning.sunAt[0])).toBe(-Math.sign(evening.sunAt[0])) // east, then west
    expect(night.dark && !noon.dark).toBe(true)
    expect(night.ambient).toBeLessThan(morning.ambient)
    expect(night.sky).not.toBe(noon.sky)
  })
})

describe('the busiest case', () => {
  it('crowds a floor and moves everyone at once from one phase to the next', () => {
    const data: FloorData = {
      code: 'first',
      name: 'First floor',
      level: 1,
      plan: 'FIRST',
      rooms: [room('DATA_OPERATIONS', 6), room('TECH_MEETING', 0, 'MEETING')],
      staff: [],
    }
    const desks = layOut(crowded(data, 45, 0), 16)
    const meeting = layOut(crowded(data, 45, 1), 16)
    expect(desks.figures).toHaveLength(45)
    expect(desks.figures.every((f) => f.pose === 'seated')).toBe(true)
    expect(meeting.figures.every((f) => f.room === 'TECH_MEETING')).toBe(true)
    const actors = stage(
      stage(new Map(), desks.figures, desks, true),
      meeting.figures,
      meeting,
      false,
    )
    expect([...actors.values()].filter((a) => a.walking)).toHaveLength(45)
  })
})
