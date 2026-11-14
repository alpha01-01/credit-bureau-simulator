import { Link, Navigate, Outlet, RouterProvider, createBrowserRouter } from 'react-router'

import { useLogout, useSession } from '../api/session'
import { Failed, Loading } from '../components/ui'
import { BriefingPage } from '../pages/BriefingPage'
import { CustomerPage, CustomersPage } from '../pages/CustomersPage'
import { DashboardPage } from '../pages/DashboardPage'
import { EnquiriesPage } from '../pages/EnquiriesPage'
import { FinanceLayout, InvoicesPage, LedgerPage, StatementsPage } from '../pages/FinancePage'
import { GamesPage } from '../pages/GamesPage'
import { LoginPage } from '../pages/LoginPage'
import { QueuePage, WorkItemPage } from '../pages/QueuePage'
import { SubmissionPage, SubmissionsPage } from '../pages/SubmissionsPage'
import { GameLayout } from './GameLayout'

function Shell() {
  const session = useSession()
  const logout = useLogout()
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Sim<span className="text-brand">B</span>
          </Link>
          {session.data?.authenticated && (
            <span className="flex items-center gap-3 text-sm text-slate-500">
              {session.data.username}
              <button
                type="button"
                onClick={() => logout.mutate()}
                className="text-slate-600 hover:underline"
              >
                Sign out
              </button>
            </span>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

function RequireSignIn() {
  const session = useSession()
  if (session.isPending) return <Loading what="your session" />
  if (session.isError) return <Failed error={session.error} />
  if (!session.data.authenticated) return <Navigate to="/login" replace />
  return <Outlet />
}

const routes = [
  {
    element: <Shell />,
    children: [
      { path: '/login', element: <LoginPage /> },
      {
        element: <RequireSignIn />,
        children: [
          { path: '/', element: <GamesPage /> },
          {
            path: '/games/:gameId',
            element: <GameLayout />,
            children: [
              { index: true, element: <BriefingPage /> },
              { path: 'dashboard', element: <DashboardPage /> },
              { path: 'submissions', element: <SubmissionsPage /> },
              { path: 'submissions/:reference', element: <SubmissionPage /> },
              { path: 'queue', element: <QueuePage /> },
              { path: 'queue/:number', element: <WorkItemPage /> },
              { path: 'customers', element: <CustomersPage /> },
              { path: 'customers/:reference', element: <CustomerPage /> },
              { path: 'enquiries', element: <EnquiriesPage /> },
              {
                path: 'finance',
                element: <FinanceLayout />,
                children: [
                  { index: true, element: <StatementsPage /> },
                  { path: 'ledger', element: <LedgerPage /> },
                  { path: 'invoices', element: <InvoicesPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
]

const router = createBrowserRouter(routes)

export function App() {
  return <RouterProvider router={router} />
}
