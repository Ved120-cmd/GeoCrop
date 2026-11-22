import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, ArrowRight, ShieldCheck, TriangleAlert } from 'lucide-react'
import { api } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { DRY, OK, WET, type Bin } from '../lib/scales'
import { DistrictChoropleth, useDistrictGeo } from '../components/Maps'
import { ChartCard, FOREST, NORMAL } from '../components/Charts'
import { BinPill, Container, ErrorBox, Legend as MapLegend, Loading, MethodNote, SectionHeader } from '../components/ui'
import { Reveal, Tilt } from '../components/motion'

interface Fc { district_id: number; district?: string; lead_days: number; issue_date: string; valid_date: string; sm_pct_now: number | null
  sm_pct_median: number; sm_pct_p10: number; sm_pct_p90: number; prob_dry: number; dry_risk: 'low' | 'possible' | 'elevated' | 'high' }
interface Skill { mae: number; mae_persistence: number; skill_vs_persistence: number; interval_coverage: number; dry_brier_skill: number; dry_auc: number; dry_precision: number; dry_recall: number; worse_than_persistence_in_2026: boolean }
interface Overview { value_type: string; lead_days: number; issue_date: string; valid_date: string; skill: { trained_at: string; lead16: Skill; lead32: Skill }; districts: Fc[] }
interface Driver { feature: string; label: string; label_mr: string; value: number | null; effect: number }
interface DistrictResp { district: string; forecasts: Fc[]; drivers: Record<string, { baseline: number; explains: string; drivers: Driver[] } | null>; history: { date: string; sm_percentile: number }[]; skill: Overview['skill'] }

// Ordinal dry-risk classes reuse the validated dry ramp (sage = low). Always shown with text labels.
const RISK_BINS: Bin[] = [
  { key: 'low', color: OK, label: 'Low (< 15%)', label_mr: 'कमी (< १५%)', textDark: true },
  { key: 'possible', color: DRY[0], label: 'Possible (15–30%)', label_mr: 'शक्य (१५–३०%)', textDark: true },
  { key: 'elevated', color: DRY[1], label: 'Elevated (30–60%)', label_mr: 'वाढलेला (३०–६०%)', textDark: false },
  { key: 'high', color: DRY[2], label: 'High (≥ 60%)', label_mr: 'जास्त (≥ ६०%)', textDark: false },
]
const riskBin = (k?: string) => RISK_BINS.find((b) => b.key === k) ?? null
const AXIS = { stroke: '#c3c2b7', tick: { fill: '#6d6d6d', fontSize: 12 }, tickLine: false }
const TT = { contentStyle: { background: '#212529', border: 0, borderRadius: 12, color: '#fff', fontSize: 13 }, labelStyle: { color: '#e8fe85' }, itemStyle: { color: '#fff' } }
const fmtD = (s: string) => new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

const T = {
  title: ['Dry-soil early warning', 'कोरड्या मातीचा पूर्वइशारा'],
  intro: ['Chance that root-zone soil moisture will be in the driest 20% for the time of year, 16 or 32 days from now, for each district. Built from satellites, rain and weather up to today.',
    'पुढील १६ किंवा ३२ दिवसांत मुळांच्या भागातील ओलावा वर्षाच्या या वेळेसाठी सर्वात कोरड्या २०% मध्ये असण्याची शक्यता.'],
  lead: ['Look ahead', 'पुढे'], days: ['days', 'दिवस'], issued: ['Issued', 'जारी'], for: ['for', 'साठी'],
  reliable: ['How reliable is this?', 'हे किती विश्वासार्ह आहे?'], dryChance: ['Chance of dry soil', 'कोरड्या मातीची शक्यता'],
  likely: ['Expected soil moisture', 'अपेक्षित ओलावा'], range: ['likely range', 'संभाव्य श्रेणी'], now: ['now', 'आता'],
  drivers: ['What drives this forecast', 'या अंदाजामागील घटक'], drier: ['pushes drier', 'कोरडेपणाकडे'], wetter: ['pushes wetter', 'ओलाव्याकडे'],
  history: ['Soil moisture: past 120 days and forecast', 'मातीतील ओलावा: मागील १२० दिवस व अंदाज'],
}
const tt = (lang: 'en' | 'mr', k: keyof typeof T) => (lang === 'mr' ? T[k][1] : T[k][0])

function ReliabilityCard({ s, lead }: { s: Skill; lead: number }) {
  const { lang } = useI18n()
  const pct = (x: number) => `${Math.round(x * 100)}%`
  return (
    <div className="rounded-[20px] bg-forest p-6 text-white">
      <p className="flex items-center gap-2 text-[15px] font-semibold"><ShieldCheck size={18} /> {tt(lang, 'reliable')} · {lead} {tt(lang, 'days')}</p>
      <ul className="mt-4 space-y-3 text-[14px] text-white/90">
        <li>{pick(lang,
          `When it says dry risk is high, soil was dry ${pct(s.dry_precision)} of the time in 2024–2026 tests. It caught ${pct(s.dry_recall)} of dry spells, so some dry spells come without a warning.`,
          `"जास्त धोका" सांगितल्यावर २०२४–२६ चाचण्यांत ${pct(s.dry_precision)} वेळा माती कोरडी होती. ${pct(s.dry_recall)} कोरडे कालावधी ओळखले.`)}</li>
        <li>{pick(lang,
          `Its dry-risk percentages are ${pct(s.dry_brier_skill)} more accurate than using normal-year odds.`,
          `सरासरी शक्यतेपेक्षा ${pct(s.dry_brier_skill)} अधिक अचूक.`)}</li>
        <li>{pick(lang,
          `The exact soil-moisture value is only ${pct(s.skill_vs_persistence)} better than assuming “no change”. Treat it as a rough guide; the likely range held ${pct(s.interval_coverage)} of the time.`,
          `नेमके मूल्य "बदल नाही" मानण्यापेक्षा फक्त ${pct(s.skill_vs_persistence)} चांगले. श्रेणी ${pct(s.interval_coverage)} वेळा बरोबर.`)}</li>
        {s.worse_than_persistence_in_2026 && <li className="flex gap-2 text-lime"><TriangleAlert size={16} className="mt-0.5 shrink-0" />{pick(lang,
          'In the long 2026 drought it expected some recovery that did not come; it did no better than assuming no change.',
          '२०२६ च्या दीर्घ दुष्काळात त्याने अपेक्षित केलेली सुधारणा झाली नाही.')}</li>}
      </ul>
    </div>
  )
}

export default function PredictPage() {
  const { id } = useParams()
  return id ? <PredictDistrict did={Number(id)} /> : <PredictOverview />
}

function PredictOverview() {
  const { lang, t } = useI18n()
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const lead = sp.get('lead') === '32' ? 32 : 16
  const geo = useDistrictGeo()
  const q = useQuery({ queryKey: ['predict', lead], queryFn: () => api.get<Overview>(`/predict/overview?lead=${lead}`) })
  const byId = useMemo(() => new Map(q.data?.districts.map((d) => [d.district_id, d]) ?? []), [q.data])
  const rows = useMemo(() => [...(q.data?.districts ?? [])].sort((a, b) => b.prob_dry - a.prob_dry), [q.data])

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow={t('nav_predict')} title={tt(lang, 'title')} intro={tt(lang, 'intro')} />
      <div className="mb-8 flex flex-wrap items-center gap-2">
        <span className="text-[14px] text-graphite">{tt(lang, 'lead')}:</span>
        {[16, 32].map((L) => (
          <button key={L} className={lead === L ? 'chip-on' : 'chip-off'} aria-pressed={lead === L} onClick={() => { sp.set('lead', String(L)); setSp(sp, { replace: true }) }}>{L} {tt(lang, 'days')}</button>
        ))}
        {q.data && <span className="badge ml-2 bg-sage text-ink">{tt(lang, 'issued')} {q.data.issue_date} · {tt(lang, 'for')} {q.data.valid_date}</span>}
      </div>
      {(q.isLoading || geo.isLoading) && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data && geo.data && (
        <>
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="overflow-hidden rounded-[20px] bg-white">
              <DistrictChoropleth fc={geo.data} height={typeof window !== 'undefined' && window.innerWidth < 640 ? 380 : 540}
                colorFor={(id) => riskBin(byId.get(id)?.dry_risk)?.color ?? '#fff'}
                tooltipFor={(id, n) => { const d = byId.get(id); return d ? `<strong>${n}</strong><br/>${tt(lang, 'dryChance')}: ${Math.round(d.prob_dry * 100)}%<br/>${tt(lang, 'likely')}: ${d.sm_pct_median.toFixed(0)}th pct (${d.sm_pct_p10.toFixed(0)}–${d.sm_pct_p90.toFixed(0)})` : n }}
                onSelect={(id) => nav(`/predict/district/${id}?lead=${lead}`)} />
            </div>
            <aside className="space-y-4">
              <div className="card !p-6"><MapLegend bins={RISK_BINS} title={tt(lang, 'dryChance')} /></div>
              <ReliabilityCard s={q.data.skill[`lead${lead}` as 'lead16' | 'lead32']} lead={lead} />
            </aside>
          </div>
          <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((d, i) => (
              <Reveal as="li" key={d.district_id} delay={Math.min(i, 8) * 45}>
                <Link to={`/predict/district/${d.district_id}?lead=${lead}`} className="lift group flex items-center gap-4 rounded-[20px] bg-white p-5 transition-colors hover:bg-sage">
                  <span className="h-10 w-1.5 shrink-0 rounded-full" style={{ background: riskBin(d.dry_risk)?.color }} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{d.district}</p>
                    <p className="text-[13px] text-pewter">{tt(lang, 'likely')}: {d.sm_pct_median.toFixed(0)}th pct</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[15px] font-medium tabular-nums">{Math.round(d.prob_dry * 100)}%</p>
                    <BinPill bin={riskBin(d.dry_risk)} />
                  </div>
                  <ArrowRight size={16} className="text-pewter transition-transform group-hover:translate-x-0.5" />
                </Link>
              </Reveal>
            ))}
          </ul>
          <div className="mt-10"><MethodNote>
            <p>{pick(lang, `${q.data.value_type}.`, 'हा एका प्रॉक्सीचा अंदाज आहे: SMAP उपग्रह-मॉडेल मातीतील ओलावा, प्रत्यक्ष पीक ताण नाही.')}</p>
            <p>{pick(lang, 'LightGBM models trained on 2015–2023 and tested on 2024–2026 (never seen in training). Each input uses only data that was actually published by the issue date. No weather forecasts are used yet, so heavy rain in the coming weeks cannot be anticipated. Full details: models/water_stress/model_card.md.',
              'LightGBM मॉडेल्स २०१५–२०२३ वर प्रशिक्षित व २०२४–२०२६ वर तपासलेली. हवामान पूर्वानुमान अजून वापरलेले नाही.')}</p>
          </MethodNote></div>
        </>
      )}
    </Container>
  )
}

function PredictDistrict({ did }: { did: number }) {
  const { lang } = useI18n()
  const [sp] = useSearchParams()
  const lead = sp.get('lead') === '32' ? '32' : '16'
  const q = useQuery({ queryKey: ['predict-d', did], queryFn: () => api.get<DistrictResp>(`/predict/district/${did}`) })
  if (q.isLoading) return <Container><Loading /></Container>
  if (q.error || !q.data) return <Container className="py-10"><ErrorBox error={q.error ?? 'no data'} /></Container>
  const d = q.data
  const f16 = d.forecasts.find((f) => f.lead_days === 16)!, f32 = d.forecasts.find((f) => f.lead_days === 32)!
  // history + forecast band: median line, p10-p90 area as [lo, hi] range
  const chart: Record<string, unknown>[] = d.history.map((h) => ({ t: Date.parse(h.date), obs: h.sm_percentile }))
  const last = d.history[d.history.length - 1]
  if (last) chart.push({ t: Date.parse(f16.issue_date), med: f16.sm_pct_now ?? last.sm_percentile, band: [f16.sm_pct_now ?? last.sm_percentile, f16.sm_pct_now ?? last.sm_percentile] })
  for (const f of [f16, f32]) chart.push({ t: Date.parse(f.valid_date), med: f.sm_pct_median, band: [f.sm_pct_p10, f.sm_pct_p90] })
  const drv = d.drivers[lead]
  const drvData = (drv?.drivers ?? []).map((x) => ({ name: pick(lang, x.label, x.label_mr), effect: x.effect, value: x.value }))

  return (
    <Container className="py-10 md:py-14">
      <Link to={`/predict?lead=${lead}`} className="mb-6 inline-flex items-center gap-1.5 text-[14px] text-graphite hover:text-ink"><ArrowLeft size={16} /> {pick(lang, 'All districts', 'सर्व जिल्हे')}</Link>
      <p className="eyebrow mb-2">{tt(lang, 'title')}</p>
      <h1 className="text-[45px] md:text-[57px]">{d.district}</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {[f16, f32].map((f, i) => (
          <Tilt key={f.lead_days} className={`rounded-[20px] ${i ? 'bg-peach' : 'bg-sky'} p-6`}>
            <p className="text-[14px] font-semibold">{f.lead_days} {tt(lang, 'days')} · {fmtD(f.valid_date)}</p>
            <p className="mt-3 text-[13px] text-graphite">{tt(lang, 'dryChance')}</p>
            <div className="flex items-center gap-3"><span className="font-serif text-[45px] font-light leading-none">{Math.round(f.prob_dry * 100)}%</span><BinPill bin={riskBin(f.dry_risk)} /></div>
            <p className="mt-3 text-[13px] text-graphite">{tt(lang, 'likely')}: <strong>{f.sm_pct_median.toFixed(0)}th</strong> {pick(lang, 'percentile', 'पर्सेंटाइल')} ({tt(lang, 'range')} {f.sm_pct_p10.toFixed(0)}–{f.sm_pct_p90.toFixed(0)}; {tt(lang, 'now')} {f.sm_pct_now?.toFixed(0) ?? '–'})</p>
          </Tilt>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ChartCard title={tt(lang, 'history')} subtitle={pick(lang, 'Percentile vs 2015–2024 for the same time of year · shaded: likely range (10–90%)', 'शेडिंग: संभाव्य श्रेणी')}>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chart} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#e1e0d9" vertical={false} />
              <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={(v) => fmtD(new Date(v).toISOString())} {...AXIS} minTickGap={28} />
              <YAxis domain={[0, 100]} ticks={[0, 20, 50, 80, 100]} {...AXIS} width={40} />
              <ReferenceLine y={20} stroke={DRY[2]} strokeDasharray="4 4" label={{ value: pick(lang, 'dry', 'कोरडे'), position: 'insideTopLeft', fill: DRY[2], fontSize: 12 }} />
              <Tooltip {...TT} labelFormatter={(l) => fmtD(new Date(Number(l)).toISOString())} formatter={(v: number | number[]) => (Array.isArray(v) ? `${v[0].toFixed(0)}–${v[1].toFixed(0)}` : `${Number(v).toFixed(0)}`)} />
              <Legend wrapperStyle={{ fontSize: 13 }} />
              <Area dataKey="band" name={tt(lang, 'range')} stroke="none" fill={WET[0]} fillOpacity={0.35} connectNulls />
              <Line dataKey="obs" name={pick(lang, 'Observed (SMAP)', 'निरीक्षित')} stroke={FOREST} strokeWidth={2} dot={false} connectNulls />
              <Line dataKey="med" name={pick(lang, 'Forecast (median)', 'अंदाज')} stroke={NORMAL} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4, fill: NORMAL }} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title={`${tt(lang, 'drivers')} · ${lead} ${tt(lang, 'days')}`}
          subtitle={pick(lang, `SHAP contributions to the ${drv?.explains ?? 'forecast'} (percentile points). Bars to the left push drier, to the right push wetter.`, 'डावीकडील पट्ट्या कोरडेपणाकडे, उजवीकडील ओलाव्याकडे.')}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={drvData} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="#e1e0d9" horizontal={false} />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="name" width={150} {...AXIS} tick={{ fill: '#353535', fontSize: 12 }} />
              <ReferenceLine x={0} stroke="#898781" />
              <Tooltip {...TT} formatter={(v: number, _n, p) => [`${v > 0 ? '+' : ''}${v.toFixed(1)} pts (${v < 0 ? tt(lang, 'drier') : tt(lang, 'wetter')})`, `value ${p?.payload?.value ?? '–'}`]} />
              <Bar dataKey="effect" radius={4} maxBarSize={18}>
                {drvData.map((x, i) => <Cell key={i} fill={x.effect < 0 ? DRY[1] : WET[1]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="mt-6"><ReliabilityCard s={d.skill[`lead${lead}` as 'lead16' | 'lead32']} lead={Number(lead)} /></div>
    </Container>
  )
}
