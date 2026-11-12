import { useHealth } from '../api/health'

export function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <span className="text-lg font-semibold tracking-tight">
            Sim<span className="text-brand">B</span>
          </span>
          <span className="text-sm text-slate-500">Credit bureau simulator</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <SystemsCheck />
      </main>
    </div>
  )
}

function SystemsCheck() {
  const health = useHealth()

  return (
    <section
      aria-labelledby="systems-heading"
      className="rounded-lg border border-slate-200 bg-white p-6"
    >
      <h1 id="systems-heading" className="text-base font-semibold">
        Systems check
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        Frontend → API → PostgreSQL. The game itself arrives with the walking skeleton.
      </p>

      <div className="mt-4" role="status">
        {health.isPending && <p className="text-sm text-slate-500">Contacting the API…</p>}
        {health.isError && (
          <p className="text-sm text-red-700">
            The API is unreachable. Start the backend with{' '}
            <code className="rounded bg-slate-100 px-1">python manage.py runserver</code>.
          </p>
        )}
        {health.isSuccess && (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-slate-500">API</dt>
            <dd className="font-medium text-brand">{health.data.status}</dd>
            <dt className="text-slate-500">Database</dt>
            <dd>
              {health.data.database.vendor} {health.data.database.server_version}
            </dd>
          </dl>
        )}
      </div>
    </section>
  )
}
