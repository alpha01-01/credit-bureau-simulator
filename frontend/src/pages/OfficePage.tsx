/**
 * The office in 3D (P3.2: a one-floor trial for Phase 4). Loaded on its own, so the
 * rest of the game never downloads three.js. It draws only what ``layOut`` gives:
 * the game's state, refreshed every two seconds; clicking opens the 2D screen.
 */
import { Canvas, type ThreeEvent, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Mesh, MeshStandardMaterial } from 'three'

import { useOffice } from '../api/game'
import { useGameId } from '../app/useGameId'
import { Failed, Loading, Page } from '../components/ui'
import { COLOURS, type Desk, type Floor, layOut } from '../lib/office'

type Point = [number, number, number]
type Pick = { label: string; to: string }

/** Pointer handlers shared by everything that can be clicked. */
function pickable(pick: Pick, onHover: (label: string | null) => void, go: (to: string) => void) {
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

function Person({ at, colour }: { at: Point; colour: string }) {
  return (
    <group position={at}>
      <mesh position={[0, 0.55, 0]}>
        <cylinderGeometry args={[0.18, 0.24, 0.7, 6]} />
        <meshStandardMaterial color={colour} flatShading />
      </mesh>
      <mesh position={[0, 1.05, 0]}>
        <icosahedronGeometry args={[0.17, 0]} />
        <meshStandardMaterial color={COLOURS.skin} flatShading />
      </mesh>
    </group>
  )
}

function DeskGroup({
  desk,
  hover,
  go,
}: {
  desk: Desk
  hover: (l: string | null) => void
  go: (to: string) => void
}) {
  const events = pickable(desk, hover, go)
  return (
    <group position={desk.position} {...events}>
      <Box size={[1.4, 0.08, 0.8]} at={[0, 0.75, 0]} colour={COLOURS.deskTop} />
      <Box size={[1.3, 0.7, 0.1]} at={[0, 0.36, -0.3]} colour={COLOURS.desk} />
      <Box size={[0.5, 0.35, 0.05]} at={[0, 1.0, -0.2]} colour="#1e293b" />
      <Box size={[0.5, 0.45, 0.5]} at={[0, 0.23, 0.75]} colour="#475569" />
      {Array.from({ length: desk.pile }, (_, i) => (
        <Box
          key={i}
          size={[0.3, 0.02, 0.4]}
          at={[0.45, 0.8 + i * 0.025, 0.1]}
          colour={COLOURS.paper}
        />
      ))}
      {desk.person?.seated && <Person at={[0, 0.25, 0.75]} colour={desk.person.colour} />}
    </group>
  )
}

/** The server rack: green lights, or red ones blinking while the systems are down. */
function Rack({
  rack,
  hover,
  go,
}: {
  rack: Floor['rack']
  hover: (l: string | null) => void
  go: (to: string) => void
}) {
  const lights = useRef<Mesh[]>([])
  useFrame(({ clock }) => {
    const on = !rack.down || Math.floor(clock.elapsedTime * 3) % 2 === 0
    for (const light of lights.current) {
      const material = light.material as MeshStandardMaterial
      material.emissiveIntensity = on ? 1.2 : 0.1
    }
  })
  const colour = rack.down ? COLOURS.rackDown : COLOURS.rackOk
  return (
    <group position={rack.position} {...pickable(rack, hover, go)}>
      <Box size={[0.9, 2.2, 0.8]} at={[0, 1.1, 0]} colour={COLOURS.rack} />
      {[0.5, 0.9, 1.3, 1.7].map((y, i) => (
        <mesh
          key={y}
          position={[0.3, y, 0.41]}
          ref={(m) => {
            if (m) lights.current[i] = m
          }}
        >
          <boxGeometry args={[0.12, 0.06, 0.02]} />
          <meshStandardMaterial color={colour} emissive={colour} emissiveIntensity={1.2} />
        </mesh>
      ))}
    </group>
  )
}

function MeetingRoom({
  room,
  hover,
  go,
}: {
  room: Floor['meeting']
  hover: (l: string | null) => void
  go: (to: string) => void
}) {
  return (
    <group position={room.position} {...pickable(room, hover, go)}>
      <Box size={[2.2, 0.08, 1.2]} at={[0, 0.75, 0]} colour={COLOURS.table} />
      <Box size={[0.3, 0.7, 0.3]} at={[0, 0.36, 0]} colour={COLOURS.table} />
      {[-0.7, 0, 0.7].flatMap((x) => [
        <Box key={`a${x}`} size={[0.45, 0.45, 0.45]} at={[x, 0.23, -0.95]} colour="#475569" />,
        <Box key={`b${x}`} size={[0.45, 0.45, 0.45]} at={[x, 0.23, 0.95]} colour="#475569" />,
      ])}
      <mesh position={[1.6, 1.1, 0]}>
        <boxGeometry args={[0.05, 2.2, 3]} />
        <meshStandardMaterial color={COLOURS.glass} transparent opacity={0.35} />
      </mesh>
    </group>
  )
}

/** Fit the whole floor (about 17 by 11 metres on screen) into the canvas, whatever its size. */
function FitCamera() {
  const { camera, size } = useThree()
  useEffect(() => {
    // A three.js camera is a mutable object: React Three Fiber expects it to be set like this.
    // oxlint-disable-next-line react/immutability
    camera.zoom = Math.min(size.width / 18, size.height / 11.5)
    camera.lookAt(0, 0.5, 1.2)
    camera.updateProjectionMatrix()
  }, [camera, size.width, size.height])
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
  hover,
  go,
  onRate,
}: {
  floor: Floor
  hover: (l: string | null) => void
  go: (to: string) => void
  onRate: (fps: number) => void
}) {
  return (
    <>
      <ambientLight intensity={0.75} />
      <directionalLight position={[6, 12, 8]} intensity={1.6} />
      <Box size={[16, 0.1, 9]} at={[0, -0.05, 1.5]} colour={COLOURS.floor} />
      <Box size={[16, 2.6, 0.15]} at={[0, 1.3, -2.9]} colour={COLOURS.wall} />
      <Box size={[0.15, 2.6, 9]} at={[-8, 1.3, 1.5]} colour={COLOURS.wall} />
      {floor.desks.map((d) => (
        <DeskGroup key={d.key} desk={d} hover={hover} go={go} />
      ))}
      <Rack rack={floor.rack} hover={hover} go={go} />
      <MeetingRoom room={floor.meeting} hover={hover} go={go} />
      <FitCamera />
      <FrameMeter onRate={onRate} />
    </>
  )
}

export function OfficePage() {
  const gameId = useGameId()
  const office = useOffice(gameId)
  const navigate = useNavigate()
  const [hovered, setHovered] = useState<string | null>(null)
  const [fps, setFps] = useState<number | null>(null)
  if (office.isPending) return <Loading what="the office" />
  if (office.isError) return <Failed error={office.error} />
  const floor = layOut(office.data, gameId)
  const all = [...floor.desks, floor.rack, floor.meeting]
  return (
    <Page
      title="Office"
      subtitle="Data Operations' floor, as the game stands. Click a desk, a person, the server rack or the meeting room to open its screen. (A first trial of the 3D office.)"
    >
      <div className="relative h-[480px] overflow-hidden rounded-lg border border-slate-200 bg-white">
        <Canvas
          orthographic
          camera={{ position: [11, 10, 13], zoom: 46, near: 0.1, far: 100 }}
          dpr={[1, 2]}
          fallback={
            <p className="p-4 text-sm text-slate-600">
              This computer cannot draw the 3D office. Everything it shows is listed below.
            </p>
          }
          aria-hidden
        >
          <Scene floor={floor} hover={setHovered} go={navigate} onRate={setFps} />
        </Canvas>
        {hovered && (
          <p className="pointer-events-none absolute top-3 left-3 rounded bg-slate-900/80 px-3 py-1.5 text-sm text-white">
            {hovered}
          </p>
        )}
        {fps !== null && (
          <p className="absolute right-3 bottom-2 text-xs text-slate-400" data-testid="fps">
            {fps} frames a second
          </p>
        )}
      </div>
      <p className="text-sm text-slate-700">{floor.summary}</p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {all.map((thing) => (
          <li key={thing.label}>
            <Link to={thing.to} className="text-brand hover:underline">
              {thing.label}
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  )
}
