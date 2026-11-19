import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type SoilDistrict, type Region } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { useDistrictGeo } from '../components/Maps'
import { Container, ErrorBox, Loading, MethodNote, NatureBadge, SectionHeader, Stat } from '../components/ui'

const DEPTHS = ['0-5cm', '5-15cm', '15-30cm', '30-60cm', '60-100cm', '100-200cm']
const TABLE_PROPS = ['clay', 'sand', 'silt', 'phh2o', 'soc', 'nitrogen', 'cec', 'bdod', 'cfvo']
const PROP_MR: Record<string, string> = {
  clay: 'चिकणमाती', sand: 'वाळू', silt: 'गाळ', phh2o: 'सामू (pH)', soc: 'सेंद्रिय कर्ब', nitrogen: 'एकूण नत्र',
  cec: 'धनायन विनिमय क्षमता', bdod: 'घनता', cfvo: 'खडे / रेव', ocd: 'सेंद्रिय कर्ब घनता',
}

export default function SoilPage() {
  const { t, lang } = useI18n()
  const { profile } = useProfile()
  const geo = useDistrictGeo()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => api.get<Region[]>('/geo/regions'), staleTime: Infinity })
  const [did, setDid] = useState<number>(profile?.farms[0]?.district_id ?? 26)
  const q = useQuery({ queryKey: ['soil', did], queryFn: () => api.get<SoilDistrict>(`/soil/district/${did}`) })
  const name = (id: number) => geo.data?.features.find((f) => f.properties.district_id === id)?.properties.district ?? ''
  const v = (p: string, d = '0-5cm') => q.data?.properties.find((x) => x.property === p && x.depth === d)

  const card = (p: string, tone: 'sage' | 'sky' | 'peach' | 'ash', digits = 1) => {
    const x = v(p)
    return x ? <Stat tone={tone} label={`${lang === 'mr' ? PROP_MR[p] ?? x.label : x.label} · 0–5 cm`} value={<>{x.mean.toFixed(digits)} <span className="text-[17px]">{x.unit}</span></>}
      sub={`${lang === 'mr' ? 'जिल्ह्यातील श्रेणी' : 'District range'} ${x.p10.toFixed(digits)}–${x.p90.toFixed(digits)} (10–90%)`} /> : null
  }

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow={t('nav_soil')} title={t('soil_title')} intro={t('soil_sub')} action={
        <div className="min-w-[260px]">
          <label className="label" htmlFor="sd">{t('district')}</label>
          <select id="sd" className="field" value={did} onChange={(e) => setDid(Number(e.target.value))}>
            {regions.data?.filter((r) => r.key !== 'Khandesh').map((r) => (
              <optgroup key={r.key} label={pick(lang, r.name, r.name_mr)}>
                {r.district_ids.map((id) => ({ id, n: name(id) })).sort((a, b) => a.n.localeCompare(b.n)).map(({ id, n }) => <option key={id} value={id}>{n}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
      } />

      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <h2 className="text-[37px]">{name(did)}</h2>
            <NatureBadge kind="estimate" />
            <span className="text-[13px] text-pewter">{lang === 'mr' ? 'जागतिक मॉडेल अंदाज (SoilGrids 2.0, २५० मी); प्रयोगशाळा मोजमाप नाही' : q.data.value_type}</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {card('phh2o', 'sage')}
            {card('soc', 'peach')}
            {card('clay', 'sky', 0)}
            {card('cec', 'ash')}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="card overflow-x-auto !p-6">
              <table className="w-full min-w-[640px] text-[14px]">
                <caption className="mb-3 text-left font-semibold">{lang === 'mr' ? 'खोलीनुसार गुणधर्म (जिल्हा सरासरी, शेतजमीन)' : 'Properties by depth (district mean over cropland)'}</caption>
                <thead>
                  <tr className="border-b border-ash text-left text-pewter">
                    <th className="py-2 pr-3 font-medium">{t('depth')}</th>
                    {TABLE_PROPS.map((p) => { const x = v(p); return <th key={p} className="py-2 pr-3 font-medium">{lang === 'mr' ? PROP_MR[p] : x?.label}<br /><span className="text-[12px]">{x?.unit}</span></th> })}
                    <th className="py-2 font-medium">{t('texture')}</th>
                  </tr>
                </thead>
                <tbody>
                  {DEPTHS.map((d) => (
                    <tr key={d} className="border-b border-ash/70 last:border-0">
                      <td className="py-2 pr-3 font-medium">{d.replace('cm', ' cm')}</td>
                      {TABLE_PROPS.map((p) => <td key={p} className="py-2 pr-3 tabular-nums">{v(p, d)?.mean.toFixed(p === 'bdod' || p === 'nitrogen' ? 2 : 1) ?? '–'}</td>)}
                      <td className="py-2">{q.data!.texture.find((x) => x.depth === d)?.texture}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rounded-[20px] bg-forest p-[30px] text-white">
              <h3 className="text-[28px]">{t('water_holding')}</h3>
              <dl className="mt-5 space-y-4">
                <div><dt className="text-[13px] text-white/75">{t('fc')} (0–5 cm)</dt><dd className="font-serif text-[37px] font-light">{q.data.water.field_capacity_topsoil.toFixed(2)} <span className="text-[15px]">m³/m³</span></dd></div>
                <div><dt className="text-[13px] text-white/75">{t('wp')} (0–5 cm)</dt><dd className="font-serif text-[37px] font-light">{q.data.water.wilting_point_topsoil.toFixed(2)} <span className="text-[15px]">m³/m³</span></dd></div>
                <div><dt className="text-[13px] text-white/75">{t('awc')} (0–1 m)</dt><dd className="font-serif text-[37px] font-light">{q.data.water.available_water_mm_per_m} <span className="text-[15px]">mm</span></dd></div>
              </dl>
              <p className="mt-5 text-[13px] text-white/75">{q.data.water.method}</p>
            </div>
          </div>

          <div className="mt-8">
            <MethodNote>
              <p>{q.data.caveat}</p>
              <p>{pick(lang, 'Source: ISRIC SoilGrids 2.0 (CC BY 4.0), 250 m, averaged over cropland pixels in the district. Water holding: Saxton & Rawls (2006) equations from sand, clay and organic matter. A national soil survey (NBSS&LUP) and Soil Health Card data will replace these estimates when available.',
                'स्रोत: ISRIC SoilGrids 2.0, २५० मी. पाणी धारण क्षमता: Saxton & Rawls (2006). NBSS&LUP व मृदा आरोग्य पत्रिका माहिती उपलब्ध झाल्यावर हे अंदाज बदलले जातील.')}</p>
            </MethodNote>
          </div>
        </>
      )}
    </Container>
  )
}
