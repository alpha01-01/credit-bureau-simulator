import { Suspense, lazy } from 'react'
import { Link, Navigate, Outlet, RouterProvider, createBrowserRouter } from 'react-router'

import { useLogout, useSession } from '../api/session'
import { Failed, Loading } from '../components/ui'
import { BriefingPage } from '../pages/BriefingPage'
import { CustomerPage, CustomersPage } from '../pages/CustomersPage'
import { DashboardPage } from '../pages/DashboardPage'
import { DisputesPage } from '../pages/DisputesPage'
import { EnquiriesPage } from '../pages/EnquiriesPage'
import { EventsPage } from '../pages/EventsPage'
import { FinanceLayout, InvoicesPage, LedgerPage, StatementsPage } from '../pages/FinancePage'
import { GamesPage } from '../pages/GamesPage'
import { LoginPage } from '../pages/LoginPage'
import { ProvidersPage } from '../pages/ProvidersPage'
import { QueuePage, WorkItemPage } from '../pages/QueuePage'
import { ReviewPage, ReviewsPage } from '../pages/ReviewPage'
import { RulesPage } from '../pages/RulesPage'
import { SubmissionPage, SubmissionsPage } from '../pages/SubmissionsPage'
import { SubscribersPage } from '../pages/SubscribersPage'
import { StaffPage } from '../pages/StaffPage'
import { OnboardingPage } from '../pages/OnboardingPage'
import { ProductsPage } from '../pages/ProductsPage'
import { SalesPage } from '../pages/SalesPage'
import { SupportPage } from '../pages/SupportPage'
import { ItPage } from '../pages/ItPage'
import { HealthPage } from '../pages/HealthPage'
import { AccountsPage } from '../pages/AccountsPage'
import { MissionsPage } from '../pages/MissionsPage'
import { HandbookPage } from '../pages/HandbookPage'
import { AnalyticsPage } from '../pages/AnalyticsPage'
import { ConsolePage } from '../pages/ConsolePage'
import { ScorecardPage, ScorecardsPage } from '../pages/ScorecardsPage'
import { CompliancePage } from '../pages/CompliancePage'
import { BankPage, BillsPage, BudgetPage, ClosePage } from '../pages/FinanceDeptPage'
import { GameLayout } from './GameLayout'

// The 3D office is loaded only when it is opened (three.js is large; P3.2).
const OfficePage = lazy(() =>
  import('../pages/OfficePage').then((m) => ({ default: m.OfficePage })),
)

function Shell() {
  const session = useSession()
  const logout = useLogout()
  return (
    <div className="min-h-screen">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to content
      </a>
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
      <main id="content" tabIndex={-1} className="mx-auto max-w-7xl px-4 py-6 outline-none">
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
              { path: 'events', element: <EventsPage /> },
              { path: 'reviews', element: <ReviewsPage /> },
              { path: 'rules', element: <RulesPage /> },
              { path: 'providers', element: <ProvidersPage /> },
              { path: 'disputes', element: <DisputesPage /> },
              { path: 'subscribers', element: <SubscribersPage /> },
              { path: 'staff', element: <StaffPage /> },
              { path: 'sales', element: <SalesPage /> },
              { path: 'onboarding', element: <OnboardingPage /> },
              { path: 'support', element: <SupportPage /> },
              { path: 'products', element: <ProductsPage /> },
              { path: 'it', element: <ItPage /> },
              { path: 'health', element: <HealthPage /> },
              { path: 'missions', element: <MissionsPage /> },
              { path: 'handbook', element: <HandbookPage /> },
              { path: 'analytics', element: <AnalyticsPage /> },
              { path: 'console', element: <ConsolePage /> },
              { path: 'scorecards', element: <ScorecardsPage /> },
              { path: 'compliance', element: <CompliancePage /> },
              { path: 'scorecards/:number', element: <ScorecardPage /> },
              {
                path: 'office',
                element: (
                  <Suspense fallback={<Loading what="the office" />}>
                    <OfficePage />
                  </Suspense>
                ),
              },
              { path: 'reviews/:period', element: <ReviewPage /> },
              { path: 'dashboard', element: <DashboardPage /> },
              { path: 'submissions', element: <SubmissionsPage /> },
              { path: 'submissions/:reference', element: <SubmissionPage /> },
              { path: 'queue', element: <QueuePage /> },
              { path: 'queue/:number', element: <WorkItemPage /> },
              { path: 'customers', element: <CustomersPage /> },
              { path: 'accounts', element: <AccountsPage /> },
              { path: 'customers/:reference', element: <CustomerPage /> },
              { path: 'enquiries', element: <EnquiriesPage /> },
              {
                path: 'finance',
                element: <FinanceLayout />,
                children: [
                  { index: true, element: <StatementsPage /> },
                  { path: 'ledger', element: <LedgerPage /> },
                  { path: 'invoices', element: <InvoicesPage /> },
                  { path: 'bills', element: <BillsPage /> },
                  { path: 'bank', element: <BankPage /> },
                  { path: 'budget', element: <BudgetPage /> },
                  { path: 'close', element: <ClosePage /> },
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
