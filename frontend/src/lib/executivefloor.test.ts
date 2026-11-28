/** The executive floor (P4.6): the boardroom, Compliance, the CEO's desk, the notice board. */
import { describe, expect, it } from 'vitest'

import { stage } from './movement'
import { COLOURS, detailsOf, type FloorData, layOut, noticeLines } from './office'

type Staff = FloorData['staff'][number]

function room(
  code: string,
  screen: string,
  desks = 0,
  kind: FloorData['rooms'][number]['kind'] = 'DEPARTMENT',
) {
  return { code, name: code, kind, screen, summary: `About ${code}.`, desks }
}

const CEO: Staff = {
  number: 'CEO',
  name: 'The chief executive (you)',
  job_title: 'Chief executive',
  desk: 'CEO_OFFICE',
  room: 'CEO_OFFICE',
  place: 'DESK',
  activity: 'WORKING',
  doing: 'at their desk: the company at a glance',
  item: null,
  morale: null,
  managed: true,
  screen: 'dashboard',
}

const OFFICER: Staff = {
  ...CEO,
  number: 'COMPLIANCE-1',
  name: 'Compliance team 1',
  job_title: 'Compliance officer',
  desk: 'COMPLIANCE',
  room: 'COMPLIANCE',
  doing: 'following up 2 open finding(s)',
  screen: 'compliance',
}

const IN_REVIEW: Partial<Staff> = {
  room: 'BOARDROOM',
  place: 'BOARDROOM',
  activity: 'BOARD_REVIEW',
  doing: 'at the board review of Q4 2026',
}

function director(n: number): Staff {
  return {
    ...CEO,
    ...IN_REVIEW,
    number: `BOARD-${n}`,
    name: n === 1 ? 'The chair' : `Director ${n - 1}`,
    job_title: n === 1 ? 'Board chair' : 'Non-executive director',
    desk: null,
    managed: undefined,
    visitor: true,
    screen: 'health#board',
  }
}

function second(overrides: Partial<FloorData> = {}): FloorData {
  return {
    code: 'second',
    name: 'Second floor',
    level: 2,
    plan: 'SECOND',
    rooms: [
      room('CEO_OFFICE', 'dashboard', 1, 'OFFICE'),
      room('EXECUTIVE', 'health'),
      room('BOARDROOM', 'health#board', 0, 'MEETING'),
      room('COMPLIANCE', 'compliance', 1),
      room('EXEC_MEETING', 'events', 0, 'MEETING'),
    ],
    staff: [CEO, OFFICER],
    board: {
      in_session: false,
      last: {
        period: '2026-12-31',
        quarter: 'Q4 2026',
        confidence: 72,
        verdict: 'CONFIDENT',
        words: 'confident',
        detail: 'Every part of the bureau is in good health.',
      },
      next_on: '2027-04-01',
    },
    compliance: {
      open: 2,
      findings: [
        {
          number: 1,
          kind: 'ACCESS_REVIEW_DUE',
          words: 'the quarterly access review due',
          due: '2027-01-19',
          escalated: false,
        },
        {
          number: 2,
          kind: 'CONSENT_MISSING',
          words: 'enquiries without consent on file',
          due: '2027-01-25',
          escalated: true,
        },
      ],
      samples: [
        { number: 3, subscriber: 'ATB', state: 'reading the forms: 1 working day(s) left' },
      ],
      today: "ATB's consent forms (check 3)",
    },
    notices: {
      mission: {
        code: 'M3',
        title: 'Is this the same person?',
        objectives: [
          { text: 'Decide 5 match reviews yourself', done: false, progress: '2 of 5' },
          { text: 'Answer the question', done: true, progress: '' },
        ],
      },
      campaign: true,
      targets: ['Revenue: GHS 12,000 of GHS 50,000 to reach'],
      regulator: ['Monthly return for December 2026: due 15 Jan 2027'],
    },
    time: '10:00',
    ...overrides,
  }
}

describe('the executive floor', () => {
  it('fills the boardroom for a board review, the chief executive with the board', () => {
    const review = second({
      staff: [{ ...CEO, ...IN_REVIEW }, OFFICER, ...[1, 2, 3, 4, 5].map(director)],
      board: { ...second().board!, in_session: true },
    })
    const floor = layOut(review, 16)
    const there = floor.figures.filter((f) => f.room === 'BOARDROOM')
    expect(there).toHaveLength(6)
    expect(there.every((f) => f.pose === 'standing' && f.colour === COLOURS.meeting)).toBe(true)
    expect(there.find((f) => f.key === 'BOARD-1')!.to).toBe('/games/16/health#board')
    // The chief executive's desk stays theirs, empty, while they are at the review.
    const desk = floor.desks.find((d) => d.room === 'CEO_OFFICE')!
    expect(desk.person?.seated).toBe(false)
    expect(desk.to).toBe('/games/16/dashboard')
    expect(floor.summary).toContain('5 visitor(s) in the building.')

    // The board walks in from the stairs; the chief executive from their office.
    const before = layOut(second(), 16)
    const actors = stage(
      stage(new Map(), before.figures, before, true),
      floor.figures,
      floor,
      false,
    )
    expect(actors.get('BOARD-1')!.path[0]).toEqual(floor.stairs)
    expect(actors.get('CEO')!.path).toContainEqual(floor.doors.BOARDROOM)
  })

  it('gives the board’s last review when the boardroom is looked at closely', () => {
    const shown = second()
    expect(detailsOf(shown.rooms[2], shown)).toEqual([
      'Last review, Q4 2026: confidence 72, confident',
      'Every part of the bureau is in good health.',
      'Next review: the first working day of April 2027',
    ])
    const none = second({ board: { in_session: false, last: null, next_on: '2027-04-01' } })
    expect(detailsOf(none.rooms[2], none)[0]).toBe('No board review yet')
  })

  it('lays Compliance’s open findings on its desk, so a new one shows', () => {
    const pile = (f: FloorData) => layOut(f, 16).desks.find((d) => d.room === 'COMPLIANCE')!.pile
    expect(pile(second())).toBe(2)
    const more = second({ compliance: { ...second().compliance!, open: 3 } })
    expect(pile(more)).toBe(3)
    expect(pile(second({ compliance: { ...second().compliance!, open: 0 } }))).toBe(0)
    const shown = second()
    expect(detailsOf(shown.rooms[3], shown)).toEqual([
      'Finding 1: the quarterly access review due, to put right by 19 Jan 2027',
      'Finding 2: enquiries without consent on file, to put right by 25 Jan 2027 (reported to the regulator)',
      'Consent sample 3 (ATB): reading the forms: 1 working day(s) left',
      "Today: ATB's consent forms (check 3)",
    ])
  })

  it('puts the mission, the targets and the regulator on the notice board', () => {
    const floor = layOut(second(), 16)
    const board = floor.fixtures.find((f) => f.kind === 'noticeboard')!
    expect(board.room).toBe('EXECUTIVE')
    expect(board.to).toBe('/games/16/missions')
    expect(board.label).toContain('Mission M3: Is this the same person?')
    expect(board.label).toContain('Regulator: Monthly return for December 2026')
    expect(noticeLines(second().notices!)).toEqual([
      'Mission M3: Is this the same person?',
      '  To do: Decide 5 match reviews yourself (2 of 5)',
      '  Done: Answer the question',
      'Target: Revenue: GHS 12,000 of GHS 50,000 to reach',
      'Regulator: Monthly return for December 2026: due 15 Jan 2027',
    ])
    const quiet = { mission: null, campaign: false, targets: [], regulator: [] }
    expect(noticeLines(quiet)).toEqual([
      'No campaign in this game.',
      "Targets: no budget set for this month (Finance's budget screen)",
      'Regulator: nothing open; the bureau is in good standing',
    ])
  })

  it('opens a 2D screen from every object on the floor', () => {
    const floor = layOut(second(), 16)
    expect(Object.fromEntries(floor.rooms.map((r) => [r.code, r.to]))).toEqual({
      CEO_OFFICE: '/games/16/dashboard',
      EXECUTIVE: '/games/16/health',
      BOARDROOM: '/games/16/health#board',
      COMPLIANCE: '/games/16/compliance',
      EXEC_MEETING: '/games/16/events',
    })
    expect(Object.fromEntries(floor.desks.map((d) => [d.room, d.to]))).toEqual({
      CEO_OFFICE: '/games/16/dashboard',
      COMPLIANCE: '/games/16/compliance',
    })
    expect(Object.fromEntries(floor.fixtures.map((f) => [f.key, [f.kind, f.to]]))).toEqual({
      'EXECUTIVE-0': ['noticeboard', '/games/16/missions'],
      'EXECUTIVE-1': ['table', '/games/16/health'],
      'BOARDROOM-0': ['table', '/games/16/health#board'],
      'EXEC_MEETING-0': ['table', '/games/16/events'],
    })
  })
})
