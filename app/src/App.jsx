// Routes and the app shell.
//
// Every guarded route's `allow` list is the operation's `x-roles` from
// contracts/openapi.json, verbatim. The guard is UX: it tells a user why a screen is not
// theirs instead of 404-ing them. The backend refuses the data independently, and that is
// the access control.
//
//   /dashboard   sanketFunnel                         M, A
//   /queue       sanketQueue, sanketLead              A, M, RM   (+ assign/crm-push: M, A)
//   /consent     consentList/Get/Request/Fetch        A, M, RM   (+ replay: A)
//   /trust       sanketFunnel.published_metrics       M, A       <- see the note in ModelTrust
//   /radar       bundled radar_data.json              any signed-in user
//   /sources     metaSync, metaProvenance             A, M, CO, RM
//   /admin       admin/*                              A

import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import RequireAuth from './auth/RequireAuth'
import RequireRole from './auth/RequireRole'
import { useAuth } from './auth/AuthContext'
import ErrorBoundary from './components/ErrorBoundary'
import RouteAnnouncer from './components/RouteAnnouncer'
import SkipLink from './components/SkipLink'
import StaticDemoBanner from './components/StaticDemoBanner'
import Empty from './components/states/Empty'
import Loading from './components/states/Loading'
import { homeFor } from './components/AppShell'
import { PackProvider } from './data/PackContext'
// Login and the queue are the two screens a signed-in user reaches first and most often,
// so they stay in the main chunk. Everything else is split: the chart-heavy screens pull
// recharts, which is the single biggest thing this bundle contains, and a relationship
// manager on the queue should never download the manager's dashboard to look at it.
import ChangePassword from './screens/ChangePassword'
import Login from './screens/Login'
import Queue from './screens/Queue'

const Admin = lazy(() => import('./screens/Admin'))
const Consent = lazy(() => import('./screens/Consent'))
const DataSources = lazy(() => import('./screens/DataSources'))
const ManagerDashboard = lazy(() => import('./screens/ManagerDashboard'))
const ModelTrust = lazy(() => import('./screens/ModelTrust'))
const Radar = lazy(() => import('./screens/Radar'))

/**
 * `?tab=queue&lead=LB-…` was how the pre-router build deep-linked, and the demo video and
 * the deck both contain those links. Keep them working.
 */
const LEGACY_TAB = { mission: '/dashboard', queue: '/queue', radar: '/radar', trust: '/trust' }

function LegacyTabRedirect() {
  const location = useLocation()
  const { role, isStatic } = useAuth()
  const params = new URLSearchParams(location.search)
  const tab = params.get('tab')
  const target = LEGACY_TAB[tab] || homeFor(role, isStatic)
  params.delete('tab')
  params.delete('tour')
  const search = params.toString()
  return <Navigate to={{ pathname: target, search: search ? `?${search}` : '' }} replace />
}

export default function App() {
  const { ready, isStatic } = useAuth()

  return (
    <>
      <SkipLink />
      {isStatic && <StaticDemoBanner />}
      <RouteAnnouncer />
      {!ready ? (
        <div className="grid min-h-screen place-items-center bg-ink-900">
          <Loading label="Tuning SANKET…" inline />
        </div>
      ) : (
        <ErrorBoundary>
          {/* The bundled export is only fetched when there is no backend to ask, plus on
              Model & Trust, which needs it for the pre-registered validation table. */}
          <PackProvider>
            <Suspense fallback={<Loading label="Loading this screen…" />}>
              <Routes>
                <Route path="/" element={<LegacyTabRedirect />} />
                <Route path="/login" element={<Login />} />
                <Route path="/change-password" element={<RequireAuth><ChangePassword /></RequireAuth>} />

                <Route path="/dashboard" element={<RequireRole allow={['M', 'A']}><ManagerDashboard /></RequireRole>} />
                <Route path="/queue" element={<RequireRole allow={['A', 'M', 'RM']}><Queue /></RequireRole>} />
                <Route path="/consent" element={<RequireRole allow={['A', 'M', 'RM']}><Consent /></RequireRole>} />
                <Route path="/trust" element={<RequireRole allow={['M', 'A']}><ModelTrust /></RequireRole>} />
                <Route path="/radar" element={<RequireAuth><Radar /></RequireAuth>} />
                <Route path="/sources" element={<RequireAuth><DataSources /></RequireAuth>} />
                <Route path="/admin" element={<RequireRole allow={['A']}><Admin /></RequireRole>} />

                <Route
                  path="*"
                  element={(
                    <main id="main-content" className="grid min-h-screen place-items-center bg-ink-900 px-6">
                      <div className="w-full max-w-md">
                        <Empty
                          title="That page does not exist"
                          hint="The link may be from an older build. Use the navigation to get back to the lead queue."
                        />
                      </div>
                    </main>
                  )}
                />
              </Routes>
            </Suspense>
          </PackProvider>
        </ErrorBoundary>
      )}
    </>
  )
}
