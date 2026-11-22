import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Info } from 'lucide-react'
import { api, type Overview, type Region } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { INDICATORS, indicatorByKey } from '../lib/indicators'
import { NO_DATA } from '../lib/scales'
import { DistrictChoropleth, useDistrictGeo } from '../components/Maps'
import { BinPill, Container, ErrorBox, Legend, Loading, MethodNote, NatureBadge, SectionHeader, Swatch } from '../components/ui'
import { Reveal } from '../components/motion'

const REGION_ORDER = ['Konkan', 'Western Maharashtra', 'North Maharashtra', 'Khandesh', 'Marathwada', 'Vidarbha']

export default function MonitorOverview() {
  const { t, lang } = useI18n()
  const { region } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const ind = indicatorByKey(sp.get('ind') ?? 'stress')

  const geo = useDistrictGeo()
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/monitor/overview') })
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => api.get<Region[]>('/geo/regions'), staleTime: Infinity })

  const reg = regions.data?.find((r) => r.key === region)
  const focusIds = reg?.district_ids
  const byId = useMemo(() => new Map(ov.data?.districts.map((d) => [d.district_id, d]) ?? []), [ov.data])
  const rows = useMemo(() => {
    const list = (ov.data?.districts ?? []).filter((d) => !focusIds || focusIds.includes(d.district_id))
    return [...list].sort((a, b) => ind.severity(b) - ind.severity(a))
  }, [ov.data, focusIds, ind])
  const counts = useMemo(() => {
    const c = new Map<string, number>()
    rows.forEach((d) => { const b = ind.read(d).bin; c.set(b?.key ?? '_none', (c.get(b?.key ?? '_none') ?? 0) + 1) })
    return c
  }, [rows, ind])

  const colorFor = (id: number) => { const d = byId.get(id); return (d && ind.read(d).bin?.color) || NO_DATA }
  const tooltipFor = (id: number, name: string) => {
    const d = byId.get(id); if (!d) return name
    const r = ind.read(d)
    const lbl = r.bin ? pick(lang, r.bin.label, r.bin.label_mr) : t('no_data')
    return `<strong>${name}</strong><br/>${t(ind.label)}: ${r.display} · ${lbl}${r.asOf ? `<br/><span style="opacity:.75">${t('as_of')} ${r.asOf}</span>` : ''}`
  }
  const setInd = (k: string) => { sp.set('ind', k); setSp(sp, { replace: true }) }
  const regionLink = (k?: string) => `/monitor${k ? `/region/${encodeURIComponent(k)}` : ''}?ind=${ind.key}`
  const statuses = new Set(rows.map((d) => ind.read(d).status).filter(Boolean))

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow={reg ? pick(lang, reg.name, reg.name_mr) : t('all_mh')} title={t('mon_title')} intro={t('mon_sub')} />

      {/* indicator selector */}
      <div className="mb-3 flex flex-wrap gap-2" role="tablist" aria-label="Indicator">
        {INDICATORS.map((i) => (
          <button key={i.key} role="tab" aria-selected={ind.key === i.key} onClick={() => setInd(i.key)} className={ind.key === i.key ? 'chip-on' : 'chip-off'}>{t(i.label)}</button>
        ))}
      </div>
      {/* region selector */}
      <div className="mb-8 flex flex-wrap gap-2" aria-label={t('region')}>
        <Link to={regionLink()} className={!reg ? 'chip-on' : 'chip-off'}>{t('all_mh')}</Link>
        {REGION_ORDER.map((k) => {
          const r = regions.data?.find((x) => x.key === k)
          return r ? <Link key={k} to={regionLink(k)} className={reg?.key === k ? 'chip-on' : 'chip-off'}>{pick(lang, r.name, r.name_mr)}</Link> : null
        })}
      </div>

      {(ov.isLoading || geo.isLoading) && <Loading />}
      {(ov.error || geo.error) && <ErrorBox error={ov.error || geo.error} onRetry={() => { ov.refetch(); geo.refetch() }} />}

      {ov.data && geo.data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="overflow-hidden rounded-[20px] bg-white">
            <DistrictChoropleth fc={geo.data} colorFor={colorFor} tooltipFor={tooltipFor} focusIds={focusIds} onSelect={(id) => nav(`/monitor/district/${id}`)} height={typeof window !== 'undefined' && window.innerWidth < 640 ? 380 : 560} />
          </div>
          <aside className="space-y-4">
            <div className="card !p-6">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h2 className="font-sans text-[17px] font-semibold tracking-normal">{t(ind.label)}</h2>
                <NatureBadge kind={ind.nature === 'estimate' ? 'estimate' : statuses.has('provisional') ? 'provisional' : 'observed'} />
              </div>
              <p className="mb-5 text-[14px] text-graphite">{t(ind.desc)}</p>
              <Legend bins={ind.bins} />
              {reg?.note && <p className="mt-4 flex gap-1.5 text-[13px] text-pewter"><Info size={14} className="mt-0.5 shrink-0" />{reg.note}</p>}
            </div>
            <div className="rounded-[20px] bg-sage p-6">
              <p className="eyebrow mb-3">{rows.length} {t('districts_ranked').toLowerCase()}</p>
              <ul className="space-y-1.5 text-[14px]">
                {ind.bins.map((b) => counts.get(b.key) ? (
                  <li key={b.key} className="flex items-center gap-2"><Swatch color={b.color} /> <span className="flex-1">{pick(lang, b.label, b.label_mr)}</span> <strong>{counts.get(b.key)}</strong></li>
                ) : null)}
                {counts.get('_none') ? <li className="flex items-center gap-2"><Swatch color="#fff" /> <span className="flex-1">{t('no_data')}</span><strong>{counts.get('_none')}</strong></li> : null}
              </ul>
            </div>
          </aside>
        </div>
      )}

      {ov.data && (
        <section className="mt-10">
          <h2 className="mb-4 text-[28px]">{t('districts_ranked')} <span className="font-sans text-[14px] text-pewter">· {t('sort_worst')}</span></h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((d, i) => {
              const r = ind.read(d)
              return (
                <Reveal as="li" key={d.district_id} delay={Math.min(i, 8) * 45}>
                  <Link to={`/monitor/district/${d.district_id}`} className="lift group flex items-center gap-4 rounded-[20px] bg-white p-5 transition-colors hover:bg-sage">
                    <span className="h-10 w-1.5 shrink-0 rounded-full" style={{ background: r.bin?.color ?? '#efefef' }} aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[16px] font-semibold">{d.district}</p>
                      <p className="text-[13px] text-pewter">{d.region}{d.subregion ? ` · ${d.subregion}` : ''}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[15px] font-medium tabular-nums">{r.display}</p>
                      <BinPill bin={r.bin} />
                    </div>
                    <ArrowRight size={16} className="text-pewter transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </Reveal>
              )
            })}
          </ul>
        </section>
      )}

      <div className="mt-10">
        <MethodNote>
          <p><strong>{t('ind_stress')}</strong>: FAO-56 root-zone water balance started from NASA SMAP soil moisture (2–3 days old), run forward with observed rain and the ECMWF forecast, using MODIS-observed water use. Validated against SMAP 2016–2024: better than "no change" at 7 and 14 days. It is an estimate, not a measurement.</p>
          <p><strong>{t('ind_vhi')}</strong>: Kogan VHI = ½·VCI + ½·TCI from MODIS NDVI and land temperature over cropland, vs a 2015–2024 baseline (short baseline exaggerates extremes).</p>
          <p><strong>{t('ind_spi')}</strong> and <strong>{t('ind_dep')}</strong>: IMD gridded gauge rainfall, 1991–2020 normal. Months after IMD's last release use satellite rain (IMERG) scaled to IMD and are marked provisional.</p>
        </MethodNote>
      </div>
    </Container>
  )
}
