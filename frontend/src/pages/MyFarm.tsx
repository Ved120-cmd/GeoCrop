import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Droplets, MapPin, Pencil, Trash2, Sprout } from 'lucide-react'
import { api, type CropOption, type FarmNowcast } from '../lib/api'
import { pick, useI18n, type TKey } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { stressBin } from '../lib/scales'
import { ChartCard, DepletionChart, RainBars } from '../components/Charts'
import { BinPill, Container, ErrorBox, Loading, MethodNote, NatureBadge, Stat } from '../components/ui'

export default function MyFarm() {
  const { t, lang } = useI18n()
  const { profile, loading, refresh, setProfileId } = useProfile()
  const qc = useQueryClient()
  const farm = profile?.farms[0]
  const crops = useQuery({ queryKey: ['crops'], queryFn: () => api.get<CropOption[]>('/meta/crops'), staleTime: Infinity })
  const nc = useQuery({ queryKey: ['farm-nowcast', farm?.id, farm?.irrigation?.length], enabled: !!farm?.id,
    queryFn: () => api.get<FarmNowcast>(`/farms/${farm!.id}/nowcast`) })

  const [irDate, setIrDate] = useState(new Date().toISOString().slice(0, 10))
  const [irMm, setIrMm] = useState('')
  const addIrr = useMutation({
    mutationFn: () => api.post(`/farms/${farm!.id}/irrigation`, { date: irDate, amount_mm: Number(irMm) }),
    onSuccess: () => { setIrMm(''); refresh(); qc.invalidateQueries({ queryKey: ['farm-nowcast'] }) },
  })
  const delIrr = useMutation({
    mutationFn: (eid: string) => api.del(`/farms/${farm!.id}/irrigation/${eid}`),
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ['farm-nowcast'] }) },
  })

  if (loading) return <Container><Loading /></Container>
  if (!profile || !farm) {
    return (
      <Container className="py-16">
        <div className="mx-auto max-w-[560px] rounded-[30px] bg-sage p-10 text-center">
          <Sprout className="mx-auto" size={32} strokeWidth={1.5} />
          <h1 className="mt-4 text-[37px]">{t('farm_title')}</h1>
          <p className="mt-3 text-graphite">{t('no_profile')}</p>
          <Link to="/onboarding" className="btn-primary mt-6">{t('create_profile')}</Link>
        </div>
      </Container>
    )
  }

  const cropLabel = (code: string, other?: string | null) => {
    if (code === 'other') return other ?? 'Other'
    const c = crops.data?.find((x) => x.code === code); return c ? pick(lang, c.label, c.label_mr) : code
  }
  const meta = nc.data?.meta as Record<string, unknown> | undefined
  const today = nc.data?.daily?.find((d) => d.date === new Date().toISOString().slice(0, 10))
  const bin = stressBin((meta?.today_stress as string) ?? null)

  return (
    <Container className="py-10 md:py-14">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">{profile.name}</p>
          <h1 className="text-[45px] md:text-[57px]">{farm.name || t('farm_title')}</h1>
          <p className="mt-2 flex items-center gap-1.5 text-[15px] text-graphite">
            <MapPin size={16} /> {[farm.village, farm.taluka, farm.district].filter(Boolean).join(', ')}
            {farm.area_value ? ` · ${farm.area_value} ${t(`unit_${farm.area_unit}` as TKey)}` : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to={`/monitor/district/${farm.district_id}`} className="btn-ghost">{t('view_district')}</Link>
          <Link to="/profile" className="btn-primary"><Pencil size={15} /> {t('edit')}</Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat tone="sage" label={t('irrigation')} value={<span className="text-[28px]">{t(`irr_${farm.irrigation_source}` as TKey)}</span>} />
        <Stat tone="peach" label={t('soil_type')} value={<span className="text-[28px]">{t(`soil_${farm.soil_type_reported}` as TKey)}</span>} />
        <Stat tone="sky" label={t('crops_title')} value={<span className="text-[28px]">{farm.crops.length ? farm.crops.map((c) => cropLabel(c.crop, c.crop_other)).join(', ') : '—'}</span>}
          sub={farm.crops.map((c) => `${t(`s_${c.season}` as TKey)}${c.sowing_date ? ` · ${c.sowing_date}` : ''}`).join(' | ')} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ChartCard title={t('farm_estimate')} subtitle={nc.data?.available
          ? <span className="inline-flex flex-wrap items-center gap-2">{cropLabel(nc.data.crop!)} · {t('sowing_date')} {nc.data.sowing_date} · <NatureBadge kind="estimate" /></span> : undefined}>
          {nc.isLoading ? <Loading /> : nc.error ? <ErrorBox error={nc.error} onRetry={() => nc.refetch()} /> : !nc.data?.available ? (
            <p className="rounded-[20px] bg-ash p-5 text-[15px] text-graphite">{nc.data?.reason}</p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-4">
                <span className="font-serif text-[45px] font-light leading-none">{today?.depletion_pct != null ? `${today.depletion_pct.toFixed(0)}%` : '–'}</span>
                <BinPill bin={bin} />
                <span className="text-[14px] text-graphite">
                  {t('days_until_stress')}: <strong>{meta?.days_until_stress === 0 ? t('stressed_now') : meta?.days_until_stress == null ? t('no_stress_10') : String(meta.days_until_stress)}</strong>
                </span>
              </div>
              <DepletionChart data={nc.data.daily!} threshold={undefined} labels={{ obs: t('observed'), fc: t('forecast'), thr: '' }} />
              <RainBars data={nc.data.daily!.map((d) => ({ date: d.date, rain_mm: (d.rain_mm ?? 0) + (d.irrigation_mm ?? 0) }))} name={lang === 'mr' ? 'पाऊस + सिंचन (मिमी)' : 'Rain + irrigation (mm)'} />
              <p className="mt-3 text-[13px] text-pewter">{String(meta?.irrigation_assumption ?? '')}</p>
            </>
          )}
        </ChartCard>

        <div className="card !p-6">
          <h3 className="flex items-center gap-2 font-sans text-[16px] font-semibold tracking-normal"><Droplets size={18} /> {t('log_irrigation')}</h3>
          <form className="mt-4 grid grid-cols-[1fr_110px] gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(irMm) > 0) addIrr.mutate() }}>
            <div>
              <label className="label" htmlFor="irdate">{t('date')}</label>
              <input id="irdate" type="date" className="field" value={irDate} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setIrDate(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="irmm">{t('amount_mm')}</label>
              <input id="irmm" type="number" min={1} max={300} className="field" value={irMm} onChange={(e) => setIrMm(e.target.value)} />
            </div>
            <button className="btn-primary col-span-2" disabled={!(Number(irMm) > 0) || addIrr.isPending}>{t('add')}</button>
          </form>
          <p className="mt-2 text-[13px] text-pewter">{t('mm_hint')}</p>
          {addIrr.error && <div className="mt-3"><ErrorBox error={addIrr.error} /></div>}
          <h4 className="eyebrow mb-2 mt-6">{t('irr_log')}</h4>
          {farm.irrigation?.length ? (
            <ul className="divide-y divide-ash text-[15px]">
              {[...farm.irrigation].reverse().map((ev) => (
                <li key={ev.id} className="flex items-center justify-between py-2">
                  <span>{ev.date}</span><span className="tabular-nums">{ev.amount_mm} mm</span>
                  <button className="rounded-full p-1.5 text-pewter hover:bg-ash hover:text-ink" onClick={() => delIrr.mutate(ev.id)} aria-label={t('remove')}><Trash2 size={15} /></button>
                </li>
              ))}
            </ul>
          ) : <p className="text-[14px] text-graphite">{t('irr_none')}</p>}
        </div>
      </div>

      <div className="mt-8">
        <MethodNote>
          <p>{pick(lang,
            'Field estimate: FAO-56 water balance for your crop (FAO crop coefficients and growth stages), using your district soil, district rain and evapotranspiration, and your logged irrigation. Growth-stage lengths are FAO-56 values, not yet calibrated for Maharashtra varieties.',
            'शेत अंदाज: तुमच्या पिकासाठी FAO-56 पाणी संतुलन (FAO पीक गुणांक व वाढीचे टप्पे), जिल्ह्यातील माती, पाऊस व बाष्पीभवन आणि तुम्ही नोंदवलेले सिंचन वापरून.')}</p>
        </MethodNote>
        <button className="mt-6 text-[13px] text-pewter underline hover:text-ink" onClick={() => { if (confirm('Forget this profile on this browser?')) setProfileId(null) }}>
          {lang === 'mr' ? 'या ब्राउझरवरून प्रोफाइल विसरा' : 'Forget profile on this browser'}
        </button>
      </div>
    </Container>
  )
}
