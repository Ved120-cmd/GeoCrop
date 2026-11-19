import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource/inter/300.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/source-serif-4/300.css'
import '@fontsource/source-serif-4/400.css'
import '@fontsource/source-serif-4/600.css'
import '@fontsource/noto-sans-devanagari/400.css'
import '@fontsource/noto-sans-devanagari/600.css'
import '@fontsource/noto-serif-devanagari/300.css'
import '@fontsource/noto-serif-devanagari/500.css'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App'
import { I18nProvider } from './lib/i18n'
import { ProfileProvider } from './lib/profile'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <I18nProvider>
        <ProfileProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ProfileProvider>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
)
