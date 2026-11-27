/**
 * The office's floors (P4.1, from the P3.2 trial), worked out from the game's state alone.
 *
 * Pure: the 3D page only draws what this returns, so what each floor shows is tested
 * here without WebGL. The server says which rooms a floor has and what is in them; the
 * plans below say where each room stands. Positions are in metres, centred on the
 * floor, with x to the right and z towards the viewer at the first quarter turn.
 */

/** Where a person is, from the game's state (P4.2, A-091). */
export type Place = 'DESK' | 'MEETING_ROOM' | 'BOARDROOM' | 'CAFETERIA' | 'OUT'
export type Activity =
  'WORKING' | 'FREE' | 'BREAK' | 'DATA_QUALITY_REVIEW' | 'BOARD_REVIEW' | 'TRAINING' | 'AFTER_HOURS'
export type RoomKind = 'DEPARTMENT' | 'FACILITY' | 'MEETING' | 'SERVERS' | 'OFFICE'
export type PlanCode = 'GROUND' | 'FIRST' | 'SECOND' | 'SMALL' | 'STANDARD'

export type BuildingData = {
  name: string
  no_office: boolean
  floors: {
    code: string
    name: string
    level: number
    plan: PlanCode
    rooms: { code: string; name: string; kind: RoomKind }[]
  }[]
}

export type FloorData = {
  code: string
  name: string
  level: number
  plan: PlanCode
  rooms: {
    code: string
    name: string
    kind: RoomKind
    screen: string
    summary: string
    desks: number
  }[]
  /** Those with a desk on this floor (`desk`), and those in one of its rooms now (`room`). */
  staff: {
    number: string
    name: string
    job_title: string
    desk: string | null
    room: string | null
    place: Place
    activity: Activity
    doing: string
    item: number | null
    morale: number
  }[]
  after_hours?: boolean
  queue?: { open: number; in_progress: number; by_type: Record<string, number> }
  systems?: {
    installed: boolean
    down: boolean
    detail: string
    files_waiting: number
    capacity: string
  }
}

type Point = [number, number, number]
/** A room on the plan: its corner and size, in metres from the plan's back left corner. */
type Rect = { x: number; z: number; w: number; d: number }
type Plan = { size: [number, number]; rooms: Record<string, Rect> }

/**
 * Where each room stands (A-090). The established building is 24 by 16 metres a floor;
 * the serviced office 14 by 10; the Ridge office floor 30 by 18, for its 45 desks.
 */
export const PLANS: Record<PlanCode, Plan> = {
  GROUND: {
    size: [24, 16],
    rooms: {
      SUPPORT: { x: 0, z: 0, w: 6, d: 10 },
      SALES: { x: 6, z: 0, w: 6, d: 10 },
      FINANCE: { x: 12, z: 0, w: 6, d: 10 },
      HR: { x: 18, z: 0, w: 6, d: 10 },
      RECEPTION: { x: 0, z: 10, w: 8, d: 6 },
      WAITING: { x: 8, z: 10, w: 6, d: 6 },
      CAFETERIA: { x: 14, z: 10, w: 10, d: 6 },
    },
  },
  FIRST: {
    size: [24, 16],
    rooms: {
      DATA_OPERATIONS: { x: 0, z: 0, w: 12, d: 16 },
      DATA_ANALYTICS: { x: 12, z: 0, w: 6, d: 6 },
      PRODUCT: { x: 18, z: 0, w: 6, d: 6 },
      IT: { x: 12, z: 6, w: 12, d: 5 },
      SERVER_ROOM: { x: 12, z: 11, w: 5, d: 5 },
      TECH_MEETING: { x: 17, z: 11, w: 7, d: 5 },
    },
  },
  SECOND: {
    size: [24, 16],
    rooms: {
      CEO_OFFICE: { x: 0, z: 0, w: 8, d: 8 },
      BOARDROOM: { x: 8, z: 0, w: 10, d: 8 },
      EXEC_MEETING: { x: 18, z: 0, w: 6, d: 8 },
      EXECUTIVE: { x: 0, z: 8, w: 12, d: 8 },
      COMPLIANCE: { x: 12, z: 8, w: 12, d: 8 },
    },
  },
  SMALL: {
    size: [14, 10],
    rooms: {
      OPEN_PLAN: { x: 0, z: 0, w: 10, d: 10 },
      MEETING: { x: 10, z: 0, w: 4, d: 5 },
      SERVER_ROOM: { x: 10, z: 5, w: 4, d: 2.5 },
      KITCHEN: { x: 10, z: 7.5, w: 4, d: 2.5 },
    },
  },
  STANDARD: {
    size: [30, 18],
    rooms: {
      OPEN_PLAN: { x: 0, z: 0, w: 21, d: 13 },
      MEETING: { x: 21, z: 0, w: 9, d: 6 },
      CEO_OFFICE: { x: 21, z: 6, w: 9, d: 6 },
      SERVER_ROOM: { x: 21, z: 12, w: 9, d: 6 },
      RECEPTION: { x: 0, z: 13, w: 9, d: 5 },
      KITCHEN: { x: 9, z: 13, w: 6, d: 5 },
    },
  },
}

/** Low-poly palette: flat colours, the brand teal for people at work. */
export const COLOURS = {
  floor: '#e2e8f0',
  wall: '#cbd5e1',
  desk: '#a16207',
  deskTop: '#ca8a04',
  paper: '#f8fafc',
  rack: '#334155',
  rackOk: '#22c55e',
  rackDown: '#ef4444',
  rackOff: '#475569',
  glass: '#bae6fd',
  table: '#78716c',
  working: '#0f766e',
  idle: '#64748b',
  meeting: '#b45309',
  break: '#7c3aed',
  skin: '#8d5524',
  seat: '#475569',
  screen: '#1e293b',
} as const

/** Each kind of room has its own floor tint, so the plan reads at a glance. */
export const ROOM_TINT: Record<RoomKind, string> = {
  DEPARTMENT: '#e2e8f0',
  FACILITY: '#f1f5f9',
  MEETING: '#e0f2fe',
  SERVERS: '#cbd5e1',
  OFFICE: '#fef3c7',
}

const DESK_SPACING_X = 2.2
const DESK_SPACING_Z = 2.4
/** Most sheets drawn on one desk: beyond it the pile stops growing. */
export const MAX_PILE = 12

/** A person's colour: at work, waiting, in a meeting or on a break. */
function colourOf(activity: Activity): string {
  if (activity === 'WORKING') return COLOURS.working
  if (activity === 'DATA_QUALITY_REVIEW' || activity === 'BOARD_REVIEW') return COLOURS.meeting
  if (activity === 'BREAK') return COLOURS.break
  return COLOURS.idle
}

export type Desk = {
  key: string
  room: string
  position: Point
  person: {
    number: string
    name: string
    jobTitle: string
    activity: Activity
    seated: boolean
    colour: string
  } | null
  /** Sheets of paper on the desk: the open queue, shared across the desks in use. */
  pile: number
  label: string
  to: string
}

/** Furniture that stands for what a room is: clicking it opens the room's screen. */
export type Fixture = {
  key: string
  room: string
  kind: 'workstation' | 'table' | 'counter' | 'sofa' | 'bigdesk' | 'rack'
  position: Point
  label: string
  to: string
}

/** Someone standing in a room that is not their desk's: a meeting, the boardroom, a break. */
export type Visitor = {
  key: string
  room: string
  position: Point
  colour: string
  label: string
  to: string
}

/** One line per person on the floor, for the text list: wherever they are. */
export type Listed = { key: string; label: string; to: string }

export type LaidRoom = {
  code: string
  name: string
  kind: RoomKind
  /** Number shown in the keyboard help: press it to zoom to the room. */
  index: number
  centre: Point
  size: [number, number]
  tint: string
  summary: string
  label: string
  to: string
}

export type Floor = {
  code: string
  name: string
  size: [number, number]
  rooms: LaidRoom[]
  desks: Desk[]
  visitors: Visitor[]
  people: Listed[]
  fixtures: Fixture[]
  /** The server room's lights: off before IT is set up, red while the systems are down. */
  lights: 'ok' | 'down' | 'off'
  summary: string
}

/** Positions for ``count`` desks in rows inside a room, front to back, with a margin. */
function deskGrid(rect: Rect, count: number): [number, number][] {
  const cols = Math.max(1, Math.floor((rect.w - 0.8) / DESK_SPACING_X))
  const rows = Math.max(1, Math.ceil(count / cols))
  // Squeeze the rows together if the room is too shallow for them.
  const dz = Math.min(DESK_SPACING_Z, (rect.d - 1.6) / rows)
  const used = Math.min(cols, count)
  return Array.from({ length: count }, (_, i) => {
    const row = Math.floor(i / cols)
    const col = i % cols
    return [
      rect.x + rect.w / 2 + (col - (used - 1) / 2) * DESK_SPACING_X,
      rect.z + 1.0 + row * dz + dz / 2 - 0.4,
    ]
  })
}

/** What stands in a room that has no desks of its own, by its kind. */
const FURNITURE: Record<RoomKind, Fixture['kind'][]> = {
  DEPARTMENT: ['workstation', 'workstation'],
  FACILITY: ['table'],
  MEETING: ['table'],
  SERVERS: ['rack', 'rack'],
  OFFICE: ['bigdesk'],
}
const FACILITY_FURNITURE: Record<string, Fixture['kind'][]> = {
  RECEPTION: ['counter'],
  WAITING: ['sofa', 'sofa'],
  CAFETERIA: ['table', 'table', 'table'],
  KITCHEN: ['table'],
}

export function layOut(data: FloorData, gameId: number): Floor {
  const plan = PLANS[data.plan]
  const [width, depth] = plan.size
  const centred = (x: number, z: number): Point => [x - width / 2, 0, z - depth / 2]
  const screen = (s: string) => `/games/${gameId}/${s}`

  const rooms: LaidRoom[] = data.rooms
    .filter((r) => plan.rooms[r.code])
    .map((r, i) => {
      const rect = plan.rooms[r.code]
      return {
        code: r.code,
        name: r.name,
        kind: r.kind,
        index: i + 1,
        centre: centred(rect.x + rect.w / 2, rect.z + rect.d / 2),
        size: [rect.w, rect.d],
        tint: ROOM_TINT[r.kind],
        summary: r.summary,
        label: `${r.name}: ${r.summary}`,
        to: screen(r.screen),
      }
    })

  const seated = (s: FloorData['staff'][number]) => s.desk !== null && s.place === 'DESK'
  const labelOf = (s: FloorData['staff'][number]) => `${s.name}, ${s.job_title}: ${s.doing}`
  const toOf = (s: FloorData['staff'][number]) =>
    s.item ? screen(`queue/${s.item}`) : screen('staff')
  // The queue is shared across the desks in use, as in the trial.
  const inUse = data.staff.filter(seated).length
  const perDesk = inUse && data.queue ? Math.ceil(data.queue.open / inUse) : 0

  const desks: Desk[] = []
  const fixtures: Fixture[] = []
  for (const r of data.rooms) {
    const rect = plan.rooms[r.code]
    if (!rect) continue
    if (r.desks > 0) {
      const here = data.staff.filter((s) => s.desk === r.code)
      deskGrid(rect, Math.max(r.desks, here.length)).forEach(([x, z], i) => {
        const position = centred(x, z)
        const s = here[i]
        if (!s) {
          desks.push({
            key: `${r.code}-empty-${i}`,
            room: r.code,
            position,
            person: null,
            pile: 0,
            label: `An empty desk in ${r.name}: room to hire (Staff)`,
            to: screen('staff'),
          })
          return
        }
        const sitting = seated(s)
        desks.push({
          key: s.number,
          room: r.code,
          position,
          person: {
            number: s.number,
            name: s.name,
            jobTitle: s.job_title,
            activity: s.activity,
            seated: sitting,
            colour: colourOf(s.activity),
          },
          pile: sitting ? Math.min(MAX_PILE, perDesk) : 0,
          label: labelOf(s),
          to: toOf(s),
        })
      })
      continue
    }
    const kinds = FACILITY_FURNITURE[r.code] ?? FURNITURE[r.kind]
    const spread = rect.w / (kinds.length + 1)
    kinds.forEach((kind, i) => {
      fixtures.push({
        key: `${r.code}-${i}`,
        room: r.code,
        kind,
        position: centred(rect.x + spread * (i + 1), rect.z + rect.d / 2),
        label: `${r.name}: ${r.summary}`,
        to: screen(r.screen),
      })
    })
  }

  // Those gathered in a room away from their desk stand round its middle.
  const visitors: Visitor[] = []
  for (const r of rooms) {
    const here = data.staff.filter((s) => s.room === r.code && s.place !== 'DESK')
    const radius = Math.min(r.size[0], r.size[1]) / 2 - 0.7
    here.forEach((s, i) => {
      const angle = (2 * Math.PI * i) / here.length
      visitors.push({
        key: `${s.number}-in-${r.code}`,
        room: r.code,
        position: [
          r.centre[0] + Math.cos(angle) * radius,
          0,
          r.centre[2] + Math.sin(angle) * radius,
        ],
        colour: colourOf(s.activity),
        label: labelOf(s),
        to: toOf(s),
      })
    })
  }
  const people: Listed[] = data.staff.map((s) => ({
    key: s.number,
    label: labelOf(s),
    to: toOf(s),
  }))

  const lights = !data.systems
    ? 'ok'
    : !data.systems.installed
      ? 'off'
      : data.systems.down
        ? 'down'
        : 'ok'
  const based = data.staff.filter((s) => s.desk !== null)
  const working = based.filter((s) => s.activity === 'WORKING').length
  const free = based.filter((s) => s.activity === 'FREE').length
  const parts = [`${data.name}: ${rooms.length} rooms.`]
  if (data.after_hours) parts.push('After hours: everyone has gone home.')
  else if (based.length)
    parts.push(
      `${based.length} staff work here: ${working} working, ${free} free, ${based.length - working - free} away from their desks.`,
    )
  if (data.queue) parts.push(`${data.queue.open} item(s) waiting in the queue.`)
  if (data.systems)
    parts.push(
      !data.systems.installed
        ? 'No systems yet.'
        : data.systems.down
          ? 'The systems are down.'
          : 'The systems are up.',
    )
  return {
    code: data.code,
    name: data.name,
    size: plan.size,
    rooms,
    desks,
    visitors,
    people,
    fixtures,
    lights,
    summary: parts.join(' '),
  }
}

// --- The view: which way it faces, and what it frames -----------------------------------

/** Quarter turns: 0 looks from the front right, 1 from the back right, and so on. */
export type Turn = 0 | 1 | 2 | 3

export function turned(turn: Turn, by: 1 | -1): Turn {
  return ((((turn + by) % 4) + 4) % 4) as Turn
}

/** The camera's bearing for a quarter turn: 0 looks from the front right. */
export function azimuthOf(turn: Turn): number {
  return Math.PI / 4 + (turn * Math.PI) / 2
}

/** Where the camera stands, looking at ``target`` from a bearing, at ``distance``. */
export function cameraFrom(azimuth: number, target: Point, distance = 30): Point {
  return [
    target[0] + Math.sin(azimuth) * distance,
    target[1] + distance * 0.85,
    target[2] + Math.cos(azimuth) * distance,
  ]
}

export function cameraAt(turn: Turn, target: Point, distance = 30): Point {
  return cameraFrom(azimuthOf(turn), target, distance)
}

/**
 * The orthographic zoom that fits an area of ``w`` by ``d`` metres into a canvas.
 * From any quarter turn an isometric view of it spans about 0.71 (w + d) across and
 * half that deep, plus the height of what stands on it and a margin around it.
 */
export function fitZoom(w: number, d: number, width: number, height: number): number {
  const across = 0.71 * (w + d) * 1.08 + 4
  const tall = 0.71 * (w + d) * 0.65 + 5
  return Math.min(width / across, height / tall)
}

/** What the view frames: the whole floor, or one room zoomed to. */
export function framing(
  floor: Floor,
  room: string | null,
): { target: Point; size: [number, number] } {
  const found = room ? floor.rooms.find((r) => r.code === room) : undefined
  if (found) return { target: [found.centre[0], 0.5, found.centre[2]], size: found.size }
  return { target: [0, 0.5, 0], size: floor.size }
}

/** The keys the office answers to, as the help line shows them. */
export type Command =
  | { type: 'floor'; by: 1 | -1 }
  | { type: 'turn'; by: 1 | -1 }
  | { type: 'room'; index: number }
  | { type: 'whole' }

export function command(key: string): Command | null {
  if (key === 'PageUp') return { type: 'floor', by: 1 }
  if (key === 'PageDown') return { type: 'floor', by: -1 }
  if (key === 'ArrowLeft' || key === 'q' || key === 'Q') return { type: 'turn', by: -1 }
  if (key === 'ArrowRight' || key === 'e' || key === 'E') return { type: 'turn', by: 1 }
  if (key === 'Escape' || key === '0') return { type: 'whole' }
  if (/^[1-9]$/.test(key)) return { type: 'room', index: Number(key) }
  return null
}
