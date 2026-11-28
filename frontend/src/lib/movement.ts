/**
 * People moving about the office (P4.3), and its light by the time of day.
 *
 * Decoration over the state, never state: the server says where each person is at the
 * tick shown (P4.2), and when that changes between two refreshes the page walks them
 * from where they were drawn to where they now are, along simple paths between the
 * rooms' doors and the stairs. Pure, so the walks are tested without WebGL; the page
 * calls ``step`` once a frame and draws what it gives.
 */
import type { Figure, Floor, FloorData, Point } from './office'

/** Walking pace, in metres a second; long walks go faster so none takes over LONGEST_WALK. */
export const WALK_SPEED = 2.2
export const LONGEST_WALK = 6

/** Someone being drawn: where they are now, and the walk they are on, if any. */
export type Actor = {
  key: string
  /** Where they are going and how they rest there; for someone leaving, where they were. */
  figure: Figure
  path: Point[]
  length: number
  travelled: number
  speed: number
  /** Walking off the floor, to the stairs: gone when they reach them. */
  leaving: boolean
  at: Point
  heading: number
  walking: boolean
}

type Where = { spot: Point; room: string | null }
type Ways = Pick<Floor, 'doors' | 'stairs'>

const distance = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[2] - a[2])

function lengthOf(path: Point[]): number {
  let total = 0
  for (let i = 1; i < path.length; i++) total += distance(path[i - 1], path[i])
  return total
}

/** Drop points that repeat the one before, so no leg of a walk has no length. */
function tidy(path: Point[]): Point[] {
  return path.filter((p, i) => i === 0 || distance(path[i - 1], p) > 1e-6)
}

/**
 * The way from one place to another: out of a room by its door, into the next by its
 * door, and on or off the floor by the stairs. ``null`` is off the floor.
 */
export function route(from: Where | null, to: Where | null, ways: Ways): Point[] {
  const door = (room: string | null) => (room ? ways.doors[room] : undefined)
  const points: (Point | undefined)[] = []
  if (from === null && to === null) return []
  if (from === null) points.push(ways.stairs, door(to!.room), to!.spot)
  else if (to === null) points.push(from.spot, door(from.room), ways.stairs)
  else if (from.room === to.room) points.push(from.spot, to.spot)
  else points.push(from.spot, door(from.room), door(to.room), to.spot)
  return tidy(points.filter((p): p is Point => p !== undefined))
}

function walk(key: string, figure: Figure, path: Point[], leaving: boolean): Actor {
  const length = lengthOf(path)
  const start = path[0] ?? figure.spot
  return {
    key,
    figure,
    path,
    length,
    travelled: 0,
    speed: Math.max(WALK_SPEED, length / LONGEST_WALK),
    leaving,
    at: [...start],
    heading: path.length > 1 ? headingOf(path[0], path[1]) : figure.facing,
    walking: length > 0,
  }
}

function placed(figure: Figure): Actor {
  return walk(figure.key, figure, [], false)
}

const same = (a: Point, b: Point) => distance(a, b) < 1e-6

/**
 * The people to draw after a refresh, from those drawn before it.
 *
 * ``fresh`` (the first look at a floor) puts everyone in their place at once. After
 * that, someone new walks in from the stairs, someone gone walks out to them, and
 * someone whose place changed walks there from wherever they are drawn, mid-walk or not.
 */
export function stage(
  before: Map<string, Actor>,
  figures: Figure[],
  ways: Ways,
  fresh: boolean,
): Map<string, Actor> {
  const after = new Map<string, Actor>()
  for (const f of figures) {
    const was = fresh ? undefined : before.get(f.key)
    if (fresh) after.set(f.key, placed(f))
    else if (!was) after.set(f.key, walk(f.key, f, route(null, f, ways), false))
    else if (!was.leaving && same(was.figure.spot, f.spot)) {
      after.set(f.key, { ...was, figure: f }) // still on the way, or there: new colours only
    } else {
      // Mid-walk, they set off from where they are drawn, straight for the new room's door.
      const from: Where = { spot: was.at, room: was.walking ? null : was.figure.room }
      const door = f.room !== was.figure.room ? ways.doors[f.room] : undefined
      const path = was.walking
        ? tidy(door ? [was.at, door, f.spot] : [was.at, f.spot])
        : route(from, f, ways)
      after.set(f.key, walk(f.key, f, path, false))
    }
  }
  if (!fresh) {
    for (const [key, was] of before) {
      if (after.has(key)) continue
      if (was.leaving) after.set(key, was)
      else {
        const from: Where = { spot: was.at, room: was.walking ? null : was.figure.room }
        after.set(key, walk(key, was.figure, route(from, null, ways), true))
      }
    }
  }
  return after
}

function headingOf(a: Point, b: Point): number {
  return Math.atan2(b[0] - a[0], b[2] - a[2])
}

/**
 * Moves someone ``seconds`` further along their walk, in place (it runs every frame).
 * Returns false once someone leaving has reached the stairs: they are no longer drawn.
 */
export function step(actor: Actor, seconds: number): boolean {
  if (!actor.walking) return true
  actor.travelled = Math.min(actor.length, actor.travelled + actor.speed * seconds)
  let left = actor.travelled
  for (let i = 1; i < actor.path.length; i++) {
    const a = actor.path[i - 1]
    const b = actor.path[i]
    const leg = distance(a, b)
    if (left <= leg || i === actor.path.length - 1) {
      const k = leg > 0 ? Math.min(1, left / leg) : 1
      // In place: this runs for everyone, every frame, so it makes no garbage.
      actor.at[0] = a[0] + (b[0] - a[0]) * k
      actor.at[2] = a[2] + (b[2] - a[2]) * k
      actor.heading = headingOf(a, b)
      break
    }
    left -= leg
  }
  if (actor.travelled >= actor.length) {
    actor.walking = false
    if (actor.leaving) return false
    actor.at = [...actor.figure.spot]
    actor.heading = actor.figure.facing
  }
  return true
}

/** How someone is drawn this frame: walking, or resting in their figure's pose. */
export function poseOf(actor: Actor): 'walking' | 'seated' | 'standing' {
  return actor.walking ? 'walking' : actor.figure.pose
}

// --- The light, by the time of day -------------------------------------------------------

export type Light = {
  ambient: number
  sun: number
  sunAt: Point
  sunColour: string
  sky: string
  dark: boolean
}

const OPEN = 8 * 60
const CLOSE = 17 * 60

/**
 * The office's light at a time of day ("HH:MM"): the sun crosses from the east (08:00)
 * to the west (17:00), brightest at midday and warmer at either end; after hours the
 * office is dark, with only the night lights on.
 */
export function daylight(time: string | null, afterHours: boolean): Light {
  if (afterHours)
    return {
      ambient: 0.28,
      sun: 0.25,
      sunAt: [-6, 12, 6],
      sunColour: '#93c5fd',
      sky: '#1e293b',
      dark: true,
    }
  const [h, m] = (time ?? '12:00').split(':').map(Number)
  const f = Math.min(1, Math.max(0, (h * 60 + m - OPEN) / (CLOSE - OPEN)))
  const high = Math.sin(Math.PI * f) // 0 at the day's ends, 1 at midday
  return {
    ambient: 0.55 + 0.2 * high,
    sun: 0.9 + 0.7 * high,
    sunAt: [14 * Math.cos(Math.PI * f), 5 + 9 * high, 8],
    sunColour: high > 0.6 ? '#ffffff' : f < 0.5 ? '#fff1d6' : '#ffd8a8',
    sky: high > 0.6 ? '#ffffff' : f < 0.5 ? '#fffaf0' : '#fff4e6',
    dark: false,
  }
}

// --- The busiest case, for measuring the budget ------------------------------------------

/**
 * A floor crowded with ``count`` staff for the budget's busiest case (dev only): all at
 * their desks in even phases, all gathered in the floor's first meeting room (or any
 * room without desks) in odd ones, so every change of phase sets everyone walking.
 */
export function crowded(data: FloorData, count: number, phase: number): FloorData {
  const deskRoom = data.rooms.find((r) => r.desks > 0)
  const away = data.rooms.find((r) => r.kind === 'MEETING') ?? data.rooms.find((r) => r.desks === 0)
  if (!deskRoom) return data
  const out = phase % 2 === 1 && away
  return {
    ...data,
    rooms: data.rooms.map((r) => (r === deskRoom ? { ...r, desks: Math.max(r.desks, count) } : r)),
    after_hours: false,
    staff: Array.from({ length: count }, (_, i) => ({
      number: `C${String(i + 1).padStart(3, '0')}`,
      name: `Crowd ${i + 1}`,
      job_title: 'Data Officer',
      desk: deskRoom.code,
      room: out ? away.code : deskRoom.code,
      place: out ? 'MEETING_ROOM' : 'DESK',
      activity: out ? 'DATA_QUALITY_REVIEW' : 'WORKING',
      doing: out ? 'in the Data Quality Review' : 'working on an item',
      item: null,
      morale: 0.7,
    })),
  }
}
