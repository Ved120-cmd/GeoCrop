import { createContext, useContext, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Profile } from './api'
import { PROFILES_ENABLED } from './config'

// No login yet: the profile id is remembered in this browser; the profile itself lives in PostgreSQL.
const KEY = 'geocrop.profileId'

interface Ctx {
  profileId: string | null
  profile: Profile | undefined
  loading: boolean
  setProfileId: (id: string | null) => void
  refresh: () => void
}
const P = createContext<Ctx | null>(null)

export function ProfileProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [profileId, setId] = useState<string | null>(() => { if (!PROFILES_ENABLED) return null; try { return localStorage.getItem(KEY) } catch { return null } })
  const q = useQuery({
    queryKey: ['profile', profileId],
    enabled: PROFILES_ENABLED && !!profileId,
    queryFn: async () => {
      try { return await api.get<Profile>(`/profiles/${profileId}`) } catch (e) {
        if (e instanceof ApiError && e.status === 404) { setProfileId(null); return undefined }
        throw e
      }
    },
  })
  function setProfileId(id: string | null) {
    try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY) } catch { /* ignore */ }
    setId(id)
  }
  return (
    <P.Provider value={{ profileId, profile: q.data, loading: q.isLoading, setProfileId, refresh: () => qc.invalidateQueries({ queryKey: ['profile'] }) }}>
      {children}
    </P.Provider>
  )
}

export function useProfile() {
  const c = useContext(P)
  if (!c) throw new Error('useProfile outside provider')
  return c
}
