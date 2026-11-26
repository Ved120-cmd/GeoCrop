import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import { Container, Loading } from './components/ui'
import { PROFILES_ENABLED } from './lib/config'

// Pages are code-split so the home page loads without the map and chart libraries.
const Onboarding = lazy(() => import('./pages/Onboarding'))
const MonitorOverview = lazy(() => import('./pages/MonitorOverview'))
const DistrictPage = lazy(() => import('./pages/DistrictPage'))
const MyFarm = lazy(() => import('./pages/MyFarm'))
const SoilPage = lazy(() => import('./pages/SoilPage'))
const SimulatorPage = lazy(() => import('./pages/SimulatorPage'))
const PredictPage = lazy(() => import('./pages/PredictPage'))
const DoctorPage = lazy(() => import('./pages/DoctorPage'))
const AdvisorPage = lazy(() => import('./pages/AdvisorPage'))

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<Container><Loading /></Container>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/onboarding" element={PROFILES_ENABLED ? <Onboarding /> : <Navigate to="/" replace />} />
        <Route path="/profile" element={PROFILES_ENABLED ? <Onboarding edit /> : <Navigate to="/" replace />} />
        <Route path="/monitor" element={<MonitorOverview />} />
        <Route path="/monitor/region/:region" element={<MonitorOverview />} />
        <Route path="/monitor/district/:id" element={<DistrictPage />} />
        <Route path="/my-farm" element={PROFILES_ENABLED ? <MyFarm /> : <Navigate to="/" replace />} />
        <Route path="/soil" element={<SoilPage />} />
        <Route path="/predict" element={<PredictPage />} />
        <Route path="/predict/district/:id" element={<PredictPage />} />
        <Route path="/crop-advisor" element={<AdvisorPage />} />
        <Route path="/plant-doctor" element={<DoctorPage />} />
        <Route path="/simulator" element={<SimulatorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </Layout>
  )
}
