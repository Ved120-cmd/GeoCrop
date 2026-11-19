import type { DistrictOverview } from './api'
import type { TKey } from './i18n'
import {
  DEPARTURE_BINS, ESI_BINS, SM_BINS, SPI_BINS, STRESS_BINS, VHI_BINS,
  departureBin, esiBin, smBin, spiBin, stressBin, vhiBin, type Bin,
} from './scales'

export type IndicatorKey = 'stress' | 'vhi' | 'sm' | 'spi' | 'dep' | 'esi'

export interface IndicatorDef {
  key: IndicatorKey
  label: TKey
  desc: TKey
  bins: Bin[]
  nature: 'estimate' | 'observation' | 'index'
  read: (d: DistrictOverview) => { value: number | null; display: string; bin: Bin | null; asOf?: string; status?: string }
  severity: (d: DistrictOverview) => number // higher = worse, for ranking
}

const fmt = (v: number | null | undefined, digits = 0, suffix = '') => (v == null || Number.isNaN(v) ? '–' : `${v.toFixed(digits)}${suffix}`)

export const INDICATORS: IndicatorDef[] = [
  {
    key: 'stress', label: 'ind_stress', desc: 'ind_stress_d', bins: STRESS_BINS, nature: 'estimate',
    read: (d) => { const s = d.indicators.stress_today; return { value: s?.depletion_pct ?? null, display: s ? `${fmt(s.depletion_pct)}%` : '–', bin: stressBin(s?.stress), asOf: s?.as_of, status: 'estimate' } },
    severity: (d) => d.indicators.stress_today?.depletion_pct ?? -1,
  },
  {
    key: 'vhi', label: 'ind_vhi', desc: 'ind_vhi_d', bins: VHI_BINS, nature: 'observation',
    read: (d) => { const v = d.indicators.vegetation; return { value: v?.vhi ?? null, display: fmt(v?.vhi), bin: vhiBin(v?.vhi), asOf: v?.as_of, status: v?.status } },
    severity: (d) => 100 - (d.indicators.vegetation?.vhi ?? 101),
  },
  {
    key: 'sm', label: 'ind_sm', desc: 'ind_sm_d', bins: SM_BINS, nature: 'observation',
    read: (d) => { const v = d.indicators.soil_moisture; return { value: v?.sm_percentile ?? null, display: v ? `${fmt(v.sm_percentile)}th pct` : '–', bin: smBin(v?.sm_percentile), asOf: v?.as_of, status: v?.status } },
    severity: (d) => 100 - (d.indicators.soil_moisture?.sm_percentile ?? 101),
  },
  {
    key: 'spi', label: 'ind_spi', desc: 'ind_spi_d', bins: SPI_BINS, nature: 'index',
    read: (d) => { const v = d.indicators.spi; return { value: v?.spi_3 ?? null, display: fmt(v?.spi_3, 2), bin: spiBin(v?.spi_3), asOf: v?.as_of?.slice(0, 7), status: v?.status } },
    severity: (d) => -(d.indicators.spi?.spi_3 ?? 99),
  },
  {
    key: 'dep', label: 'ind_dep', desc: 'ind_dep_d', bins: DEPARTURE_BINS, nature: 'index',
    read: (d) => { const v = d.indicators.monsoon_departure; return { value: v?.departure_pct ?? null, display: v ? `${v.departure_pct > 0 ? '+' : ''}${fmt(v.departure_pct)}%` : '–', bin: departureBin(v?.departure_pct), asOf: v?.as_of, status: v?.status } },
    severity: (d) => -(d.indicators.monsoon_departure?.departure_pct ?? 999),
  },
  {
    key: 'esi', label: 'ind_esi', desc: 'ind_esi_d', bins: ESI_BINS, nature: 'observation',
    read: (d) => { const v = d.indicators.evaporative_stress; return { value: v?.esi_z ?? null, display: v ? `z ${fmt(v.esi_z, 2)}` : '–', bin: esiBin(v?.esi_z), asOf: v?.as_of, status: v?.status } },
    severity: (d) => -(d.indicators.evaporative_stress?.esi_z ?? 99),
  },
]

export const indicatorByKey = (k: string) => INDICATORS.find((i) => i.key === k) ?? INDICATORS[0]
