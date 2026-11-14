import type { ReactNode } from 'react'
import { Link } from 'react-router'

import type { Drill } from '../api/game'
import { drillPath } from '../lib/drill'

export function Page({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section aria-labelledby="page-title" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="page-title" className="text-xl font-semibold tracking-tight">
            {title}
          </h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {title && <h2 className="mb-3 text-sm font-semibold text-slate-700">{title}</h2>}
      {children}
    </div>
  )
}

export function Loading({ what = 'data' }: { what?: string }) {
  return (
    <p role="status" className="text-sm text-slate-500">
      Loading {what}…
    </p>
  )
}

export function Failed({ error }: { error: unknown }) {
  return (
    <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
      {error instanceof Error ? error.message : 'Something went wrong.'}
    </p>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>
}

const TONES = {
  neutral: 'bg-slate-100 text-slate-700',
  good: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-800',
  bad: 'bg-red-50 text-red-800',
  info: 'bg-sky-50 text-sky-800',
} as const

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: keyof typeof TONES
  children: ReactNode
}) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  )
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  )
}

export function Td({ children, right }: { children: ReactNode; right?: boolean }) {
  return <td className={`px-3 py-2 ${right ? 'text-right tabular-nums' : ''}`}>{children}</td>
}

export function WhyLink({ gameId, drill, label }: { gameId: number; drill: Drill; label: string }) {
  return (
    <Link
      to={drillPath(gameId, drill)}
      className="text-xs font-medium text-brand underline-offset-2 hover:underline"
      aria-label={`Why? Show the records behind ${label}`}
    >
      Why?
    </Link>
  )
}
