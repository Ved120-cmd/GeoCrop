import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Camera, CheckCircle2, ImageUp, Phone, ShieldCheck, TriangleAlert } from 'lucide-react'
import { api } from '../lib/api'
import { pick, useI18n } from '../lib/i18n'
import { DRY } from '../lib/scales'
import { Container, ErrorBox, Loading, MethodNote, SectionHeader } from '../components/ui'

interface CropInfo { crop: string; name: string; name_mr: string; conditions: string[] }
interface Skill { n: number; top1: number; top3: number; top1_crop_given: number; healthy_vs_diseased_acc_crop_given: number; diseased_recall_crop_given: number; ece: number }
interface Info { crops: CropInfo[]; unsure_below: number; trained_at: string; skill: { test_lab: Skill; test_field: Skill } }
interface Pred { label: string; crop: string; crop_mr: string; condition: string; condition_name: string; condition_name_mr: string; healthy: boolean; probability: number }
interface Diagnosis { predictions: Pred[]; confident: boolean; crop_given: string | null; warnings: string[]; value_type: string }

const pct = (x: number) => `${Math.round(x * 100)}%`
// never round a near-perfect score up to 100%
const pct1 = (x: number) => `${(Math.floor(x * 1000) / 10).toFixed(1)}%`
const cropName = (c: string) => c.replace('_', ' ').replace(/^./, (m) => m.toUpperCase())

function Reliability({ s }: { s: Info['skill'] }) {
  const { lang } = useI18n()
  const f = s.test_field
  return (
    <div className="rounded-[20px] bg-forest p-6 text-white">
      <p className="flex items-center gap-2 text-[15px] font-semibold"><ShieldCheck size={18} /> {pick(lang, 'How reliable is this?', 'हे किती विश्वासार्ह आहे?')}</p>
      <ul className="mt-4 space-y-3 text-[14px] text-white/90">
        <li>{pick(lang,
          `On ${f.n} real field photos it never saw, with the crop chosen, the top answer was right ${pct(f.top1_crop_given)} of the time; the right answer was in its top 3 ${pct(f.top3)} of the time (without choosing the crop).`,
          `न पाहिलेल्या ${f.n} शेतातील फोटोंवर, पीक निवडल्यावर पहिले उत्तर ${pct(f.top1_crop_given)} वेळा बरोबर.`)}</li>
        <li>{pick(lang,
          `It told healthy from diseased leaves correctly ${pct(f.healthy_vs_diseased_acc_crop_given)} of the time and flagged ${pct(f.diseased_recall_crop_given)} of diseased leaves.`,
          `निरोगी व रोगग्रस्त पाने ${pct(f.healthy_vs_diseased_acc_crop_given)} वेळा बरोबर ओळखली.`)}</li>
        <li>{pick(lang,
          `On clean lab photos it scores ${pct1(s.test_lab.top1)}, but real photos are much harder; trust the field figure.`,
          `प्रयोगशाळेतील फोटोंवर ${pct1(s.test_lab.top1)}, पण शेतातील फोटो कठीण असतात.`)}</li>
        <li className="flex gap-2 text-lime"><TriangleAlert size={16} className="mt-0.5 shrink-0" />{pick(lang,
          'Not yet tested on photos from Maharashtra farms. Use it to screen, then confirm with your KVK or agriculture officer before spraying.',
          'महाराष्ट्रातील शेतांच्या फोटोंवर अजून तपासलेले नाही. फवारणीपूर्वी कृषी विज्ञान केंद्र / कृषी अधिकाऱ्यांकडून खात्री करा.')}</li>
      </ul>
    </div>
  )
}

export default function DoctorPage() {
  const { lang, t } = useI18n()
  const info = useQuery({ queryKey: ['doctor-info'], queryFn: () => api.get<Info>('/doctor/info') })
  const [crop, setCrop] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const run = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append('image', file!); if (crop) fd.append('crop', crop); return api.postForm<Diagnosis>('/doctor/diagnose', fd) },
  })
  const choose = (f: File | null) => { setFile(f); run.reset() }
  const top = run.data?.predictions[0]

  return (
    <Container className="py-10 md:py-14">
      <SectionHeader eyebrow={t('nav_doctor')} title={pick(lang, 'Check a leaf for disease', 'पानावरील रोग तपासा')}
        intro={pick(lang, 'Take a clear photo of one leaf. The model suggests the most likely disease, with how sure it is.', 'एका पानाचा स्पष्ट फोटो घ्या. मॉडेल संभाव्य रोग व खात्री सांगेल.')} />
      {info.isLoading && <Loading />}
      {info.error && <ErrorBox error={info.error} onRetry={() => info.refetch()} />}
      {info.data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-6">
            <div className="card space-y-5">
              <label className="block">
                <span className="text-[14px] font-semibold">1. {pick(lang, 'Crop', 'पीक')}</span>
                <select className="mt-2 w-full rounded-[12px] border border-[#c3c2b7] bg-white px-4 py-3 text-[15px]" value={crop} onChange={(e) => { setCrop(e.target.value); run.reset() }}>
                  <option value="">{pick(lang, 'Not sure / let the model decide', 'माहीत नाही / मॉडेल ठरवेल')}</option>
                  {info.data.crops.map((c) => <option key={c.crop} value={c.crop}>{pick(lang, c.name, c.name_mr)}</option>)}
                </select>
                <span className="mt-1.5 block text-[13px] text-pewter">{pick(lang, 'Choosing the crop makes the answer more accurate. Cotton, soybean diseases, onion, sugarcane, pulses and pomegranate are not covered yet.', 'पीक निवडल्यास उत्तर अधिक अचूक. कापूस, सोयाबीन रोग, कांदा, ऊस, डाळी, डाळिंब अजून समाविष्ट नाहीत.')}</span>
              </label>
              <div>
                <span className="text-[14px] font-semibold">2. {pick(lang, 'Leaf photo', 'पानाचा फोटो')}</span>
                <div className="mt-2 flex flex-wrap gap-3">
                  <label className="btn-primary cursor-pointer"><Camera size={16} /> {pick(lang, 'Take photo', 'फोटो काढा')}
                    <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => choose(e.target.files?.[0] ?? null)} /></label>
                  <label className="btn-ghost cursor-pointer"><ImageUp size={16} /> {pick(lang, 'Upload', 'अपलोड')}
                    <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => choose(e.target.files?.[0] ?? null)} /></label>
                </div>
                <p className="mt-2 text-[13px] text-pewter">{pick(lang, 'Tips: one leaf filling most of the frame, daylight, in focus, both spots and healthy parts visible.', 'टीप: एक पान, दिवसाचा प्रकाश, स्पष्ट फोकस.')}</p>
              </div>
              {preview && <img src={preview} alt={pick(lang, 'Selected leaf photo', 'निवडलेला फोटो')} className="max-h-72 rounded-[16px] object-contain" />}
              <button className="btn-primary" disabled={!file || run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? pick(lang, 'Checking…', 'तपासत आहे…') : pick(lang, 'Check this leaf', 'हे पान तपासा')}
              </button>
              {run.error && <ErrorBox error={run.error} />}
            </div>

            {run.data && top && (
              <div className="card" aria-live="polite">
                {!run.data.confident && (
                  <p className="mb-4 flex gap-2 rounded-[12px] bg-peach p-4 text-[14px]"><TriangleAlert size={18} className="shrink-0" />
                    {pick(lang, 'The model is not sure about this photo. Try a closer, sharper photo of a single leaf, or choose the crop. It may also be a problem the model does not know (pest, nutrient, water or spray damage).',
                      'मॉडेलला खात्री नाही. जवळून स्पष्ट फोटो घ्या किंवा पीक निवडा. ही समस्या मॉडेलला माहीत नसलेली असू शकते.')}</p>)}
                {run.data.warnings.includes('low_resolution') && <p className="mb-4 text-[13px] text-graphite">{pick(lang, 'Low-resolution photo: results may be less reliable.', 'कमी रिझोल्यूशन फोटो.')}</p>}
                <p className="eyebrow">{pick(lang, 'Most likely', 'सर्वाधिक शक्यता')}</p>
                <p className="mt-1 flex items-center gap-2 text-[28px] font-light">
                  {top.healthy ? <CheckCircle2 className="text-forest" /> : <TriangleAlert style={{ color: DRY[2] }} />}
                  {pick(lang, `${cropName(top.crop)}: ${top.condition_name}`, `${top.crop_mr}: ${top.condition_name_mr}`)}
                </p>
                <ul className="mt-5 space-y-3">
                  {run.data.predictions.map((p) => (
                    <li key={p.label}>
                      <div className="flex justify-between text-[14px]"><span>{pick(lang, `${cropName(p.crop)}: ${p.condition_name}`, `${p.crop_mr}: ${p.condition_name_mr}`)}</span><span className="tabular-nums font-medium">{pct(p.probability)}</span></div>
                      <div className="mt-1 h-2 rounded-full bg-[#e9e7dd]"><div className="h-2 rounded-full" style={{ width: pct(p.probability), background: p.healthy ? 'var(--color-forest)' : DRY[1] }} /></div>
                    </li>
                  ))}
                </ul>
                <div className="mt-6 rounded-[16px] bg-sage p-5 text-[14px]">
                  <p className="font-semibold">{pick(lang, 'What to do next', 'पुढे काय करावे')}</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-graphite">
                    <li>{pick(lang, 'Check several plants: one leaf is not the whole field.', 'अनेक झाडे तपासा.')}</li>
                    <li>{pick(lang, 'Before buying or spraying any chemical, confirm with your Krishi Vigyan Kendra (KVK) or taluka agriculture officer, and use only products registered for that crop.', 'कोणतेही रसायन फवारण्यापूर्वी कृषी विज्ञान केंद्र / तालुका कृषी अधिकाऱ्यांकडून खात्री करा.')}</li>
                    <li className="flex items-center gap-1.5"><Phone size={14} /> {pick(lang, 'Kisan Call Centre (free): 1800-180-1551', 'किसान कॉल सेंटर (मोफत): १८००-१८०-१५५१')}</li>
                  </ul>
                </div>
              </div>
            )}
          </div>
          <aside className="space-y-4">
            <Reliability s={info.data.skill} />
            <div className="card !p-6 text-[14px]">
              <p className="font-semibold">{pick(lang, 'Crops it knows', 'समाविष्ट पिके')}</p>
              <p className="mt-2 text-graphite">{info.data.crops.map((c) => pick(lang, c.name, c.name_mr)).join(', ')}</p>
            </div>
          </aside>
        </div>
      )}
      <div className="mt-10"><MethodNote>
        <p>{pick(lang, 'EfficientNet-B0 image model fine-tuned on PlantVillage (lab photos) and PlantDoc (field photos from the internet). Repeat photos of the same leaf were kept out of the test sets. Your photo is analysed and not stored.',
          'EfficientNet-B0 मॉडेल PlantVillage व PlantDoc फोटोंवर प्रशिक्षित. तुमचा फोटो साठवला जात नाही.')}</p>
      </MethodNote></div>
    </Container>
  )
}
