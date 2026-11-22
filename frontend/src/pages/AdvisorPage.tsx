import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BookOpen, Droplets, FlaskConical, Sprout, TriangleAlert } from 'lucide-react'
import { api, type Region } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { DRY } from '../lib/scales'
import { useDistrictGeo } from '../components/Maps'
import { Container, ErrorBox, Loading, MethodNote, SectionHeader } from '../components/ui'
import { GrowBar, Reveal } from '../components/motion'

interface Rec {
  rank: number; crop: string; crop_mr: string; yield_type: string; suitability_class: 'S1' | 'S2' | 'S3' | 'N'; suitability: string; suitability_mr: string
  relative_yield: number; best_sow: string; median_by_sow_date: Record<string, number>; median_t_ha: number; p10_t_ha: number
  median_q_acre: number; p10_q_acre: number; poor_season_share: number; irrigation_mm: number; rain_mm: number; n_seasons: number
  yearly: { year: number; yield_t_ha: number; irrigation_mm: number; failed: boolean }[]; ipm_package: string | null; rainfed_median_t_ha?: number
  best_is_latest_tested: boolean; best_is_earliest_tested: boolean; share_of_irrigated_potential?: number; model_note?: string; model_note_mr?: string
  phenology: { simulated_days: number; fao56_days: number; ratio: number; plausible: boolean } | null
}
interface Resp {
  district: string; season: string; water: string; recommendations: Rec[]; warnings: { en: string; mr: string }[]; not_ranked: { crop: string; reason: string }[]; method: string; caveats: string[]; value_type: string
  context: { soil_moisture?: { as_of: string; percentile: number }; dry_risk?: { lead_days: number; valid_date: string; prob_dry: number; dry_risk: string }[] }
}

const CLASS_STYLE: Record<Rec['suitability_class'], string> = { S1: 'bg-forest text-white', S2: 'bg-sage text-ink', S3: 'bg-peach text-ink', N: 'bg-ash text-ink' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_MR = ['जाने', 'फेब्रु', 'मार्च', 'एप्रि', 'मे', 'जून', 'जुलै', 'ऑग', 'सप्टें', 'ऑक्टो', 'नोव्हें', 'डिसें']
const fmtSow = (s: string, lang: 'en' | 'mr') => { const [m, d] = s.split('-').map(Number); return `${d} ${(lang === 'mr' ? MONTHS_MR : MONTHS)[m - 1]}` }
const cropName = (c: string) => c.replace(/^./, (m) => m.toUpperCase())
const ordinal = (n: number) => { const v = n % 100; return `${n}${v >= 11 && v <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}` }

function CropCard({ r, water }: { r: Rec; water: string }) {
  const { lang } = useI18n()
  const sows = Object.entries(r.median_by_sow_date).sort()
  const maxSow = Math.max(...sows.map(([, v]) => v), 0.01)
  const fresh = r.yield_type?.startsWith('fresh')
  return (
    <Reveal as="li" className="card !p-6">
      <div className="flex flex-wrap items-start gap-3">
        <span className="font-serif text-[34px] font-light leading-none text-pewter">{r.rank}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[22px] font-medium">{pick(lang, cropName(r.crop), r.crop_mr)}</p>
          <p className="text-[13px] text-pewter">{r.yield_type}</p>
        </div>
        <span className={`badge ${CLASS_STYLE[r.suitability_class]}`}>{r.suitability_class} · {pick(lang, r.suitability, r.suitability_mr)}</span>
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-4 text-[14px] sm:grid-cols-4">
        <div><dt className="text-pewter">{pick(lang, 'Typical yield', 'सामान्य उत्पादन')}</dt><dd className="text-[18px] font-medium tabular-nums">{r.median_q_acre} <span className="text-[13px] font-normal">q/acre</span></dd></div>
        <div><dt className="text-pewter">{pick(lang, 'Bad year (1 in 10)', 'वाईट वर्ष (१० पैकी १)')}</dt><dd className="text-[18px] font-medium tabular-nums">{r.p10_q_acre} <span className="text-[13px] font-normal">q/acre</span></dd></div>
        <div><dt className="text-pewter">{pick(lang, 'Poor seasons', 'खराब हंगाम')}</dt><dd className="text-[18px] font-medium tabular-nums">{Math.round(r.poor_season_share * 100)}%</dd></div>
        <div><dt className="text-pewter">{water === 'irrigated' ? pick(lang, 'Irrigation needed', 'लागणारे सिंचन') : pick(lang, 'Season rain', 'हंगामातील पाऊस')}</dt>
          <dd className="text-[18px] font-medium tabular-nums">{water === 'irrigated' ? r.irrigation_mm : r.rain_mm} <span className="text-[13px] font-normal">mm</span></dd></div>
      </dl>
      {r.share_of_irrigated_potential !== undefined && (
        <p className="mt-3 text-[13px] text-graphite">{pick(lang, `Without irrigation it reaches ${Math.round(r.share_of_irrigated_potential * 100)}% of what irrigated ${cropName(r.crop).toLowerCase()} reaches in the best districts.`, `सिंचनाशिवाय सर्वोत्तम सिंचित उत्पादनाच्या ${Math.round(r.share_of_irrigated_potential * 100)}%.`)}</p>
      )}
      {r.rainfed_median_t_ha !== undefined && (
        <p className="mt-3 text-[13px] text-graphite">{pick(lang, `Without irrigation: ${(r.rainfed_median_t_ha * 4.047).toFixed(1)} q/acre typical.`, `सिंचनाशिवाय: ${(r.rainfed_median_t_ha * 4.047).toFixed(1)} क्विं/एकर.`)}</p>
      )}
      <div className="mt-5 grid gap-5 md:grid-cols-[1fr_1.4fr]">
        <div>
          <p className="text-[13px] font-semibold">{pick(lang, 'Sowing date', 'पेरणी तारीख')}</p>
          <ul className="mt-2 space-y-1.5">
            {sows.map(([s, v]) => (
              <li key={s} className="flex items-center gap-2 text-[13px]">
                <span className="w-14 shrink-0">{fmtSow(s, lang)}</span>
                <GrowBar className="flex-1" pct={(100 * v) / maxSow} color={s === r.best_sow ? 'var(--color-forest)' : '#9aa79c'} />
                <span className="w-16 text-right tabular-nums">{(v * 4.047).toFixed(1)} q</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12px] text-pewter">{pick(lang, `Best tested: ${fmtSow(r.best_sow, lang)}`, `सर्वोत्तम: ${fmtSow(r.best_sow, lang)}`)}
            {(r.best_is_latest_tested || r.best_is_earliest_tested) && pick(lang, ` (the ${r.best_is_latest_tested ? 'latest' : 'earliest'} date tested; ${r.best_is_latest_tested ? 'later' : 'earlier'} dates were not simulated)`, ' (तपासलेल्या कालावधीच्या टोकाला)')}</p>
        </div>
        <div>
          <p className="text-[13px] font-semibold">{pick(lang, `Each past season (${r.n_seasons}), sown ${fmtSow(r.best_sow, lang)}`, `मागील प्रत्येक हंगाम (${r.n_seasons})`)}</p>
          <ResponsiveContainer width="100%" height={110}>
            <BarChart data={r.yearly.map((y) => ({ year: y.year, q: +(y.yield_t_ha * 4.047).toFixed(1) }))} margin={{ top: 6, right: 0, left: -28, bottom: 0 }}>
              <XAxis dataKey="year" tick={{ fill: '#6d6d6d', fontSize: 11 }} tickLine={false} stroke="#c3c2b7" interval={1} />
              <YAxis tick={{ fill: '#6d6d6d', fontSize: 11 }} tickLine={false} stroke="#c3c2b7" />
              <ReferenceLine y={r.median_q_acre / 2} stroke={DRY[2]} strokeDasharray="3 3" />
              <Tooltip contentStyle={{ background: '#212529', border: 0, borderRadius: 12, color: '#fff', fontSize: 12 }} labelStyle={{ color: '#e8fe85' }} itemStyle={{ color: '#fff' }}
                formatter={(v: number) => [`${v} q/acre`, pick(lang, 'attainable yield', 'संभाव्य उत्पादन')]} />
              <Bar dataKey="q" radius={3} maxBarSize={16}>
                {r.yearly.map((y, i) => <Cell key={i} fill={y.yield_t_ha * 4.047 < r.median_q_acre / 2 ? DRY[1] : '#07503f'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-[12px] text-pewter">{pick(lang, 'Orange bars: poor seasons (below half the typical yield, dashed line).', 'नारिंगी: खराब हंगाम.')}</p>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {r.ipm_package && <a className="btn-ghost !py-2" href={`/api/advisor/ipm/${r.crop}`} target="_blank" rel="noreferrer"><BookOpen size={15} /> {pick(lang, 'Official pest management guide (NIPHM)', 'अधिकृत कीड व्यवस्थापन मार्गदर्शिका')}</a>}
        <Link className="btn-ghost !py-2" to="/simulator"><FlaskConical size={15} /> {pick(lang, 'Try your own plan in the simulator', 'सिम्युलेटरमध्ये तुमची योजना तपासा')}</Link>
      </div>
      {(r.model_note || (r.phenology && !r.phenology.plausible)) && (
        <p className="mt-4 flex gap-2 rounded-[12px] bg-peach/60 p-3 text-[13px] text-graphite"><TriangleAlert size={15} className="mt-0.5 shrink-0" />
          <span>{r.model_note && pick(lang, r.model_note, r.model_note_mr ?? r.model_note)}
            {r.phenology && !r.phenology.plausible && pick(lang, ` Simulated season: ${r.phenology.simulated_days} days vs ${r.phenology.fao56_days} days in FAO-56 Table 11.`, ` सिम्युलेटेड हंगाम ${r.phenology.simulated_days} दिवस; FAO-56: ${r.phenology.fao56_days} दिवस.`)}</span></p>)}
      {fresh && <p className="mt-3 text-[12px] text-pewter">{pick(lang, 'Fresh-weight yield: not comparable in quintals with grain crops; compare the suitability class instead.', 'ताज्या वजनाचे उत्पादन: धान्य पिकांशी तुलना वर्गाने करा.')}</p>}
    </Reveal>
  )
}

export default function AdvisorPage() {
  const { lang, t } = useI18n()
  const { profile } = useProfile()
  const geo = useDistrictGeo()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => api.get<Region[]>('/geo/regions'), staleTime: Infinity })
  const farm = profile?.farms[0]
  const [district, setDistrict] = useState<number>(farm?.district_id ?? 26)
  const [season, setSeason] = useState<'kharif' | 'rabi'>(() => { const m = new Date().getMonth() + 1; return m >= 9 || m <= 2 ? 'rabi' : 'kharif' })
  const [water, setWater] = useState<'rainfed' | 'irrigated'>(farm && farm.irrigation_source !== 'rainfed' ? 'irrigated' : 'rainfed')
  useEffect(() => { if (farm) { setDistrict(farm.district_id); setWater(farm.irrigation_source === 'rainfed' ? 'rainfed' : 'irrigated') } }, [farm])
  const q = useQuery({ queryKey: ['advisor', district, season, water], queryFn: () => api.get<Resp>(`/advisor/district/${district}?season=${season}&water=${water}`) })
  const name = (id: number) => geo.data?.features.find((f) => f.properties.district_id === id)?.properties.district ?? ''
  const recs = q.data?.recommendations ?? []
  const top = useMemo(() => recs.filter((r) => r.suitability_class === 'S1' || r.suitability_class === 'S2'), [recs])
  const ctx = q.data?.context

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow={t('nav_advisor')} title={pick(lang, 'Which crop suits this district?', 'या जिल्ह्यासाठी कोणते पीक योग्य?')}
        intro={pick(lang, 'Crops are compared by how they would have done in each of the last ~10 seasons here, simulated with FAO AquaCrop on this district’s real weather and soil.',
          'मागील ~१० हंगामांतील या जिल्ह्याच्या प्रत्यक्ष हवामान व मातीवर FAO AquaCrop ने केलेल्या सिम्युलेशनवरून पिकांची तुलना.')} />
      <div className="card mb-8 grid gap-5 md:grid-cols-3">
        <div>
          <label className="label" htmlFor="ad">{pick(lang, 'District', 'जिल्हा')}</label>
          <select id="ad" className="field" value={district} onChange={(e) => setDistrict(Number(e.target.value))}>
            {regions.data?.filter((r) => r.key !== 'Khandesh').map((r) => (
              <optgroup key={r.key} label={pick(lang, r.name, r.name_mr)}>
                {r.district_ids.map((id) => ({ id, n: name(id) })).sort((a, b) => a.n.localeCompare(b.n)).map(({ id, n }) => <option key={id} value={id}>{n}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        <fieldset>
          <legend className="label">{pick(lang, 'Season', 'हंगाम')}</legend>
          <div className="flex gap-2">
            {(['kharif', 'rabi'] as const).map((s) => <button key={s} className={season === s ? 'chip-on' : 'chip-off'} aria-pressed={season === s} onClick={() => setSeason(s)}>{s === 'kharif' ? pick(lang, 'Kharif (monsoon)', 'खरीप') : pick(lang, 'Rabi (winter)', 'रब्बी')}</button>)}
          </div>
        </fieldset>
        <fieldset>
          <legend className="label">{pick(lang, 'Water', 'पाणी')}</legend>
          <div className="flex gap-2">
            {(['rainfed', 'irrigated'] as const).map((w) => <button key={w} className={water === w ? 'chip-on' : 'chip-off'} aria-pressed={water === w} onClick={() => setWater(w)}>{w === 'rainfed' ? pick(lang, 'Rain only', 'फक्त पाऊस') : pick(lang, 'Can irrigate', 'सिंचन शक्य')}</button>)}
          </div>
        </fieldset>
      </div>

      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div>
            {(q.data.warnings ?? []).map((w) => (
              <p key={w.en} className="mb-4 flex gap-2 rounded-[12px] bg-peach p-4 text-[14px]"><TriangleAlert size={18} className="shrink-0" />{pick(lang, w.en, w.mr)}</p>
            ))}
            <p className="mb-4 text-[15px]">
              {top.length
                ? pick(lang, `In ${q.data.district}, ${top.map((r) => cropName(r.crop)).join(', ')} ${top.length > 1 ? 'do' : 'does'} best here compared with other districts growing ${top.length > 1 ? 'them' : 'it'} ${water === 'rainfed' ? 'on rain alone' : 'with irrigation'} in ${season}.`,
                  `${q.data.district} मध्ये ${top.map((r) => r.crop_mr).join(', ')} इतर जिल्ह्यांच्या तुलनेत चांगले.`)
                : pick(lang, `None of the simulated crops does well here for ${season} ${water === 'rainfed' ? 'on rain alone' : ''}.`, 'येथे कोणतेही सिम्युलेट केलेले पीक चांगले येत नाही.')}
            </p>
            {water === 'rainfed' && recs.length > 0 && recs.every((r) => (r.share_of_irrigated_potential ?? 1) < 0.4) && (
              <p className="mb-4 flex gap-2 rounded-[12px] bg-peach p-4 text-[14px]"><TriangleAlert size={18} className="shrink-0" />
                {pick(lang, `On rain alone, every crop here reaches less than 40% of what it yields with irrigation in the best districts. ${season === 'rabi' ? 'Rabi on rain alone depends on moisture stored after the monsoon, so sow early and expect low yields in dry years.' : ''}`,
                  'फक्त पावसावर प्रत्येक पीक सिंचित उत्पादनाच्या ४०% पेक्षा कमी देते.')}</p>
            )}
            <ul className="space-y-4">{recs.map((r) => <CropCard key={r.crop} r={r} water={water} />)}</ul>
            {(q.data.not_ranked ?? []).length > 0 && <p className="mt-4 text-[13px] text-graphite">{pick(lang, `Not ranked here: ${q.data.not_ranked.map((x) => `${cropName(x.crop)} (${x.reason})`).join('; ')}. Choose "Can irrigate" to compare them.`, `येथे क्रमवारीत नाही: ${q.data.not_ranked.map((x) => x.crop).join(', ')} (रब्बीत सिंचनानेच घेतले जाते).`)}</p>}
          </div>
          <aside className="space-y-4">
            {ctx && (ctx.soil_moisture || ctx.dry_risk) && (
              <div className="rounded-[20px] bg-sky p-6 text-[14px]">
                <p className="flex items-center gap-2 font-semibold"><Droplets size={17} /> {pick(lang, 'This season so far', 'या हंगामात आतापर्यंत')}</p>
                {ctx.soil_moisture && <p className="mt-3">{pick(lang, `Root-zone soil moisture: ${ordinal(Math.round(ctx.soil_moisture.percentile))} percentile for the time of year (${ctx.soil_moisture.as_of}).`, `मुळांच्या भागातील ओलावा: ${ctx.soil_moisture.percentile.toFixed(0)} पर्सेंटाइल (${ctx.soil_moisture.as_of}).`)}</p>}
                {ctx.dry_risk?.map((d) => <p key={d.lead_days} className="mt-2">{pick(lang, `Chance of dry soil in ${d.lead_days} days: ${Math.round(d.prob_dry * 100)}%`, `${d.lead_days} दिवसांत कोरड्या मातीची शक्यता: ${Math.round(d.prob_dry * 100)}%`)}</p>)}
                <p className="mt-3 text-[12px] text-graphite">{pick(lang, 'Dry soil now makes rainfed sowing riskier than the long-term ranking suggests.', 'सध्या कोरडी माती असल्यास पावसावरील पेरणी अधिक जोखमीची.')} <Link to="/predict" className="underline">{pick(lang, 'Forecast', 'अंदाज')}</Link></p>
              </div>
            )}
            <div className="rounded-[20px] bg-forest p-6 text-[14px] text-white">
              <p className="flex items-center gap-2 font-semibold"><Sprout size={17} /> {pick(lang, 'How to read this', 'हे कसे वाचावे')}</p>
              <ul className="mt-3 space-y-2 text-white/90">
                <li>{pick(lang, 'Within a class, crops with better bad-year (1 in 10) yields are listed first.', 'एकाच वर्गात, वाईट वर्षी चांगले उत्पादन देणारी पिके आधी.')}</li>
                <li>{pick(lang, 'S1–N compares this district with the best districts growing the same crop the same way, rain-fed or irrigated (FAO suitability classes).', 'S1–N: याच पिकासाठी सर्वोत्तम जिल्ह्यांशी तुलना (FAO वर्ग).')}</li>
                <li>{pick(lang, 'Yields are what good management could reach (no pests, enough fertiliser). Real farm yields are usually lower; use them to compare crops.', 'उत्पादन चांगल्या व्यवस्थापनात शक्य असलेले; प्रत्यक्ष उत्पादन सहसा कमी.')}</li>
                <li className="flex gap-2 text-lime"><TriangleAlert size={15} className="mt-0.5 shrink-0" />{pick(lang, 'Prices, costs and pulses (tur, gram), onion, sugarcane, rice are not included yet. Discuss your choice with your KVK.', 'बाजारभाव, खर्च व तूर, हरभरा, कांदा, ऊस, भात अजून समाविष्ट नाहीत.')}</li>
              </ul>
            </div>
          </aside>
        </div>
      )}
      {q.data && <div className="mt-10"><MethodNote>
        <p>{q.data.method}</p>
        <p>{pick(lang, 'Crop parameters are FAO AquaCrop defaults, calibrated outside Maharashtra (soybean at Patancheru, India). Soil is the district average from SoilGrids; weather is district-average IMD/IMERG rain and NASA POWER. "Can irrigate" means water is applied whenever the crop needs it, with no limit on supply.',
          'पीक मापदंड FAO AquaCrop मानक; महाराष्ट्रासाठी अजून कॅलिब्रेट केलेले नाहीत.')}</p>
      </MethodNote></div>}
    </Container>
  )
}
