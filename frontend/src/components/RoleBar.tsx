import { type RoleInfo, type RoleState, useGameCommand, useRoles } from '../api/game'

/** Game time of day, as the clock bar shows it (game times are kept in UTC). */
function time(value: string): string {
  return new Date(value).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  })
}

/** Who the player is working as, and the switch to another role (P3.1). */
export function RoleSwitcher({ gameId, role }: { gameId: number; role: RoleState }) {
  const roles = useRoles(gameId)
  const change = useGameCommand(gameId, '/role/')
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor="role" className="text-slate-500">
        Working as
      </label>
      <select
        id="role"
        className="rounded border border-slate-300 bg-white px-2 py-1"
        value={role.code}
        disabled={change.isPending || !roles.data}
        onChange={(e) => change.mutate({ role: e.target.value })}
      >
        {(roles.data?.roles ?? [{ code: role.code, title: role.title }]).map((r) => (
          <option key={r.code} value={r.code}>
            {r.title}
          </option>
        ))}
      </select>
      {!role.ready && (
        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800" role="status">
          Taking over{role.ready_at ? ` until ${time(role.ready_at)}` : ''}: run the clock on
        </span>
      )}
      {change.isError && (
        <span className="text-xs text-red-700" role="alert">
          {change.error.message}
        </span>
      )}
    </div>
  )
}

/** The role whose screen this is: a department head's if one has it, else the CEO's. */
function ownerOf(screen: string, roles: RoleInfo[]): RoleInfo | undefined {
  const holders = roles.filter((r) => r.screens.includes(screen))
  return holders.find((r) => r.code !== 'CEO') ?? holders[0]
}

/** Shown on a screen the current role does not work on: you can look, not act. */
export function ScreenOwner({
  gameId,
  screen,
  role,
}: {
  gameId: number
  screen: string
  role: RoleState
}) {
  const roles = useRoles(gameId)
  const change = useGameCommand(gameId, '/role/')
  if (!roles.data || role.screens.includes(screen)) return null
  const owner = ownerOf(screen, roles.data.roles)
  if (!owner) return null
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm"
      role="note"
    >
      <span>
        This is the {owner.title}&apos;s screen. As {role.title} you can look, but not act here.
      </span>
      <button
        type="button"
        className="rounded bg-brand px-3 py-1 text-white disabled:opacity-50"
        disabled={change.isPending}
        onClick={() => change.mutate({ role: owner.code })}
      >
        Work as {owner.title}
      </button>
    </div>
  )
}
