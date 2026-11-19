import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Plus, Sprout, Trash2, Play, Info } from 'lucide-react'
import { api, type Region } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { useDistrictGeo } from '../components/Maps'
import { ChartCard } from '../components/Charts'
import { Container, ErrorBox, MethodNote, SectionHeader } from '../components/ui'

// ---------- types
interface SimCrop { code: string; label: string; label_mr: string | null; calibration: string; yield_type: string; season_hint: string | null }
interface Irr { mode: 'rainfed' | 'net' | 'schedule'; allowable_depletion_raw_pct: number; schedule: [number, number][]; method: 1 | 3 | 4 | 5 }
interface Scen { label: string; sow: string /* MM-DD */; irrigation: Irr; every: number; depth: number; fromDay: number; toDay: number }
interface Run {
  year: number; sow_date: string; yield_t_ha: number; yield_q_acre: number; rain_mm: number; irrigation_mm: number; cycle_days: number
  water_stress_expansion_pct: number; water_stress_stomata_pct: number; complete_observed_weather: boolean; weather_gap_filled_pct: number
  harvest_date: string | null; initial_water: string; daily?: Record<string, number | string | null>[]
}
interface ScenResult {
  label: string; irrigation: string; yield_type: string; crop_calibration: string; caveats: string[]; runs: Run[]; errors: { sow_date: string; error: string }[]
  summary: { n_seasons: number; median_t_ha: number; p10_t_ha: number; p90_t_ha: number; median_q_acre: number; median_irrigation_mm: number; median_rain_mm: number; worst_year: number; best_year: number } | null
  vs_reference?: { median_yield_change_t_ha: number; median_yield_change_pct: number; median_extra_irrigation_mm: number; seasons_better: number; seasons_worse: number; n_seasons: number }
  soil: { thickness_m: number; sat: number; fc: number; wp: number; ksat: number; description: string }[]
}
interface SimResp { scenarios: ScenResult[]; value_type: string; cached: boolean }

// Categorical scenario colours: dataviz reference slots 1-3 (validated all-pairs for CVD); every series is also labelled.
const SCEN_COLORS = ['#2a78d6', '#eb6834', '#1baf7a']
const TONES = ['bg-sky', 'bg-peach', 'bg-sage']
const AXIS = { stroke: '#c3c2b7', tick: { fill: '#6d6d6d', fontSize: 12 }, tickLine: false }
const TT = { contentStyle: { background: '#212529', border: 0, borderRadius: 12, color: '#fff', fontSize: 13 }, labelStyle: { color: '#e8fe85' }, itemStyle: { color: '#fff' } }

const T = {
  title: ['Farm simulator', 'शेत सिम्युलेटर'], intro: ['Try “what if” choices for your crop: sowing date and irrigation. GeoCrop replays the last ten seasons of real weather in your district through FAO AquaCrop 7.3 and shows how yield and water use would have turned out.', 'तुमच्या पिकासाठी "असे केले तर" निवडी तपासा: पेरणी तारीख व सिंचन. GeoCrop तुमच्या जिल्ह्यातील मागील दहा हंगामांचे खरे हवामान FAO AquaCrop 7.3 मधून चालवते.'],
  district: ['District', 'जिल्हा'], crop: ['Crop', 'पीक'], scenario: ['Scenario', 'पर्याय'], sow: ['Sowing date', 'पेरणी तारीख'], water: ['Water management', 'पाणी व्यवस्थापन'],
  rainfed: ['Rainfed', 'कोरडवाहू'], net: ['Irrigate when needed', 'गरजेनुसार पाणी'], schedule: ['Fixed schedule', 'ठराविक वेळापत्रक'],
  threshold: ['Irrigate when this share of readily-available water is used', 'सहज उपलब्ध पाण्याचा इतका भाग वापरल्यावर पाणी द्या'],
  every: ['Every (days)', 'दर (दिवस)'], depth: ['Depth (mm)', 'खोली (मिमी)'], from: ['From day', 'दिवसापासून'], to: ['To day', 'दिवसापर्यंत'], method: ['Method', 'पद्धत'],
  m1: ['Sprinkler', 'तुषार'], m3: ['Drip', 'ठिबक'], m4: ['Furrow', 'सरी'], m5: ['Flood / basin', 'पाटपाणी'],
  add: ['Add scenario', 'पर्याय जोडा'], run: ['Run simulation', 'सिम्युलेशन चालवा'], running: ['Simulating past seasons… (about 10–30 s)', 'मागील हंगाम चालवत आहे… (सुमारे १०–३० सेकंद)'],
  median: ['Median yield', 'मध्य उत्पादन'], range: ['10–90% range across seasons', 'हंगामांतील १०–९०% श्रेणी'], irr: ['Irrigation (median)', 'सिंचन (मध्य)'],
  worst: ['Worst season', 'सर्वात वाईट हंगाम'], vs: ['compared with', 'तुलनेत'], better: ['better in', 'चांगले'], seasons: ['seasons', 'हंगाम'],
  byYear: ['Yield by season', 'हंगामानुसार उत्पादन'], irrByYear: ['Irrigation water by season', 'हंगामानुसार सिंचन'], detail: ['Inside one season', 'एका हंगामाच्या आत'],
  pickYear: ['Season', 'हंगाम'], canopy: ['Canopy cover (%)', 'पानांचे आच्छादन (%)'], rootWater: ['Root-zone water (mm)', 'मुळांच्या भागातील पाणी (मिमी)'],
  table: ['Season table', 'हंगाम सारणी'], soil: ['Soil used for this district', 'या जिल्ह्यासाठी वापरलेली माती'],
  attainable: ['Water-limited attainable yield, not a forecast of your harvest', 'पाणी-मर्यादित शक्य उत्पादन; तुमच्या पिकाचा अंदाज नाही'],
  incomplete: ['partly typical weather', 'अंशतः सरासरी हवामान'],
}
const tt = (lang: 'en' | 'mr', k: keyof typeof T) => (lang === 'mr' ? T[k][1] : T[k][0])

const newScen = (label: string, sow = '06-25', mode: Irr['mode'] = 'rainfed'): Scen => ({
  label, sow, irrigation: { mode, allowable_depletion_raw_pct: 50, schedule: [], method: 1 }, every: 10, depth: 40, fromDay: 20, toDay: 100,
})

export default function SimulatorPage() {
  const { lang } = useI18n()
  const { profile } = useProfile()
  const geo = useDistrictGeo()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => api.get<Region[]>('/geo/regions'), staleTime: Infinity })
  const crops = useQuery({ queryKey: ['sim-crops'], queryFn: () => api.get<SimCrop[]>('/simulator/crops'), staleTime: Infinity })

  const farm = profile?.farms[0]
  const [district, setDistrict] = useState<number>(farm?.district_id ?? 17)
  const [crop, setCrop] = useState('soybean')
  const [scens, setScens] = useState<Scen[]>([newScen('A'), newScen('B', '06-25', 'net')])
  const [detailYear, setDetailYear] = useState<number | null>(null)

  // prefill from profile: first simulator-supported crop + its sowing date + water source
  useEffect(() => {
    if (!farm || !crops.data) return
    setDistrict(farm.district_id)
    const map: Record<string, string> = { maize_kharif: 'maize', maize_rabi: 'maize' }
    const c = farm.crops.find((x) => crops.data!.some((s) => s.code === (map[x.crop] ?? x.crop)))
    if (c) {
      setCrop(map[c.crop] ?? c.crop)
      const sow = c.sowing_date ? c.sowing_date.slice(5) : '06-25'
      setScens([newScen('A', sow, farm.irrigation_source === 'rainfed' ? 'rainfed' : 'net'), newScen('B', sow, farm.irrigation_source === 'rainfed' ? 'net' : 'rainfed')])
    }
  }, [farm?.id, crops.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const body = (dy: number | null) => ({
    district_id: district, crop, detail_year: dy ?? undefined,
    scenarios: scens.map((s) => {
      const [m, d] = s.sow.split('-').map(Number)
      const sched: [number, number][] = s.irrigation.mode === 'schedule'
        ? Array.from({ length: Math.max(1, Math.floor((s.toDay - s.fromDay) / s.every) + 1) }, (_, i) => [s.fromDay + i * s.every, s.depth])
        : []
      return { label: s.label, sow_month: m, sow_day: d, irrigation: { ...s.irrigation, schedule: sched } }
    }),
  })
  const sim = useMutation({ mutationFn: (dy: number | null) => api.post<SimResp>('/simulator/run', body(dy)) })
  const res = sim.data

  const name = (id: number) => geo.data?.features.find((f) => f.properties.district_id === id)?.properties.district ?? ''
  const cropInfo = crops.data?.find((c) => c.code === crop)
  const yearsTable = useMemo(() => {
    if (!res) return []
    const years = [...new Set(res.scenarios.flatMap((s) => s.runs.map((r) => r.year)))].sort()
    return years.map((y) => {
      const row: Record<string, number | string | boolean | null> = { year: String(y) }
      res.scenarios.forEach((s, i) => {
        const r = s.runs.find((x) => x.year === y)
        row[`y${i}`] = r ? +(r.yield_q_acre).toFixed(1) : null
        row[`i${i}`] = r ? r.irrigation_mm : null
        row[`c${i}`] = r ? r.complete_observed_weather : null
      })
      return row
    })
  }, [res])
  const detail = res?.scenarios.map((s) => s.runs.find((r) => r.year === detailYear && r.daily)) ?? []
  const set = (i: number, patch: Partial<Scen>) => setScens((ss) => ss.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const setIrr = (i: number, patch: Partial<Irr>) => setScens((ss) => ss.map((s, j) => (j === i ? { ...s, irrigation: { ...s.irrigation, ...patch } } : s)))

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow="FAO AquaCrop 7.3" title={tt(lang, 'title')} intro={tt(lang, 'intro')} />

      {/* ---------- setup ---------- */}
      <div className="card space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="label" htmlFor="sd">{tt(lang, 'district')}</label>
            <select id="sd" className="field" value={district} onChange={(e) => setDistrict(Number(e.target.value))}>
              {regions.data?.filter((r) => r.key !== 'Khandesh').map((r) => (
                <optgroup key={r.key} label={pick(lang, r.name, r.name_mr)}>
                  {r.district_ids.map((id) => ({ id, n: name(id) })).sort((a, b) => a.n.localeCompare(b.n)).map(({ id, n }) => <option key={id} value={id}>{n}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="sc">{tt(lang, 'crop')}</label>
            <select id="sc" className="field" value={crop} onChange={(e) => setCrop(e.target.value)}>
              {crops.data?.map((c) => <option key={c.code} value={c.code}>{pick(lang, c.label, c.label_mr)}{c.season_hint ? ` · ${c.season_hint}` : ''}</option>)}
            </select>
            {cropInfo && <p className="mt-1.5 pl-5 text-[13px] text-pewter">{lang === 'mr' ? 'पीक मापदंड' : 'Crop parameters'}: {cropInfo.calibration}</p>}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {scens.map((s, i) => (
            <fieldset key={i} className={`rounded-[20px] ${TONES[i]} p-5`}>
              <legend className="sr-only">{tt(lang, 'scenario')} {s.label}</legend>
              <div className="mb-3 flex items-center justify-between">
                <span className="flex items-center gap-2 font-semibold"><span className="h-3 w-3 rounded-full" style={{ background: SCEN_COLORS[i] }} />{tt(lang, 'scenario')} {s.label}</span>
                {scens.length > 1 && <button type="button" className="rounded-full p-1.5 hover:bg-white/60" aria-label="remove" onClick={() => setScens(scens.filter((_, j) => j !== i))}><Trash2 size={15} /></button>}
              </div>
              <label className="label" htmlFor={`sow${i}`}>{tt(lang, 'sow')}</label>
              <input id={`sow${i}`} type="date" className="field" value={`2026-${s.sow}`} onChange={(e) => e.target.value && set(i, { sow: e.target.value.slice(5) })} />
              <p className="mb-3 mt-1 pl-5 text-[12px] text-graphite">{lang === 'mr' ? 'दरवर्षी हीच तारीख वापरली जाते' : 'Same day and month is used in every past season'}</p>
              <p className="label">{tt(lang, 'water')}</p>
              <div className="mb-3 flex flex-wrap gap-1.5">
                {(['rainfed', 'net', 'schedule'] as const).map((m) => (
                  <button key={m} type="button" aria-pressed={s.irrigation.mode === m} onClick={() => setIrr(i, { mode: m })} className={`${s.irrigation.mode === m ? 'chip-on' : 'chip-off'} !px-3 !py-1 !text-[13px]`}>{tt(lang, m)}</button>
                ))}
              </div>
              {s.irrigation.mode === 'net' && (
                <div>
                  <label className="label !text-[13px]" htmlFor={`thr${i}`}>{tt(lang, 'threshold')}: <strong>{s.irrigation.allowable_depletion_raw_pct}%</strong></label>
                  <input id={`thr${i}`} type="range" min={0} max={100} step={10} value={s.irrigation.allowable_depletion_raw_pct} className="w-full accent-[#07503f]"
                    onChange={(e) => setIrr(i, { allowable_depletion_raw_pct: Number(e.target.value) })} />
                </div>
              )}
              {s.irrigation.mode === 'schedule' && (
                <div className="grid grid-cols-2 gap-2">
                  {([['every', 'every', 3, 60], ['depth', 'depth', 5, 150], ['from', 'fromDay', 1, 300], ['to', 'toDay', 1, 300]] as const).map(([lab, key, mn, mx]) => (
                    <div key={key}>
                      <label className="label !text-[13px]" htmlFor={`${key}${i}`}>{tt(lang, lab)}</label>
                      <input id={`${key}${i}`} type="number" min={mn} max={mx} className="field !py-2" value={s[key]} onChange={(e) => set(i, { [key]: Number(e.target.value) } as Partial<Scen>)} />
                    </div>
                  ))}
                </div>
              )}
              {s.irrigation.mode !== 'rainfed' && (
                <div className="mt-3">
                  <label className="label !text-[13px]" htmlFor={`m${i}`}>{tt(lang, 'method')}</label>
                  <select id={`m${i}`} className="field !py-2" value={s.irrigation.method} onChange={(e) => setIrr(i, { method: Number(e.target.value) as Irr['method'] })}>
                    {([1, 3, 4, 5] as const).map((m) => <option key={m} value={m}>{tt(lang, `m${m}` as keyof typeof T)}</option>)}
                  </select>
                </div>
              )}
            </fieldset>
          ))}
          {scens.length < 3 && (
            <button type="button" onClick={() => setScens([...scens, newScen(['A', 'B', 'C'][scens.length], scens[0].sow)])}
              className="flex min-h-[180px] items-center justify-center gap-2 rounded-[20px] border-2 border-dashed border-moss text-graphite hover:border-forest hover:text-ink">
              <Plus size={18} /> {tt(lang, 'add')}
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-ash pt-6">
          <button className="btn-primary" onClick={() => { setDetailYear(null); sim.mutate(null) }} disabled={sim.isPending}><Play size={16} /> {tt(lang, 'run')}</button>
          {sim.isPending && <span className="flex items-center gap-2 text-[14px] text-pewter"><span className="h-4 w-4 animate-spin rounded-full border-2 border-moss border-t-forest" />{tt(lang, 'running')}</span>}
        </div>
        {sim.error && <ErrorBox error={sim.error} />}
      </div>

      {/* ---------- results ---------- */}
      {res && (
        <section className="mt-10 space-y-6" aria-live="polite">
          <p className="flex items-start gap-2 rounded-[20px] bg-lime px-5 py-3 text-[14px]"><Info size={16} className="mt-0.5 shrink-0" />
            <span><strong>{tt(lang, 'attainable')}.</strong> {res.scenarios[0].caveats.slice(1).join(' ')}</span></p>

          <div className="grid gap-4 lg:grid-cols-3">
            {res.scenarios.map((s, i) => (
              <div key={i} className={`rounded-[20px] ${TONES[i]} p-6`}>
                <p className="flex items-center gap-2 text-[14px] font-semibold"><span className="h-3 w-3 rounded-full" style={{ background: SCEN_COLORS[i] }} />{tt(lang, 'scenario')} {s.label}</p>
                <p className="mt-1 text-[13px] text-graphite">{s.irrigation}</p>
                {s.summary ? (
                  <>
                    <p className="mt-4 text-[13px] text-graphite">{tt(lang, 'median')} · {s.yield_type}</p>
                    <p className="font-serif text-[45px] font-light leading-none">{s.summary.median_q_acre} <span className="text-[17px]">q/acre</span></p>
                    <p className="text-[13px] text-graphite">{s.summary.median_t_ha} t/ha · {tt(lang, 'range')}: {s.summary.p10_t_ha}–{s.summary.p90_t_ha} t/ha</p>
                    <dl className="mt-4 grid grid-cols-2 gap-2 text-[13px]">
                      <div><dt className="text-graphite">{tt(lang, 'irr')}</dt><dd className="font-semibold">{s.summary.median_irrigation_mm} mm</dd></div>
                      <div><dt className="text-graphite">{tt(lang, 'worst')}</dt><dd className="font-semibold">{s.summary.worst_year}</dd></div>
                    </dl>
                    {s.vs_reference && (
                      <p className="mt-4 rounded-[14px] bg-white/70 p-3 text-[13px]">
                        <strong>{s.vs_reference.median_yield_change_pct > 0 ? '+' : ''}{s.vs_reference.median_yield_change_pct}%</strong> {lang === 'mr' ? 'उत्पादन' : 'yield'},{' '}
                        <strong>{s.vs_reference.median_extra_irrigation_mm > 0 ? '+' : ''}{s.vs_reference.median_extra_irrigation_mm} mm</strong> {lang === 'mr' ? 'पाणी' : 'water'} {tt(lang, 'vs')} {res.scenarios[0].label};{' '}
                        {tt(lang, 'better')} {s.vs_reference.seasons_better}/{s.vs_reference.n_seasons} {tt(lang, 'seasons')}
                      </p>
                    )}
                  </>
                ) : <p className="mt-4 text-[14px]">{s.errors[0]?.error}</p>}
              </div>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard title={tt(lang, 'byYear')} subtitle={`q/acre · ${res.scenarios[0].yield_type}`}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={yearsTable} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barGap={2}>
                  <CartesianGrid stroke="#e1e0d9" vertical={false} />
                  <XAxis dataKey="year" {...AXIS} />
                  <YAxis {...AXIS} width={44} />
                  <Tooltip {...TT} formatter={(v: number) => `${v} q/acre`} />
                  <Legend wrapperStyle={{ fontSize: 13 }} />
                  {res.scenarios.map((s, i) => <Bar key={i} dataKey={`y${i}`} name={`${tt(lang, 'scenario')} ${s.label}`} fill={SCEN_COLORS[i]} radius={[4, 4, 0, 0]} maxBarSize={22} />)}
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title={tt(lang, 'irrByYear')} subtitle="mm">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={yearsTable} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barGap={2}>
                  <CartesianGrid stroke="#e1e0d9" vertical={false} />
                  <XAxis dataKey="year" {...AXIS} />
                  <YAxis {...AXIS} width={44} />
                  <Tooltip {...TT} formatter={(v: number) => `${v} mm`} />
                  <Legend wrapperStyle={{ fontSize: 13 }} />
                  {res.scenarios.map((s, i) => <Bar key={i} dataKey={`i${i}`} name={`${tt(lang, 'scenario')} ${s.label}`} fill={SCEN_COLORS[i]} radius={[4, 4, 0, 0]} maxBarSize={22} />)}
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          {/* one season in detail */}
          <ChartCard title={tt(lang, 'detail')} subtitle={
            <span className="inline-flex flex-wrap items-center gap-2">{tt(lang, 'pickYear')}:
              {yearsTable.map((r) => (
                <button key={String(r.year)} className={`${detailYear === Number(r.year) ? 'chip-on' : 'chip-off'} !px-2.5 !py-0.5 !text-[12px]`}
                  onClick={() => { setDetailYear(Number(r.year)); sim.mutate(Number(r.year)) }}>{String(r.year)}</button>
              ))}
            </span>}>
            {detailYear == null ? <p className="py-6 text-[14px] text-pewter">{lang === 'mr' ? 'दैनिक वाढ पाहण्यासाठी हंगाम निवडा.' : 'Pick a season to see daily canopy growth and root-zone water.'}</p>
              : sim.isPending ? <p className="py-6 text-[14px] text-pewter">{tt(lang, 'running')}</p> : (
                <div className="grid gap-6 lg:grid-cols-2">
                  {(['canopy_pct', 'root_zone_water_mm'] as const).map((k) => (
                    <div key={k}>
                      <p className="mb-2 text-[13px] font-medium">{k === 'canopy_pct' ? tt(lang, 'canopy') : tt(lang, 'rootWater')}</p>
                      <ResponsiveContainer width="100%" height={220}>
                        <ComposedChart margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                          <CartesianGrid stroke="#e1e0d9" vertical={false} />
                          <XAxis dataKey="dap" type="number" domain={['dataMin', 'dataMax']} {...AXIS} allowDuplicatedCategory={false} label={{ value: lang === 'mr' ? 'पेरणीनंतर दिवस' : 'days after sowing', position: 'insideBottomRight', offset: -2, fontSize: 11, fill: '#6d6d6d' }} />
                          <YAxis {...AXIS} width={48} />
                          <Tooltip {...TT} labelFormatter={(l) => `${lang === 'mr' ? 'दिवस' : 'day'} ${l}`} />
                          <Legend wrapperStyle={{ fontSize: 13 }} />
                          {detail.map((r, i) => r?.daily ? <Line key={i} data={r.daily} dataKey={k} name={`${tt(lang, 'scenario')} ${res.scenarios[i].label}`} stroke={SCEN_COLORS[i]} strokeWidth={2} dot={false} /> : null)}
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  ))}
                </div>
              )}
          </ChartCard>

          <details className="card !p-6">
            <summary className="cursor-pointer font-semibold">{tt(lang, 'table')}</summary>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[560px] text-[14px]">
                <thead><tr className="border-b border-ash text-left text-pewter">
                  <th className="py-2 pr-3 font-medium">{tt(lang, 'pickYear')}</th>
                  {res.scenarios.map((s, i) => <th key={i} className="py-2 pr-3 font-medium">{s.label}: q/acre · mm</th>)}
                </tr></thead>
                <tbody>{yearsTable.map((r) => (
                  <tr key={String(r.year)} className="border-b border-ash/70">
                    <td className="py-2 pr-3">{String(r.year)}</td>
                    {res.scenarios.map((_, i) => <td key={i} className="py-2 pr-3 tabular-nums">{r[`y${i}`] ?? '–'} · {r[`i${i}`] ?? '–'}{r[`c${i}`] === false ? ` (${tt(lang, 'incomplete')})` : ''}</td>)}
                  </tr>))}</tbody>
              </table>
            </div>
          </details>

          <MethodNote>
            <p>{pick(lang,
              'Engine: official FAO AquaCrop 7.3 (Python), with one documented bug fix (simulator/aquacrop/engine_patched/PATCHES.md). Weather: NASA POWER temperature and FAO-56 reference ET, IMD gauge rainfall (IMERG scaled to IMD after IMD’s last release) for the district. Initial soil water: NASA SMAP on the sowing date. Seasons whose crop cycle runs past today use typical weather for the remaining days and are excluded from the statistics.',
              'इंजिन: अधिकृत FAO AquaCrop 7.3 (Python), एका नोंदवलेल्या दुरुस्तीसह. हवामान: NASA POWER, IMD पाऊस. सुरुवातीचा मातीतील ओलावा: SMAP.')}</p>
            <p className="font-medium">{tt(lang, 'soil')}:</p>
            <ul className="list-inside list-disc">
              {res.scenarios[0].soil.map((h) => <li key={h.description}>{h.description}: FC {h.fc}% · WP {h.wp}% · SAT {h.sat}% · Ksat {h.ksat} mm/day</li>)}
            </ul>
          </MethodNote>
        </section>
      )}

      {!res && !sim.isPending && (
        <div className="mt-10 flex items-center gap-3 rounded-[20px] bg-sage p-6 text-[15px] text-graphite"><Sprout size={20} className="shrink-0 text-forest" />
          {lang === 'mr' ? 'उदा.: कोरडवाहू सोयाबीन विरुद्ध गरजेनुसार पाणी, किंवा २० जून विरुद्ध १० जुलै पेरणी.' : 'Example: rainfed soybean vs. irrigating when needed, or sowing on 20 June vs. 10 July.'}
        </div>
      )}
    </Container>
  )
}
