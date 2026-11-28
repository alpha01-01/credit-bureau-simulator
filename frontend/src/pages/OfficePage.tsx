/**
 * The office in 3D (P4.1: the building and its floors, from the P3.2 trial). Loaded on
 * its own, so the rest of the game never downloads three.js. It draws only what
 * ``layOut`` gives for the floor in view, refreshed every two seconds. The player moves
 * between floors, turns the view a quarter at a time and zooms to a room, by mouse or
 * keyboard; clicking a desk, a person or a piece of furniture opens its 2D screen.
 *
 * P4.3: people are figures of a few parts, seated at their desks or standing, and walk
 * between places when the game moves them (``lib/movement``); the light follows the
 * clock, and the office goes dark after hours.
 *
 * P4.4: the whole first floor. The server room's racks follow the IT state and IT walks
 * to them during an outage; Analytics' screens show the scorecards, Product
 * Development's desks the products' progress; a room looked at closely lists its figures.
 *
 * P4.5: the ground floor. Visitors (blue) come in for a dispute or a meeting with Sales;
 * Support's tickets pile up on its desks; Finance's desks show the month's close; the
 * cafeteria, looked at closely, gives the staff's welfare.
 *
 * P4.6: the executive floor. The board fills the boardroom for a review; the chief
 * executive works at their desk; Compliance's open findings lie on its desk; the notice
 * board gives the current mission, the month's targets and the regulator's open actions.
 */
import { Canvas, type ThreeEvent, useFrame, useThree } from '@react-three/fiber'
import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import {
  BoxGeometry,
  CylinderGeometry,
  type Group,
  IcosahedronGeometry,
  type Mesh,
  MeshStandardMaterial,
} from 'three'

import { useBuilding, useOfficeFloor } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Failed, Loading, Page } from '../components/ui'
import {
  azimuthOf,
  cameraFrom,
  COLOURS,
  command,
  type Desk,
  type Fixture,
  type Floor,
  fitZoom,
  framing,
  type LaidRoom,
  layOut,
  type Turn,
  turned,
} from '../lib/office'
import { type Actor, crowded, daylight, poseOf, stage, step } from '../lib/movement'

type Point = [number, number, number]
type Pick = { label: string; to: string }
type Hover = (label: string | null) => void
type Go = (to: string) => void

const BUTTON =
  'rounded border border-slate-300 px-2.5 py-1 text-sm hover:bg-slate-50 disabled:opacity-40'
const WALL_HEIGHT = 0.6

/** Pointer handlers for something that opens a screen when clicked. */
function pickable(pick: Pick, onHover: Hover, go: Go) {
  return {
    onPointerOver: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation()
      document.body.style.cursor = 'pointer'
      onHover(pick.label)
    },
    onPointerOut: () => {
      document.body.style.cursor = ''
      onHover(null)
    },
    onClick: (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation()
      document.body.style.cursor = ''
      go(pick.to)
    },
  }
}

function Box({
  size,
  at,
  colour,
  ...rest
}: {
  size: Point
  at: Point
  colour: string
  [k: string]: unknown
}) {
  return (
    <mesh position={at} {...rest}>
      <boxGeometry args={size} />
      <meshStandardMaterial color={colour} flatShading />
    </mesh>
  )
}

// One set of shapes for every figure, shared: a figure is six meshes and no new geometry.
const LEG = new BoxGeometry(0.13, 0.5, 0.13).translate(0, -0.25, 0)
const ARM = new BoxGeometry(0.09, 0.45, 0.09).translate(0, -0.22, 0)
const TORSO = new CylinderGeometry(0.17, 0.2, 0.55, 6)
const HEAD = new IcosahedronGeometry(0.15, 0)
const materials = new Map<string, MeshStandardMaterial>()
function material(colour: string): MeshStandardMaterial {
  let m = materials.get(colour)
  if (!m) {
    m = new MeshStandardMaterial({ color: colour, flatShading: true })
    materials.set(colour, m)
  }
  return m
}
const TROUSERS = '#334155'
const SEATED_DROP = -0.05 // hips from standing height (0.5) to the chair's seat (0.45)

/** The moving parts of one figure, set every frame from its actor. */
type Parts = { root: Group | null; legs: (Group | null)[]; arms: (Group | null)[] }

function applyPose(p: Parts, a: Actor, time: number) {
  if (!p.root) return
  const pose = poseOf(a)
  p.root.position.set(a.at[0], pose === 'seated' ? SEATED_DROP : 0, a.at[2])
  p.root.rotation.y = a.heading
  const swing = pose === 'walking' ? Math.sin(time * 9) * 0.55 : 0
  p.legs.forEach((leg, i) => {
    if (leg) leg.rotation.x = pose === 'seated' ? -Math.PI / 2 : i === 0 ? swing : -swing
  })
  p.arms.forEach((arm, i) => {
    if (arm) arm.rotation.x = pose === 'seated' ? -1.2 : (i === 0 ? -swing : swing) * 0.8
  })
}

/** A person: legs, body, arms and head, low-poly (brief, finding 2). */
function Body({
  actor,
  onParts,
  hover,
  go,
}: {
  actor: Actor
  onParts: (key: string, parts: Parts | null) => void
  hover: Hover
  go: Go
}) {
  const parts = useRef<Parts>({ root: null, legs: [null, null], arms: [null, null] })
  const key = actor.key
  useEffect(() => {
    onParts(key, parts.current)
    return () => onParts(key, null)
  }, [key, onParts])
  const shirt = material(actor.figure.colour)
  return (
    <group
      ref={(g) => {
        parts.current.root = g
      }}
      position={actor.at}
      {...pickable(actor.figure, hover, go)}
    >
      {[-0.09, 0.09].map((x, i) => (
        <group
          key={x}
          position={[x, 0.5, 0]}
          ref={(g) => {
            parts.current.legs[i] = g
          }}
        >
          <mesh geometry={LEG} material={material(TROUSERS)} />
        </group>
      ))}
      <mesh geometry={TORSO} material={shirt} position={[0, 0.78, 0]} />
      {[-0.25, 0.25].map((x, i) => (
        <group
          key={x}
          position={[x, 1.0, 0]}
          ref={(g) => {
            parts.current.arms[i] = g
          }}
        >
          <mesh geometry={ARM} material={shirt} />
        </group>
      ))}
      <mesh geometry={HEAD} material={material(COLOURS.skin)} position={[0, 1.22, 0]} />
    </group>
  )
}

/**
 * Everyone on the floor. Each refresh stages the walks from where people are drawn to
 * where the game now has them; each frame moves them along and sets their pose.
 */
function Cast({ floor, hover, go }: { floor: Floor; hover: Hover; go: Go }) {
  const actors = useRef(new Map<string, Actor>())
  const parts = useRef(new Map<string, Parts>())
  const floorShown = useRef<string | null>(null)
  const [shown, setShown] = useState<Actor[]>([])
  useEffect(() => {
    const fresh = floorShown.current !== floor.code
    floorShown.current = floor.code
    actors.current = stage(actors.current, floor.figures, floor, fresh)
    setShown([...actors.current.values()])
  }, [floor])
  useFrame(({ clock }, delta) => {
    const seconds = Math.min(delta, 0.1)
    let gone = false
    for (const [key, a] of actors.current) {
      if (!step(a, seconds)) {
        actors.current.delete(key)
        gone = true
        continue
      }
      const p = parts.current.get(key)
      if (p) applyPose(p, a, clock.elapsedTime)
    }
    if (gone) setShown([...actors.current.values()])
  })
  const onParts = useCallback((key: string, p: Parts | null) => {
    if (p) parts.current.set(key, p)
    else parts.current.delete(key)
  }, [])
  return (
    <>
      {shown.map((a) => (
        <Body key={a.key} actor={a} onParts={onParts} hover={hover} go={go} />
      ))}
    </>
  )
}

/** The stairs everyone comes and goes by, at the front of the floor. */
function Stairs({ at }: { at: Point }) {
  return (
    <group position={at}>
      {[0, 1, 2].map((i) => (
        <Box
          key={i}
          size={[1.6, 0.12, 0.35]}
          at={[0, -0.1 - i * 0.12, 0.1 + i * 0.3]}
          colour={COLOURS.seat}
        />
      ))}
    </group>
  )
}

/** A workstation: desk, screen and chair; the screen lit by what is on it (P4.4). */
function Workstation({ screen = COLOURS.screen }: { screen?: string }) {
  const lit = screen !== COLOURS.screen
  return (
    <>
      <Box size={[1.4, 0.08, 0.8]} at={[0, 0.75, 0]} colour={COLOURS.deskTop} />
      <Box size={[1.3, 0.7, 0.1]} at={[0, 0.36, -0.3]} colour={COLOURS.desk} />
      <mesh position={[0, 1.0, -0.2]}>
        <boxGeometry args={[0.5, 0.35, 0.05]} />
        <meshStandardMaterial
          color={screen}
          emissive={screen}
          emissiveIntensity={lit ? 0.6 : 0}
          flatShading
        />
      </mesh>
      <Box size={[0.5, 0.45, 0.5]} at={[0, 0.23, 0.75]} colour={COLOURS.seat} />
    </>
  )
}

function DeskGroup({ desk, hover, go }: { desk: Desk; hover: Hover; go: Go }) {
  return (
    <group position={desk.position} {...pickable(desk, hover, go)}>
      <Workstation screen={desk.screen} />
      {desk.progress !== null && (
        // A product's progress: a bar along the desk's front, filled as far as it has got.
        <>
          <Box size={[1.2, 0.06, 0.06]} at={[0, 0.82, 0.37]} colour={COLOURS.wall} />
          <Box
            size={[Math.max(0.02, 1.2 * desk.progress), 0.08, 0.08]}
            at={[-0.6 + (1.2 * desk.progress) / 2, 0.82, 0.38]}
            colour={COLOURS.progress}
          />
        </>
      )}
      {desk.pile > 0 && (
        // One box for the pile, its height the sheets on it: a mesh a desk, however busy.
        <Box
          size={[0.3, desk.pile * 0.025, 0.4]}
          at={[0.45, 0.79 + (desk.pile * 0.025) / 2, 0.1]}
          colour={COLOURS.paper}
        />
      )}
    </group>
  )
}

/** A server rack: green lights, red ones blinking while the systems are down, or dark. */
function Rack({ lights }: { lights: Floor['lights'] }) {
  const leds = useRef<Mesh[]>([])
  useFrame(({ clock }) => {
    const on = lights === 'ok' || (lights === 'down' && Math.floor(clock.elapsedTime * 3) % 2 === 0)
    for (const led of leds.current) {
      const material = led.material as MeshStandardMaterial
      material.emissiveIntensity = on ? 1.2 : 0.1
    }
  })
  const colour =
    lights === 'down' ? COLOURS.rackDown : lights === 'off' ? COLOURS.rackOff : COLOURS.rackOk
  return (
    <>
      <Box size={[0.9, 2.2, 0.8]} at={[0, 1.1, 0]} colour={COLOURS.rack} />
      {[0.5, 0.9, 1.3, 1.7].map((y, i) => (
        <mesh
          key={y}
          position={[0.3, y, 0.41]}
          ref={(m) => {
            if (m) leds.current[i] = m
          }}
        >
          <boxGeometry args={[0.12, 0.06, 0.02]} />
          <meshStandardMaterial color={colour} emissive={colour} emissiveIntensity={1.2} />
        </mesh>
      ))}
    </>
  )
}

function Table() {
  return (
    <>
      <Box size={[2.2, 0.08, 1.2]} at={[0, 0.75, 0]} colour={COLOURS.table} />
      <Box size={[0.3, 0.7, 0.3]} at={[0, 0.36, 0]} colour={COLOURS.table} />
      {[-0.7, 0, 0.7].flatMap((x) => [
        <Box key={`a${x}`} size={[0.45, 0.45, 0.45]} at={[x, 0.23, -0.95]} colour={COLOURS.seat} />,
        <Box key={`b${x}`} size={[0.45, 0.45, 0.45]} at={[x, 0.23, 0.95]} colour={COLOURS.seat} />,
      ])}
    </>
  )
}

function FixtureMesh({
  fixture,
  lights,
  hover,
  go,
}: {
  fixture: Fixture
  lights: Floor['lights']
  hover: Hover
  go: Go
}) {
  return (
    <group position={fixture.position} {...pickable(fixture, hover, go)}>
      {fixture.kind === 'workstation' && <Workstation />}
      {fixture.kind === 'table' && <Table />}
      {fixture.kind === 'rack' && <Rack lights={lights} />}
      {fixture.kind === 'counter' && (
        <Box size={[2.6, 1.1, 0.7]} at={[0, 0.55, 0]} colour={COLOURS.deskTop} />
      )}
      {fixture.kind === 'sofa' && (
        <>
          <Box size={[1.8, 0.45, 0.8]} at={[0, 0.23, 0]} colour="#0f766e" />
          <Box size={[1.8, 0.5, 0.2]} at={[0, 0.65, -0.3]} colour="#115e59" />
        </>
      )}
      {fixture.kind === 'bigdesk' && (
        <>
          <Box size={[2.4, 0.1, 1.1]} at={[0, 0.78, 0]} colour={COLOURS.desk} />
          <Box size={[2.2, 0.72, 0.1]} at={[0, 0.37, -0.4]} colour={COLOURS.desk} />
          <Box size={[0.6, 0.9, 0.6]} at={[0, 0.45, 0.9]} colour={COLOURS.seat} />
        </>
      )}
      {fixture.kind === 'noticeboard' && (
        <>
          {/* A cork board on two legs, with notices pinned to it (P4.6). */}
          <Box size={[0.08, 1.7, 0.08]} at={[-0.9, 0.85, 0]} colour={COLOURS.desk} />
          <Box size={[0.08, 1.7, 0.08]} at={[0.9, 0.85, 0]} colour={COLOURS.desk} />
          <Box size={[2.0, 1.1, 0.08]} at={[0, 1.35, 0]} colour={COLOURS.cork} />
          {NOTICES.map(([x, y], i) => (
            <Box key={i} size={[0.34, 0.26, 0.02]} at={[x, y, 0.05]} colour={COLOURS.paper} />
          ))}
        </>
      )}
    </group>
  )
}

/** Where the notices are pinned on the notice board. */
const NOTICES: [number, number][] = [
  [-0.6, 1.6],
  [-0.15, 1.55],
  [0.35, 1.62],
  [-0.45, 1.15],
  [0.1, 1.1],
  [0.6, 1.2],
]

/** A room's floor and low partition walls; clicking the floor looks closer at the room. */
function RoomTile({
  room,
  hover,
  onZoom,
}: {
  room: LaidRoom
  hover: Hover
  onZoom: (code: string) => void
}) {
  const [w, d] = room.size
  const walls: [Point, Point][] = [
    [
      [w, WALL_HEIGHT, 0.1],
      [0, WALL_HEIGHT / 2, -d / 2],
    ],
    [
      [w, WALL_HEIGHT, 0.1],
      [0, WALL_HEIGHT / 2, d / 2],
    ],
    [
      [0.1, WALL_HEIGHT, d],
      [-w / 2, WALL_HEIGHT / 2, 0],
    ],
    [
      [0.1, WALL_HEIGHT, d],
      [w / 2, WALL_HEIGHT / 2, 0],
    ],
  ]
  return (
    <group position={room.centre}>
      <Box
        size={[w - 0.1, 0.1, d - 0.1]}
        at={[0, -0.05, 0]}
        colour={room.tint}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation()
          hover(`${room.label} Click to look closer.`)
        }}
        onPointerOut={() => hover(null)}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          onZoom(room.code)
        }}
      />
      {walls.map(([size, at], i) => (
        <Box key={i} size={size} at={at} colour={COLOURS.wall} />
      ))}
    </group>
  )
}

/** Moves the camera smoothly to the bearing and framing asked for. */
function CameraRig({ target, area, turn }: { target: Point; area: [number, number]; turn: Turn }) {
  const { camera, size } = useThree()
  const now = useRef<{ target: Point; zoom: number; azimuth: number } | null>(null)
  useFrame((_, delta) => {
    const zoom = fitZoom(area[0], area[1], size.width, size.height)
    const azimuth = azimuthOf(turn)
    if (now.current === null) now.current = { target: [...target], zoom, azimuth }
    const s = now.current
    const k = 1 - Math.exp(-Math.min(delta, 0.1) * 8)
    for (const i of [0, 1, 2] as const) s.target[i] += (target[i] - s.target[i]) * k
    s.zoom += (zoom - s.zoom) * k
    const turnBy = Math.atan2(Math.sin(azimuth - s.azimuth), Math.cos(azimuth - s.azimuth))
    s.azimuth += turnBy * k
    camera.position.set(...cameraFrom(s.azimuth, s.target))
    camera.lookAt(...s.target)
    // A three.js camera is a mutable object: React Three Fiber expects it to be set like this.
    // oxlint-disable-next-line react/immutability
    camera.zoom = s.zoom
    camera.updateProjectionMatrix()
  })
  return null
}

/** Frames drawn per second, for the performance budget. */
function FrameMeter({ onRate }: { onRate: (fps: number) => void }) {
  const frames = useRef({ count: 0, since: 0 })
  useFrame(({ clock }) => {
    const f = frames.current
    f.count += 1
    if (clock.elapsedTime - f.since >= 1) {
      onRate(Math.round(f.count / (clock.elapsedTime - f.since)))
      f.count = 0
      f.since = clock.elapsedTime
    }
  })
  return null
}

function Scene({
  floor,
  room,
  turn,
  hover,
  go,
  onZoom,
  onRate,
}: {
  floor: Floor
  room: string | null
  turn: Turn
  hover: Hover
  go: Go
  onZoom: (code: string) => void
  onRate: (fps: number) => void
}) {
  const view = framing(floor, room)
  const light = daylight(floor.time, floor.afterHours)
  return (
    <>
      <color attach="background" args={[light.sky]} />
      <ambientLight intensity={light.ambient} />
      <directionalLight position={light.sunAt} intensity={light.sun} color={light.sunColour} />
      <Box
        size={[floor.size[0] + 1, 0.1, floor.size[1] + 1]}
        at={[0, -0.16, 0]}
        colour={COLOURS.wall}
      />
      {floor.rooms.map((r) => (
        <RoomTile key={r.code} room={r} hover={hover} onZoom={onZoom} />
      ))}
      {floor.desks.map((d) => (
        <DeskGroup key={d.key} desk={d} hover={hover} go={go} />
      ))}
      <Cast floor={floor} hover={hover} go={go} />
      <Stairs at={floor.stairs} />
      {floor.fixtures.map((f) => (
        <FixtureMesh key={f.key} fixture={f} lights={floor.lights} hover={hover} go={go} />
      ))}
      <CameraRig target={view.target} area={view.size} turn={turn} />
      <FrameMeter onRate={onRate} />
    </>
  )
}

const KEY_HELP =
  'Keys: Page Up and Page Down change floor; the arrow keys (or Q and E) turn the view; 1 to 9 look closer at a room; Escape shows the whole floor.'

export function OfficePage() {
  const gameId = useGameId()
  const building = useBuilding(gameId)
  const [params, setParams] = useSearchParams()
  const floors = (building.data?.floors ?? []).toSorted((a, b) => a.level - b.level)
  const asked = params.get('floor')
  // The first floor, where the data work is, unless another is asked for.
  const current =
    floors.find((f) => f.code === asked) ?? floors.find((f) => f.code === 'first') ?? floors[0]
  const floorData = useOfficeFloor(gameId, current?.code ?? null)
  // The budget's busiest case (dev only): ?crowd=45 fills the floor and moves everyone
  // between their desks and a meeting room every four seconds.
  const crowd = import.meta.env.DEV ? Number(params.get('crowd')) || 0 : 0
  const phase = crowd ? Math.floor(floorData.dataUpdatedAt / 4000) : 0
  const data = floorData.data
  const code = current?.code ?? null
  // Laid out once per refresh, not per render: the walks restage whenever ``floor`` changes.
  const floor = useMemo(() => {
    if (!data || data.code !== code) return null
    return layOut(crowd ? crowded(data, crowd, phase) : data, gameId)
    // oxlint-disable-next-line react/preserve-manual-memoization
  }, [data, code, gameId, crowd, phase])
  const navigate = useNavigate()
  const [hovered, setHovered] = useState<string | null>(null)
  const [fps, setFps] = useState<number | null>(null)
  const [turn, setTurn] = useState<Turn>(0)
  const [room, setRoom] = useState<string | null>(null)

  if (building.isPending) return <Loading what="the office" />
  if (building.isError) return <Failed error={building.error} />
  if (building.data.no_office || !current)
    return (
      <Page title="Office" subtitle="The bureau has no office yet.">
        <p className="text-sm text-slate-700">
          Staff need desks, and IT is installed in an office.{' '}
          <Link to={`/games/${gameId}/startup`} className="text-brand hover:underline">
            Rent one on the Startup screen
          </Link>
          .
        </p>
      </Page>
    )

  const goFloor = (code: string) => {
    setRoom(null)
    setHovered(null)
    setParams({ floor: code }, { replace: true })
  }
  const index = floors.indexOf(current)
  const zoomed = floor?.rooms.find((r) => r.code === room) ?? null

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const c = command(e.key)
    if (!c) return
    e.preventDefault()
    if (c.type === 'floor') {
      const next = floors[index + c.by]
      if (next) goFloor(next.code)
    } else if (c.type === 'turn') setTurn((t) => turned(t, c.by))
    else if (c.type === 'whole') setRoom(null)
    else {
      const r = floor?.rooms.find((x) => x.index === c.index)
      if (r) setRoom(r.code)
    }
  }

  const people = floor?.people ?? []
  const empty = floor?.desks.filter((d) => !d.person) ?? []
  return (
    <Page
      title="Office"
      subtitle={`${building.data.name}. Click a room to look closer, or a desk, a person or a piece of furniture to open its screen.`}
    >
      <div
        className="flex flex-wrap items-center gap-2"
        role="toolbar"
        aria-label="The office view"
      >
        {floors.length > 1 &&
          [...floors].reverse().map((f) => (
            <button
              key={f.code}
              type="button"
              aria-pressed={f.code === current.code}
              onClick={() => goFloor(f.code)}
              className={
                f.code === current.code
                  ? 'rounded border border-brand bg-brand px-2.5 py-1 text-sm text-white'
                  : BUTTON
              }
            >
              {f.name}
            </button>
          ))}
        <span className="mx-1 h-5 w-px bg-slate-200" />
        <button type="button" className={BUTTON} onClick={() => setTurn((t) => turned(t, -1))}>
          ⟲ Turn left
        </button>
        <button type="button" className={BUTTON} onClick={() => setTurn((t) => turned(t, 1))}>
          Turn right ⟳
        </button>
        <label className="flex items-center gap-1 text-sm">
          Look closer at
          <select
            value={room ?? ''}
            onChange={(e) => setRoom(e.target.value || null)}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="">the whole floor</option>
            {floor?.rooms.map((r) => (
              <option key={r.code} value={r.code}>
                {r.index}. {r.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        className="relative h-[520px] overflow-hidden rounded-lg border border-slate-200 bg-white focus:ring-2 focus:ring-brand focus:outline-none"
        tabIndex={0}
        role="region"
        aria-label={`The office in 3D, ${current.name}. ${KEY_HELP}`}
        onKeyDown={onKey}
        data-testid="office-view"
      >
        {floor ? (
          <Canvas
            orthographic
            camera={{ position: [11, 10, 13], zoom: 30, near: 0.1, far: 200 }}
            dpr={[1, 2]}
            fallback={
              <p className="p-4 text-sm text-slate-600">
                This computer cannot draw the 3D office. Everything it shows is listed below.
              </p>
            }
            aria-hidden
          >
            <Scene
              floor={floor}
              room={room}
              turn={turn}
              hover={setHovered}
              go={navigate}
              onZoom={setRoom}
              onRate={setFps}
            />
          </Canvas>
        ) : floorData.isError ? (
          <Failed error={floorData.error} />
        ) : (
          <Loading what={current.name.toLowerCase()} />
        )}
        {/* The label, then the room's details under it, however many lines the label takes. */}
        <div className="pointer-events-none absolute top-3 left-3 flex max-w-[70%] flex-col items-start gap-1.5">
          <p className="rounded bg-slate-900/80 px-3 py-1.5 text-sm text-white empty:hidden">
            {hovered ?? (zoomed ? zoomed.label : '')}
          </p>
          {zoomed && zoomed.details.length > 0 && (
            <ul
              className="space-y-0.5 rounded bg-white/90 px-3 py-2 text-xs text-slate-800 shadow"
              data-testid="office-details"
            >
              {zoomed.details.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </div>
        <p className="absolute bottom-2 left-3 text-xs text-slate-400" data-testid="office-place">
          {current.name}
          {zoomed ? ` › ${zoomed.name}` : ''}
          {floors.length > 1 ? ` (${index + 1} of ${floors.length})` : ''}
        </p>
        {fps !== null && (
          <p className="absolute right-3 bottom-2 text-xs text-slate-400" data-testid="fps">
            {fps} frames a second
          </p>
        )}
      </div>
      <p className="text-xs text-slate-500">{KEY_HELP}</p>
      {floor && (
        <>
          <p className="text-sm text-slate-700">{floor.summary}</p>
          <div className="grid gap-4 text-sm md:grid-cols-2">
            <section>
              <h2 className="mb-1 font-medium">Rooms: {current.name}</h2>
              <ul className="space-y-1" data-testid="office-rooms">
                {floor.rooms.map((r) => (
                  <li key={r.code}>
                    <Link to={r.to} className="text-brand hover:underline">
                      {r.name}
                    </Link>
                    : {r.summary}
                    {r.details.length > 0 && (
                      <ul className="ml-4 list-disc text-slate-600">
                        {r.details.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h2 className="mb-1 font-medium">People here</h2>
              {people.length === 0 && empty.length === 0 ? (
                <p className="text-slate-600">No one works on this floor yet.</p>
              ) : (
                <ul className="space-y-1" data-testid="office-people">
                  {people.map((d) => (
                    <li key={d.key}>
                      <Link to={d.to} className="text-brand hover:underline">
                        {d.label}
                      </Link>
                    </li>
                  ))}
                  {empty.length > 0 && (
                    <li>
                      <Link to={empty[0].to} className="text-brand hover:underline">
                        {empty.length} empty desk{empty.length === 1 ? '' : 's'}: room to hire
                      </Link>
                    </li>
                  )}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </Page>
  )
}
