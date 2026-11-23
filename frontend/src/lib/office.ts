/**
 * The office floor (P3.2, the 3D trial), worked out from the game's state alone.
 *
 * Pure: the 3D page only draws what this returns, so what the floor shows is
 * tested here without WebGL. Positions are in metres on the floor plan, with x to
 * the right and z towards the viewer; the camera looks from the front right.
 */

export type StaffState = 'WORKING' | 'IDLE' | 'AWAY' | 'GONE'

export type OfficeData = {
  staff: {
    number: string
    name: string
    job_title: string
    state: StaffState
    item: number | null
    morale: number
  }[]
  queue: { open: number; in_progress: number; by_type: Record<string, number> }
  systems: { down: boolean; detail: string; files_waiting: number; capacity: string }
}

export type Desk = {
  key: string
  position: [number, number, number]
  person: {
    number: string
    name: string
    jobTitle: string
    state: StaffState
    seated: boolean
    colour: string
  } | null
  /** Sheets of paper on the desk: the open queue, shared across the desks in use. */
  pile: number
  label: string
  to: string
}

export type Floor = {
  desks: Desk[]
  rack: { position: [number, number, number]; down: boolean; label: string; to: string }
  meeting: { position: [number, number, number]; label: string; to: string }
  summary: string
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
  glass: '#bae6fd',
  table: '#78716c',
  working: '#0f766e',
  idle: '#64748b',
  skin: '#8d5524',
} as const

const DESKS_PER_ROW = 4
const DESK_SPACING_X = 2.2
const DESK_SPACING_Z = 2.4
/** At least this many desks, so an empty seat shows room to hire. */
const MIN_DESKS = 6
/** Most sheets drawn on one desk: beyond it the pile stops growing. */
export const MAX_PILE = 12

const STATE_WORDS: Record<StaffState, string> = {
  WORKING: 'working on an item',
  IDLE: 'at their desk, nothing to do',
  AWAY: 'away on a training course',
  GONE: 'has left the bureau',
}

export function layOut(data: OfficeData, gameId: number): Floor {
  const present = data.staff.filter((s) => s.state !== 'GONE')
  const deskCount = Math.max(MIN_DESKS, present.length)
  const inUse = present.filter((s) => s.state !== 'AWAY').length
  const perDesk = inUse ? Math.ceil(data.queue.open / inUse) : 0

  const desks: Desk[] = Array.from({ length: deskCount }, (_, i) => {
    const row = Math.floor(i / DESKS_PER_ROW)
    const col = i % DESKS_PER_ROW
    const position: [number, number, number] = [
      (col - (DESKS_PER_ROW - 1) / 2) * DESK_SPACING_X,
      0,
      row * DESK_SPACING_Z,
    ]
    const s = present[i]
    if (!s) {
      return {
        key: `empty-${i}`,
        position,
        person: null,
        pile: 0,
        label: 'An empty desk: room to hire (Staff)',
        to: `/games/${gameId}/staff`,
      }
    }
    const seated = s.state === 'WORKING' || s.state === 'IDLE'
    return {
      key: s.number,
      position,
      person: {
        number: s.number,
        name: s.name,
        jobTitle: s.job_title,
        state: s.state,
        seated,
        colour: s.state === 'WORKING' ? COLOURS.working : COLOURS.idle,
      },
      pile: seated ? Math.min(MAX_PILE, perDesk) : 0,
      label: `${s.name}, ${s.job_title}: ${STATE_WORDS[s.state]}`,
      to: s.item ? `/games/${gameId}/queue/${s.item}` : `/games/${gameId}/staff`,
    }
  })

  const away = present.filter((s) => s.state === 'AWAY').length
  const working = present.filter((s) => s.state === 'WORKING').length
  return {
    desks,
    rack: {
      position: [5.6, 0, -1.2],
      down: data.systems.down,
      label: data.systems.down
        ? `Systems down: ${data.systems.detail} (IT)`
        : `Systems up; ${data.systems.files_waiting} file(s) waiting to process (IT)`,
      to: `/games/${gameId}/it`,
    },
    meeting: {
      position: [-6.2, 0, 1.2],
      label: 'Meeting room: the monthly Data Quality Reviews',
      to: `/games/${gameId}/reviews`,
    },
    summary:
      `${present.length} staff: ${working} working, ${present.length - working - away} free, ` +
      `${away} away. ${data.queue.open} item(s) waiting in the queue. ` +
      (data.systems.down ? 'The systems are down.' : 'The systems are up.'),
  }
}
