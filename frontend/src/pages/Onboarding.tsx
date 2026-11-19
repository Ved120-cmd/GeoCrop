import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check, LocateFixed, MapPin, Plus, Trash2 } from 'lucide-react'
import { api, type CropOption, type CropPlanting, type Farm, type Profile, type ProfileIn, type Region } from '../lib/api'
import { pick, useI18n, type TKey } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { useDistrictGeo, PinMap } from '../components/Maps'
import { Container, ErrorBox, Loading } from '../components/ui'

const IRR = ['rainfed', 'well', 'borewell', 'canal', 'tank', 'river', 'drip', 'sprinkler', 'other'] as const
const SOILS = ['black', 'red', 'laterite', 'alluvial', 'sandy', 'unknown'] as const
const SEASONS = ['kharif', 'rabi', 'summer', 'annual'] as const

const emptyFarm = (): Farm => ({ district_id: 0, area_unit: 'acre', irrigation_source: 'rainfed', soil_type_reported: 'unknown', crops: [] })

export default function Onboarding({ edit = false }: { edit?: boolean }) {
  const { t, lang, setLang } = useI18n()
  const { profile, setProfileId, refresh } = useProfile()
  const nav = useNavigate()
  const geo = useDistrictGeo()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => api.get<Region[]>('/geo/regions'), staleTime: Infinity })
  const crops = useQuery({ queryKey: ['crops'], queryFn: () => api.get<CropOption[]>('/meta/crops'), staleTime: Infinity })

  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [language, setLanguage] = useState<'en' | 'mr'>(lang)
  const [farm, setFarm] = useState<Farm>(emptyFarm)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const [pinCheck, setPinCheck] = useState<{ inside_maharashtra: boolean; district_id: number | null; district: string | null } | null>(null)

  useEffect(() => {
    if (edit && profile) {
      setName(profile.name); setPhone(profile.phone ?? ''); setLanguage(profile.language)
      const f = profile.farms[0]; if (f) setFarm({ ...f, crops: f.crops.map((c) => ({ ...c })) })
    }
  }, [edit, profile])

  useEffect(() => {
    if (farm.lat == null || farm.lon == null) { setPinCheck(null); return }
    api.get<typeof pinCheck>(`/geo/locate?lat=${farm.lat}&lon=${farm.lon}`).then(setPinCheck).catch(() => setPinCheck(null))
  }, [farm.lat, farm.lon])

  const districtName = (id: number) => geo.data?.features.find((f) => f.properties.district_id === id)?.properties.district ?? ''
  const cropLabel = (code: string) => { const c = crops.data?.find((x) => x.code === code); return c ? pick(lang, c.label, c.label_mr) : code }

  const steps: TKey[] = ['step_you', 'step_location', 'step_farm', 'step_review']
  const valid = [name.trim().length > 0 && (!phone || /^[0-9+ -]{7,20}$/.test(phone)), farm.district_id > 0, farm.crops.every((c) => c.crop && c.season && (c.crop !== 'other' || c.crop_other)), true]

  const grouped = useMemo(() => {
    if (!regions.data || !geo.data) return []
    return regions.data.filter((r) => r.key !== 'Khandesh').map((r) => ({
      label: pick(lang, r.name, r.name_mr),
      items: r.district_ids.map((id) => ({ id, name: districtName(id) })).sort((a, b) => a.name.localeCompare(b.name)),
    }))
  }, [regions.data, geo.data, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setSaving(true); setErr(null)
    const body: ProfileIn = {
      name: name.trim(), phone: phone.trim() || null, language,
      farm: { ...farm, crops: farm.crops.map((c) => ({ crop: c.crop, crop_other: c.crop === 'other' ? c.crop_other : null, season: c.season, sowing_date: c.sowing_date || null })) },
    }
    try {
      const p = edit && profile ? await api.put<Profile>(`/profiles/${profile.id}`, body) : await api.post<Profile>('/profiles', body)
      setProfileId(p.id); setLang(p.language); refresh()
      nav('/my-farm')
    } catch (e) { setErr(e) } finally { setSaving(false) }
  }

  function setCrop(i: number, patch: Partial<CropPlanting>) {
    setFarm((f) => ({ ...f, crops: f.crops.map((c, j) => (j === i ? { ...c, ...patch } : c)) }))
  }

  if (geo.isLoading || regions.isLoading || crops.isLoading) return <Container><Loading /></Container>
  if (geo.error || regions.error || crops.error) return <Container className="py-10"><ErrorBox error={geo.error || regions.error || crops.error} /></Container>

  return (
    <Container className="py-10 md:py-14">
      <div className="mx-auto max-w-[820px]">
        <h1 className="text-[37px] md:text-[45px]">{t('ob_title')}</h1>
        <p className="mt-2 text-[17px] text-graphite">{t('ob_sub')}</p>

        {/* stepper */}
        <ol className="mt-8 flex flex-wrap gap-2" aria-label="Steps">
          {steps.map((s, i) => (
            <li key={s}>
              <button type="button" onClick={() => i <= step && setStep(i)} disabled={i > step}
                aria-current={i === step ? 'step' : undefined}
                className={i === step ? 'chip-on' : i < step ? 'chip-off !border-forest' : 'chip-off opacity-60'}>
                <span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] ${i === step ? 'bg-white text-forest' : 'bg-sage'}`}>
                  {i < step ? <Check size={12} /> : i + 1}
                </span>
                {t(s)}
              </button>
            </li>
          ))}
        </ol>

        <div className="card mt-6 space-y-6">
          {step === 0 && (
            <>
              <div>
                <label className="label" htmlFor="name">{t('name')} *</label>
                <input id="name" className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={120} />
              </div>
              <div>
                <label className="label" htmlFor="phone">{t('phone')}</label>
                <input id="phone" className="field" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" />
                <p className="mt-1.5 pl-5 text-[13px] text-pewter">{t('phone_help')}</p>
              </div>
              <fieldset>
                <legend className="label">{t('language')}</legend>
                <div className="flex gap-2">
                  {(['en', 'mr'] as const).map((l) => (
                    <button key={l} type="button" onClick={() => { setLanguage(l); setLang(l) }} className={language === l ? 'chip-on' : 'chip-off'} aria-pressed={language === l}>
                      {l === 'en' ? 'English' : 'मराठी'}
                    </button>
                  ))}
                </div>
              </fieldset>
            </>
          )}

          {step === 1 && (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="label">{t('state')}</label>
                  <input className="field bg-ash" value={lang === 'mr' ? 'महाराष्ट्र' : 'Maharashtra'} disabled />
                </div>
                <div>
                  <label className="label" htmlFor="district">{t('district')} *</label>
                  <select id="district" className="field appearance-none" value={farm.district_id || ''}
                    onChange={(e) => setFarm({ ...farm, district_id: Number(e.target.value), lat: null, lon: null })}>
                    <option value="" disabled>{t('choose_district')}</option>
                    {grouped.map((g) => (
                      <optgroup key={g.label} label={g.label}>
                        {g.items.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="taluka">{t('taluka')}</label>
                  <input id="taluka" className="field" value={farm.taluka ?? ''} onChange={(e) => setFarm({ ...farm, taluka: e.target.value })} maxLength={80} />
                </div>
                <div>
                  <label className="label" htmlFor="village">{t('village')}</label>
                  <input id="village" className="field" value={farm.village ?? ''} onChange={(e) => setFarm({ ...farm, village: e.target.value })} maxLength={80} />
                </div>
              </div>
              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="label !mb-0 flex items-center gap-1.5"><MapPin size={16} /> {t('pin_title')}</p>
                  <button type="button" className="btn-ghost !py-1.5" onClick={() => navigator.geolocation?.getCurrentPosition(
                    (p) => setFarm((f) => ({ ...f, lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5) })))}>
                    <LocateFixed size={15} /> {t('use_my_location')}
                  </button>
                </div>
                <p className="mb-3 text-[14px] text-pewter">{t('pin_help')}</p>
                <div className="overflow-hidden rounded-[20px] ring-1 ring-moss">
                  <PinMap fc={geo.data} districtId={farm.district_id || undefined} lat={farm.lat} lon={farm.lon} onPick={(lat, lon) => setFarm((f) => ({ ...f, lat, lon }))} />
                </div>
                {pinCheck && (
                  <p className={`mt-2 text-[14px] ${!pinCheck.inside_maharashtra || (farm.district_id && pinCheck.district_id !== farm.district_id) ? 'text-dry-3' : 'text-forest'}`}>
                    {!pinCheck.inside_maharashtra ? t('pin_outside')
                      : farm.district_id && pinCheck.district_id !== farm.district_id ? t('pin_mismatch', { d: pinCheck.district ?? '' })
                        : t('pin_ok', { d: pinCheck.district ?? '' })}
                    {farm.lat != null && <span className="ml-2 text-pewter">({farm.lat}, {farm.lon})</span>}
                  </p>
                )}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="label" htmlFor="fname">{t('farm_name')}</label>
                  <input id="fname" className="field" value={farm.name ?? ''} onChange={(e) => setFarm({ ...farm, name: e.target.value })} maxLength={120} />
                </div>
                <div>
                  <label className="label" htmlFor="area">{t('area')}</label>
                  <div className="flex gap-2">
                    <input id="area" className="field" type="number" min={0} step="0.1" value={farm.area_value ?? ''}
                      onChange={(e) => setFarm({ ...farm, area_value: e.target.value ? Number(e.target.value) : null })} />
                    <select className="field !w-auto" value={farm.area_unit} onChange={(e) => setFarm({ ...farm, area_unit: e.target.value as Farm['area_unit'] })} aria-label="unit">
                      {(['acre', 'hectare', 'guntha'] as const).map((u) => <option key={u} value={u}>{t(`unit_${u}` as TKey)}</option>)}
                    </select>
                  </div>
                </div>
              </div>
              <fieldset>
                <legend className="label">{t('irrigation')}</legend>
                <div className="flex flex-wrap gap-2">
                  {IRR.map((s) => (
                    <button key={s} type="button" aria-pressed={farm.irrigation_source === s} onClick={() => setFarm({ ...farm, irrigation_source: s })}
                      className={farm.irrigation_source === s ? 'chip-on' : 'chip-off'}>{t(`irr_${s}` as TKey)}</button>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend className="label">{t('soil_type')}</legend>
                <div className="flex flex-wrap gap-2">
                  {SOILS.map((s) => (
                    <button key={s} type="button" aria-pressed={farm.soil_type_reported === s} onClick={() => setFarm({ ...farm, soil_type_reported: s })}
                      className={farm.soil_type_reported === s ? 'chip-on' : 'chip-off'}>{t(`soil_${s}` as TKey)}</button>
                  ))}
                </div>
              </fieldset>
              <div>
                <p className="label">{t('crops_title')}</p>
                <div className="space-y-3">
                  {farm.crops.map((c, i) => {
                    const opt = crops.data?.find((x) => x.code === c.crop)
                    return (
                      <div key={i} className="rounded-[20px] bg-sage p-4">
                        <div className="grid gap-3 md:grid-cols-[1.3fr_1fr_1fr_auto] md:items-end">
                          <div>
                            <label className="label" htmlFor={`crop${i}`}>{t('crop')}</label>
                            <select id={`crop${i}`} className="field" value={c.crop} onChange={(e) => {
                              const o = crops.data?.find((x) => x.code === e.target.value)
                              setCrop(i, { crop: e.target.value, season: (o?.season_hint as CropPlanting['season']) ?? c.season })
                            }}>
                              {crops.data?.map((o) => <option key={o.code} value={o.code}>{pick(lang, o.label, o.label_mr)}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="label" htmlFor={`season${i}`}>{t('season')}</label>
                            <select id={`season${i}`} className="field" value={c.season} onChange={(e) => setCrop(i, { season: e.target.value as CropPlanting['season'] })}>
                              {SEASONS.map((s) => <option key={s} value={s}>{t(`s_${s}` as TKey)}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="label" htmlFor={`sow${i}`}>{t('sowing_date')}</label>
                            <input id={`sow${i}`} className="field" type="date" value={c.sowing_date ?? ''} onChange={(e) => setCrop(i, { sowing_date: e.target.value })} />
                          </div>
                          <button type="button" className="btn-ghost !px-3" onClick={() => setFarm({ ...farm, crops: farm.crops.filter((_, j) => j !== i) })} aria-label={t('remove')}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                        {c.crop === 'other' && (
                          <div className="mt-3">
                            <label className="label" htmlFor={`oc${i}`}>{t('other_crop')}</label>
                            <input id={`oc${i}`} className="field" value={c.crop_other ?? ''} onChange={(e) => setCrop(i, { crop_other: e.target.value })} />
                          </div>
                        )}
                        {opt && (
                          <p className="mt-2 pl-1 text-[13px] text-graphite">
                            {opt.stress_estimate_supported ? `✓ ${t('stress_supported')}` : `— ${t('stress_unsupported')}`}
                          </p>
                        )}
                      </div>
                    )
                  })}
                </div>
                <button type="button" className="btn-ghost mt-3" onClick={() => setFarm({ ...farm, crops: [...farm.crops, { crop: 'soybean', season: 'kharif', sowing_date: '' }] })}>
                  <Plus size={16} /> {t('add_crop')}
                </button>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <h2 className="text-[28px]">{t('review_title')}</h2>
              <dl className="grid gap-x-6 gap-y-3 text-[15px] sm:grid-cols-[max-content_1fr]">
                <dt className="text-pewter">{t('name')}</dt><dd>{name}</dd>
                {phone && <><dt className="text-pewter">{t('phone')}</dt><dd>{phone}</dd></>}
                <dt className="text-pewter">{t('district')}</dt><dd>{districtName(farm.district_id)}{farm.taluka ? ` · ${farm.taluka}` : ''}{farm.village ? ` · ${farm.village}` : ''}</dd>
                <dt className="text-pewter">{t('pin_title')}</dt><dd>{farm.lat != null ? `${farm.lat}, ${farm.lon}` : '—'}</dd>
                <dt className="text-pewter">{t('area')}</dt><dd>{farm.area_value ? `${farm.area_value} ${t(`unit_${farm.area_unit}` as TKey)}` : '—'}</dd>
                <dt className="text-pewter">{t('irrigation')}</dt><dd>{t(`irr_${farm.irrigation_source}` as TKey)}</dd>
                <dt className="text-pewter">{t('soil_type')}</dt><dd>{t(`soil_${farm.soil_type_reported}` as TKey)}</dd>
                <dt className="text-pewter">{t('crops_title')}</dt>
                <dd>{farm.crops.length ? farm.crops.map((c) => `${c.crop === 'other' ? c.crop_other : cropLabel(c.crop)} (${t(`s_${c.season}` as TKey)}${c.sowing_date ? `, ${c.sowing_date}` : ''})`).join('; ') : '—'}</dd>
              </dl>
              {err != null && <ErrorBox error={err} />}
            </>
          )}

          <div className="flex justify-between gap-3 border-t border-ash pt-6">
            <button type="button" className="btn-ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>{t('back')}</button>
            {step < 3
              ? <button type="button" className="btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!valid[step]}>{t('next')}</button>
              : <button type="button" className="btn-primary" onClick={save} disabled={saving || !valid.every(Boolean)}>{saving ? t('saving') : t('save')}</button>}
          </div>
        </div>
      </div>
    </Container>
  )
}
