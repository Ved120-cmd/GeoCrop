// Thin typed client for the GeoCrop FastAPI backend (proxied at /api by Vite).

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies must not get a JSON content type (the browser sets the multipart boundary)
  // X-GeoCrop-Client: the API rejects state-changing requests without it (CSRF protection; see geocrop/api/security.py)
  const headers: Record<string, string> = init?.body instanceof FormData ? { 'X-GeoCrop-Client': 'web' } : { 'Content-Type': 'application/json', 'X-GeoCrop-Client': 'web' }
  const r = await fetch(`/api${path}`, { headers, ...init })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(r.status, msg)
  }
  return r.status === 204 ? (undefined as T) : r.json()
}

export const api = {
  get: <T,>(p: string) => req<T>(p),
  post: <T,>(p: string, body: unknown) => req<T>(p, { method: 'POST', body: JSON.stringify(body) }),
  put: <T,>(p: string, body: unknown) => req<T>(p, { method: 'PUT', body: JSON.stringify(body) }),
  del: (p: string) => req<void>(p, { method: 'DELETE' }),
  postForm: <T,>(p: string, body: FormData) => req<T>(p, { method: 'POST', body }),
}

// ---------- types (mirror geocrop/api) ----------
export type Stress = 'none' | 'mild' | 'moderate' | 'severe'

export interface Indicator { as_of: string; status: string; [k: string]: unknown }
export interface DistrictOverview {
  district_id: number
  district: string
  region: string
  subregion: string | null
  indicators: {
    vegetation?: Indicator & { vhi: number; vhi_class: string; ndvi: number; ndvi_pct_normal: number; vci: number; tci: number }
    soil_moisture?: Indicator & { sm_percentile: number; sm_class: string; sm_rootzone: number }
    evaporative_stress?: Indicator & { esi_z: number; et_pet_ratio: number }
    spi?: Indicator & { spi_1: number; spi_3: number; spi_class: string }
    monsoon_departure?: Indicator & { departure_pct: number; departure_class: string; monsoon_cum_mm: number; monsoon_normal_mm: number }
    stress_today?: Indicator & { stress: Stress; depletion_pct: number; days_until_stress: number | null; initialised_from: string }
  }
}
export interface Overview {
  districts: DistrictOverview[]
  freshness: { last_update: string; sources: Record<string, { latest: string; status_latest: string; median_valid_frac_latest: number }> } | null
}
export interface Region { key: string; name: string; name_mr: string; district_ids: number[]; note?: string }

export interface CropOption { code: string; label: string; label_mr: string; season_hint: string | null; stress_estimate_supported: boolean; note: string | null }

export interface CropPlanting { id?: string; crop: string; crop_other?: string | null; season: 'kharif' | 'rabi' | 'summer' | 'annual'; sowing_date?: string | null }
export interface IrrigationEvent { id: string; date: string; amount_mm: number; method: string | null }
export interface Farm {
  id?: string; name?: string | null; district_id: number; district?: string; taluka?: string | null; village?: string | null
  lat?: number | null; lon?: number | null; area_value?: number | null; area_unit: 'acre' | 'hectare' | 'guntha'
  irrigation_source: string; soil_type_reported: string; crops: CropPlanting[]; irrigation?: IrrigationEvent[]
}
export interface Profile { id: string; name: string; phone: string | null; language: 'en' | 'mr'; created_at: string; farms: Farm[] }
export interface ProfileIn { name: string; phone?: string | null; language: 'en' | 'mr'; farm: Farm }

export interface NowcastDay {
  date: string; stage?: string; kc?: number; rain_mm?: number; irrigation_mm?: number; eto_mm?: number; depletion_pct?: number
  ks?: number; stress?: string; kind?: string; rain_src?: string; eto_src?: string; taw_mm?: number; raw_mm?: number; dr_mm?: number
}
export interface FarmNowcast { available: boolean; reason?: string; crop?: string; sowing_date?: string; meta?: Record<string, unknown>; daily?: NowcastDay[] }

export interface SeriesPoint { date: string; mean: number | null; median: number | null; p10: number | null; p90: number | null; valid_frac: number | null; status: string }
export interface Series { district: string; variable: string; units: string; data: SeriesPoint[] }

export interface SoilProp { property: string; label: string; unit: string; depth: string; mean: number; p10: number; p90: number; mask_used: string }
export interface SoilDistrict {
  district_id: number; value_type: string; properties: SoilProp[]; texture: { depth: string; texture: string }[]
  water: { field_capacity_topsoil: number; wilting_point_topsoil: number; available_water_mm_per_m: number; method: string }; caveat: string
}
