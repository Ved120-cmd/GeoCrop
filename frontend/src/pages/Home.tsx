import { lazy, Suspense, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowRight, CloudRain, Droplets, FlaskConical, Leaf, LineChart, Satellite, ShieldCheck, Sprout, Stethoscope, Waves } from 'lucide-react'
import { pick, useI18n } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { api, type Overview } from '../lib/api'
import { Container } from '../components/ui'
import { CountUp, Reveal, Tilt } from '../components/motion'
import { PROFILES_ENABLED } from '../lib/config'

const Hero3D = lazy(() => import('../components/Hero3D'))

/** Skip the 3D download (~240 KB gzipped) on data-saver or 2G connections. */
function lightweightOnly() {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection
  return !!c && (c.saveData === true || ['slow-2g', '2g'].includes(c.effectiveType ?? ''))
}

/** Aerial "quilt" of fields built from the design's pastel tiles (background texture; also the 3D fallback). */
function FieldQuilt({ className = '' }: { className?: string }) {
  const tiles = ['#e6ecd5', '#fceace', '#c3cda7', '#b2cee7', '#e6ecd5', '#f1efdf', '#c3cda7', '#fceace', '#e6ecd5', '#c3cda7', '#b2cee7', '#e6ecd5']
  const cells = Array.from({ length: 48 }, (_, i) => tiles[(i * 7 + (i % 5)) % tiles.length])
  return (
    <div aria-hidden className={`quilt-drift absolute inset-0 grid grid-cols-8 gap-[6px] p-[6px] opacity-[0.16] [transform-origin:50%_100%] ${className}`}>
      {cells.map((c, i) => <div key={i} className="rounded-[14px]" style={{ background: c, gridColumn: i % 9 === 0 ? 'span 2' : undefined }} />)}
    </div>
  )
}

const MODULES = [
  { to: '/monitor', icon: Satellite, tone: 'bg-sky', en: ['Monitor', 'Satellite and weather indicators for every district, and today’s water-stress estimate.'], mr: ['निरीक्षण', 'प्रत्येक जिल्ह्याचे उपग्रह व हवामान निर्देशक, आजचा पाण्याचा ताण.'] },
  { to: '/predict', icon: LineChart, tone: 'bg-peach', en: ['Predict', 'Chance of dry soil 16 and 32 days ahead, with what drives it.'], mr: ['अंदाज', '१६ व ३२ दिवसांनंतर कोरड्या मातीची शक्यता.'] },
  { to: '/soil', icon: Waves, tone: 'bg-sage', en: ['Soil', 'Texture, carbon and water-holding capacity of your district’s soil.'], mr: ['माती', 'तुमच्या जिल्ह्याच्या मातीचा पोत व पाणी धारण क्षमता.'] },
  { to: '/crop-advisor', icon: Sprout, tone: 'bg-white', en: ['Crop Advisor', 'Which crops did best here over the last ten seasons, rain-fed or irrigated.'], mr: ['पीक सल्ला', 'मागील दहा हंगामांत येथे कोणती पिके चांगली आली.'] },
  { to: '/plant-doctor', icon: Stethoscope, tone: 'bg-sage', en: ['Plant Doctor', 'Photograph a leaf to screen it for common diseases.'], mr: ['वनस्पती डॉक्टर', 'पानाचा फोटो घेऊन रोग तपासा.'] },
  { to: '/simulator', icon: FlaskConical, tone: 'bg-sky', en: ['Farm Simulator', 'Try sowing dates and irrigation plans on past seasons’ weather.'], mr: ['शेत सिम्युलेटर', 'पेरणी तारीख व सिंचन योजना मागील हंगामांवर तपासा.'] },
]

export default function Home() {
  const { t, lang } = useI18n()
  const { profile } = useProfile()
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/monitor/overview') })
  const lite = useMemo(lightweightOnly, [])
  const stressed = useMemo(() => ov.data?.districts.filter((d) => ['moderate', 'severe'].includes(d.indicators.stress_today?.stress ?? '')).length ?? null, [ov.data])
  const cards = [
    { icon: Satellite, title: t('how_1t'), body: t('how_1'), bg: 'bg-sky' },
    { icon: CloudRain, title: t('how_2t'), body: t('how_2'), bg: 'bg-peach' },
    { icon: Droplets, title: t('how_3t'), body: t('how_3'), bg: 'bg-sage' },
  ]
  return (
    <>
      <section className="relative isolate overflow-hidden bg-forest text-white">
        <FieldQuilt />
        <div className="relative mx-auto grid min-h-[82vh] max-w-[1200px] items-center gap-6 px-4 pb-16 pt-14 lg:grid-cols-[1.05fr_1fr] lg:gap-2 lg:py-20">
          <div className="text-center lg:text-left">
            <p className="eyebrow rise mb-5 !text-lime">{t('tagline')}</p>
            <h1 className="rise max-w-[16ch] text-[42px] leading-[1.04] [animation-delay:120ms] md:text-[60px] lg:text-[68px] mx-auto lg:mx-0">{t('hero_title')}</h1>
            <p className="rise mx-auto mt-6 max-w-[52ch] text-[17px] text-white/85 [animation-delay:260ms] lg:mx-0">{t('hero_body')}</p>
            <div className="rise mt-9 flex flex-wrap justify-center gap-3 [animation-delay:400ms] lg:justify-start">
              {PROFILES_ENABLED
                ? <Link to={profile ? '/my-farm' : '/onboarding'} className="btn bg-lime text-ink hover:bg-white">{profile ? t('nav_myfarm') : t('im_farmer')}</Link>
                : <Link to="/crop-advisor" className="btn bg-lime text-ink hover:bg-white">{pick(lang, 'Find crops for my district', 'माझ्या जिल्ह्यासाठी पिके')}</Link>}
              <Link to="/monitor" className="btn-ghost-light group">{t('explore')} <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" /></Link>
            </div>
          </div>
          <div className="rise relative h-[340px] [animation-delay:200ms] sm:h-[420px] lg:h-[560px]">
            {lite ? <div className="relative h-full overflow-hidden rounded-[20px]"><FieldQuilt className="!opacity-40" /></div> : (
              <Suspense fallback={<div className="h-full w-full" />}>
                <Hero3D fallback={<div className="relative h-full overflow-hidden rounded-[20px]"><FieldQuilt className="!opacity-40" /></div>} />
              </Suspense>
            )}
          </div>
        </div>
        <a href="#how" className="absolute bottom-5 left-1/2 hidden -translate-x-1/2 items-center gap-1.5 text-[13px] text-white/75 hover:text-white md:flex">{t('scroll')} <ArrowDown size={14} className="animate-bounce [animation-duration:2.4s]" /></a>
      </section>

      {/* live numbers */}
      <section className="bg-white">
        <Container className="grid grid-cols-2 gap-6 py-8 md:grid-cols-4">
          {[
            { v: stressed, suffix: ' / 36', label: pick(lang, 'districts under moderate or severe water stress today (estimate)', 'जिल्ह्यांत आज मध्यम/तीव्र पाण्याचा ताण (अंदाज)'), live: true },
            { v: 36, label: pick(lang, 'districts watched from space every few days', 'जिल्ह्यांवर उपग्रहांचे लक्ष') },
            { v: 30731, label: pick(lang, 'past seasons simulated to compare crops', 'पिकांच्या तुलनेसाठी सिम्युलेट केलेले हंगाम') },
            { v: 38, label: pick(lang, 'leaf conditions Plant Doctor can screen', 'वनस्पती डॉक्टर ओळखू शकणाऱ्या स्थिती') },
          ].map((s, i) => (
            <Reveal key={i} delay={i * 90}>
              <p className="flex items-center gap-2 font-serif text-[40px] font-light leading-none md:text-[48px]">
                {s.live && <span className="live-dot inline-block h-2.5 w-2.5 rounded-full bg-[#d0683d]" aria-hidden />}
                {s.v == null ? '–' : <CountUp value={s.v} />}{s.v != null && s.suffix && <span className="text-[22px] text-pewter">{s.suffix}</span>}
              </p>
              <p className="mt-2 max-w-[28ch] text-[13px] text-graphite">{s.label}</p>
            </Reveal>
          ))}
        </Container>
      </section>

      <section id="how" className="py-[50px] md:py-20">
        <Container>
          <Reveal><h2 className="mb-10 text-[37px] md:text-[45px]">{t('how_title')}</h2></Reveal>
          <div className="grid gap-6 md:grid-cols-3">
            {cards.map(({ icon: Icon, title, body, bg }, i) => (
              <Reveal key={title} delay={i * 120}>
                <Tilt className={`h-full rounded-[20px] ${bg} p-[30px]`}>
                  <span className="grid h-10 w-10 place-items-center rounded-full bg-white"><Icon size={18} strokeWidth={1.5} /></span>
                  <h3 className="mt-5 text-[24px]">{title}</h3>
                  <p className="mt-2 text-[15px] text-graphite">{body}</p>
                </Tilt>
              </Reveal>
            ))}
          </div>
        </Container>
      </section>

      <section className="pb-[50px] md:pb-20">
        <Container>
          <Reveal className="mb-8 flex items-end justify-between gap-4">
            <h2 className="text-[37px] md:text-[45px]">{pick(lang, 'Six tools, one farm', 'सहा साधने, एक शेत')}</h2>
            <Leaf className="hidden text-forest md:block" size={28} strokeWidth={1.25} />
          </Reveal>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((m, i) => {
              const [title, body] = lang === 'mr' ? m.mr : m.en
              return (
                <Reveal key={m.to} delay={(i % 3) * 100}>
                  <Tilt as={Link} to={m.to} className={`group flex h-full flex-col rounded-[20px] ${m.tone} p-[26px]`}>
                    <span className="grid h-11 w-11 place-items-center rounded-full bg-white transition-colors group-hover:bg-forest group-hover:text-white"><m.icon size={19} strokeWidth={1.5} /></span>
                    <h3 className="mt-5 text-[24px]">{title}</h3>
                    <p className="mt-2 flex-1 text-[15px] text-graphite">{body}</p>
                    <span className="mt-5 inline-flex items-center gap-1.5 text-[14px] font-semibold text-forest">{pick(lang, 'Open', 'उघडा')} <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" /></span>
                  </Tilt>
                </Reveal>
              )
            })}
          </div>
        </Container>
      </section>

      <section className="bg-forest py-16 text-white md:py-20">
        <Container className="grid items-center gap-10 md:grid-cols-[1.2fr_1fr]">
          <Reveal>
            <h2 className="text-[37px] md:text-[45px]">{t('how_4t')}</h2>
            <p className="mt-4 max-w-[60ch] text-[17px] text-white/85">{t('how_4')}</p>
          </Reveal>
          <Reveal delay={150} className="flex items-start gap-4 rounded-[20px] bg-white/10 p-[30px]">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-white text-forest"><ShieldCheck size={18} /></span>
            <p className="text-[15px] text-white/85">{t('footer_note')}</p>
          </Reveal>
        </Container>
      </section>
    </>
  )
}
