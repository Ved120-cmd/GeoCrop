import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import { Container, Loading } from './components/ui'

// Pages are code-split so the home page loads without the map and chart libraries.
const Onboarding = lazy(() => import('./pages/Onboarding'))
const MonitorOverview = lazy(() => import('./pages/MonitorOverview'))
const DistrictPage = lazy(() => import('./pages/DistrictPage'))
const MyFarm = lazy(() => import('./pages/MyFarm'))
const SoilPage = lazy(() => import('./pages/SoilPage'))
const ModulePage = lazy(() => import('./pages/ModulePage'))
const SimulatorPage = lazy(() => import('./pages/SimulatorPage'))
const PredictPage = lazy(() => import('./pages/PredictPage'))

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<Container><Loading /></Container>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/profile" element={<Onboarding edit />} />
        <Route path="/monitor" element={<MonitorOverview />} />
        <Route path="/monitor/region/:region" element={<MonitorOverview />} />
        <Route path="/monitor/district/:id" element={<DistrictPage />} />
        <Route path="/my-farm" element={<MyFarm />} />
        <Route path="/soil" element={<SoilPage />} />
        <Route path="/predict" element={<PredictPage />} />
        <Route path="/predict/district/:id" element={<PredictPage />} />
        <Route path="/crop-advisor" element={<ModulePage module="advisor" />} />
        <Route path="/plant-doctor" element={<ModulePage module="doctor" />} />
        <Route path="/simulator" element={<SimulatorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </Layout>
  )
}
