import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Home as HomeIcon } from 'lucide-react'
import { api, type NowcastDay, type Overview } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { INDICATORS } from '../lib/indicators'
import { useProfile } from '../lib/profile'
import { DistrictChoropleth, useDistrictGeo } from '../components/Maps'
import { ChartCard, DepletionChart, PercentileChart, RainBars, ThisYearVsNormal } from '../components/Charts'
import { BinPill, Container, ErrorBox, Loading, MethodNote, NatureBadge } from '../components/ui'

interface IndexResp<T> { data: T[] }
const TONES = ['bg-sage', 'bg-sky', 'bg-peach', 'bg-ash', 'bg-sage', 'bg-sky']
const iso = (d: Date) => d.toISOString().slice(0, 10)

export default function DistrictPage() {
  const { id } = useParams()
  const did = Number(id)
  const navigate = useNavigate()
  const { t, lang } = useI18n()
  const { profile } = useProfile()
  const geo = useDistrictGeo()
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/monitor/overview') })
  const d = ov.data?.districts.find((x) => x.district_id === did)

  const year = new Date().getFullYear()
  const today = new Date()
  const veg = useQuery({ queryKey: ['veg', did], queryFn: () => api.get<IndexResp<{ date: string; ndvi: number; ndvi_normal: number; low_confidence: boolean }>>(`/monitor/district/${did}/index/vegetation?start=${year}-01-01`) })
  const sm = useQuery({ queryKey: ['sm', did], queryFn: () => api.get<IndexResp<{ date: string; sm_percentile: number }>>(`/monitor/district/${did}/index/soil_moisture?start=${iso(new Date(today.getTime() - 120 * 864e5))}`) })
  const dep = useQuery({ queryKey: ['dep', did], queryFn: () => api.get<IndexResp<{ date: string; monsoon_cum_mm: number; monsoon_normal_mm: number; status: string }>>(`/monitor/district/${did}/index/monsoon_departure?start=${year}-06-01`) })
  const st = useQuery({ queryKey: ['stress', did], queryFn: () => api.get<{ daily: NowcastDay[] }>(`/monitor/district/${did}/stress-today`) })

  const myFarm = profile?.farms.find((f) => f.district_id === did)
  if (ov.isLoading) return <Container><Loading /></Container>
  if (ov.error) return <Container className="py-10"><ErrorBox error={ov.error} /></Container>
  if (!d) return <Container className="py-10"><ErrorBox error="Unknown district" /></Container>

  const s = d.indicators.stress_today
  const days = st.data?.daily ?? []
  const todayStr = iso(today)
  const depProv = dep.data?.data.some((r) => r.status === 'provisional')

  return (
    <Container className="py-10 md:py-14">
      <Link to="/monitor" className="mb-6 inline-flex items-center gap-1.5 text-[14px] text-graphite hover:text-ink"><ArrowLeft size={16} /> {t('back_to_map')}</Link>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          <p className="eyebrow mb-2">
            <Link to={`/monitor/region/${encodeURIComponent(d.region)}`} className="hover:text-ink">{d.region}</Link>
            {d.subregion ? ` · ${d.subregion}` : ''}
          </p>
          <h1 className="text-[45px] md:text-[57px]">{d.district}</h1>
          {s && (
            <div className="mt-6 flex flex-wrap items-center gap-4 rounded-[20px] bg-white p-6">
              <div>
                <p className="text-[13px] font-medium text-graphite">{t('ind_stress')}</p>
                <div className="mt-1 flex items-center gap-3">
                  <span className="font-serif text-[45px] font-light leading-none">{s.depletion_pct.toFixed(0)}%</span>
                  <BinPill bin={INDICATORS[0].read(d).bin} />
                </div>
                <p className="mt-1 text-[13px] text-pewter">{t('depletion')}</p>
              </div>
              <div className="ml-auto text-[14px]">
                <p className="text-graphite">{t('days_until_stress')}</p>
                <p className="font-serif text-[28px] font-light">{s.days_until_stress === 0 ? t('stressed_now') : s.days_until_stress == null ? t('no_stress_10') : s.days_until_stress}</p>
                <NatureBadge kind="estimate" />
              </div>
            </div>
          )}
          {myFarm && (
            <Link to="/my-farm" className="mt-4 flex items-center gap-3 rounded-[20px] bg-lime p-4 text-[15px] font-medium">
              <HomeIcon size={18} /> {t('my_farm_here')} → {t('open_my_farm')}
            </Link>
          )}
        </div>
        {geo.data && (
          <div className="overflow-hidden rounded-[20px] bg-white">
            <DistrictChoropleth fc={geo.data} height={300} selectedId={did}
              colorFor={(x) => (x === did ? '#07503f' : '#e6ecd5')} tooltipFor={(_, n) => n} onSelect={(x) => x !== did && navigate(`/monitor/district/${x}`)} />
          </div>
        )}
      </div>

      {/* status quilt */}
      <h2 className="mb-4 mt-12 text-[28px]">{t('status_now')}</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {INDICATORS.map((ind, i) => {
          const r = ind.read(d)
          return (
            <Link key={ind.key} to={`/monitor?ind=${ind.key}`} className={`rounded-[20px] ${TONES[i]} p-6 transition-opacity hover:opacity-90`}>
              <div className="flex items-start justify-between gap-2">
                <p className="text-[14px] font-semibold">{t(ind.label)}</p>
                <NatureBadge kind={ind.nature === 'estimate' ? 'estimate' : r.status === 'provisional' ? 'provisional' : 'observed'} />
              </div>
              <p className="mt-3 font-serif text-[37px] font-light leading-none">{r.display}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-graphite">
                <BinPill bin={r.bin} /> {r.asOf && <span>{t('as_of')} {r.asOf}</span>}
              </div>
            </Link>
          )
        })}
      </div>

      {/* charts */}
      <h2 className="mb-4 mt-12 text-[28px]">{t('trends')}</h2>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title={t('next_10')} subtitle={<span className="inline-flex items-center gap-2">{t('depletion')} · <NatureBadge kind="estimate" /></span>}
          footer={days.length ? `${t('as_of')} ${todayStr}. ${lang === 'mr' ? 'घन रेषा: निरीक्षित हवामान; तुटक: पूर्वानुमान.' : 'Solid: observed weather; dashed: ECMWF forecast.'}` : undefined}>
          {st.isLoading ? <Loading /> : st.error ? <ErrorBox error={st.error} /> : (
            <>
              <DepletionChart data={days} threshold={50} labels={{ obs: t('observed'), fc: t('forecast'), thr: lang === 'mr' ? 'ताण सुरू (≈५०%)' : 'stress begins (≈50%)' }} />
              <RainBars data={days} name={lang === 'mr' ? 'पाऊस (मिमी)' : 'Rain (mm)'} />
            </>
          )}
        </ChartCard>
        <ChartCard title={t('ndvi_vs_normal')} subtitle={`MODIS MOD13Q1 · ${lang === 'mr' ? 'शेतजमीन' : 'cropland'} · ${year}`}>
          {veg.isLoading ? <Loading /> : veg.error ? <ErrorBox error={veg.error} /> :
            <ThisYearVsNormal data={veg.data!.data} x="date" y="ndvi" yNormal="ndvi_normal" labels={[t('this_year'), t('normal')]} yDomain={[0, 0.9]} />}
        </ChartCard>
        <ChartCard title={t('sm_trend')} subtitle="NASA SMAP L4 · root zone">
          {sm.isLoading ? <Loading /> : sm.error ? <ErrorBox error={sm.error} /> : <PercentileChart data={sm.data!.data} x="date" y="sm_percentile" name={t('ind_sm')} />}
        </ChartCard>
        <ChartCard title={t('rain_vs_normal')} subtitle={<span className="inline-flex items-center gap-2">IMD 1991–2020 normal {depProv && <NatureBadge kind="provisional" />}</span>}>
          {dep.isLoading ? <Loading /> : dep.error ? <ErrorBox error={dep.error} /> : dep.data!.data.length === 0
            ? <p className="py-10 text-center text-pewter">{t('no_data')}</p>
            : <ThisYearVsNormal data={dep.data!.data} x="date" y="monsoon_cum_mm" yNormal="monsoon_normal_mm" labels={[t('this_year'), t('normal')]} unit=" mm" />}
        </ChartCard>
      </div>

      <div className="mt-8">
        <MethodNote>
          <p>{lang === 'mr'
            ? 'जिल्हा मूल्ये ही शेतजमिनीवरील उपग्रह पिक्सेलची सरासरी आहेत. आजचा ताण हा मॉडेल अंदाज आहे (मोजमाप नाही).'
            : 'District values average the satellite pixels over cropland (MODIS land cover). Today\'s stress is a model estimate (not a measurement), started from SMAP 2–3 days ago. Fields vary within a district; irrigated fields are wetter than the district average.'}</p>
          <p>{pick(lang, 'Soil-moisture percentiles compare with 2015–2024 for the same time of year; NDVI "normal" is the 2015–2024 average for the same 16-day period.', 'मातीतील ओलावा व NDVI ची तुलना २०१५–२०२४ मधील त्याच कालावधीशी केली जाते.')}</p>
        </MethodNote>
      </div>
    </Container>
  )
}
