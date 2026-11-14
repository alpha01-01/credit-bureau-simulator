import { type FormEvent, useState } from 'react'
import { Navigate } from 'react-router'

import { useLogin, useSession } from '../api/session'

export function LoginPage() {
  const session = useSession()
  const login = useLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  if (session.data?.authenticated) return <Navigate to="/" replace />

  function submit(event: FormEvent) {
    event.preventDefault()
    login.mutate({ username, password })
  }

  return (
    <form
      onSubmit={submit}
      className="mx-auto mt-16 max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h1 className="text-lg font-semibold">Sign in</h1>
      <label className="block text-sm">
        <span className="text-slate-600">Username</span>
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        <span className="text-slate-600">Password</span>
        <input
          type="password"
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      {login.error && (
        <p role="alert" className="text-sm text-red-700">
          {login.error.message}
        </p>
      )}
      <button
        type="submit"
        disabled={login.isPending}
        className="w-full rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
      >
        {login.isPending ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}
