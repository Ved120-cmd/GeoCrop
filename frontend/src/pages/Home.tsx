import { Link } from 'react-router-dom'
import { ArrowDown, CloudRain, Droplets, Satellite, ShieldCheck } from 'lucide-react'
import { useI18n } from '../lib/i18n'
import { useProfile } from '../lib/profile'
import { Container } from '../components/ui'

/** Aerial "quilt" of fields built from the design's pastel tiles (stand-in for landscape photography). */
function FieldQuilt() {
  const tiles = ['#e6ecd5', '#fceace', '#c3cda7', '#b2cee7', '#e6ecd5', '#f1efdf', '#c3cda7', '#fceace', '#e6ecd5', '#c3cda7', '#b2cee7', '#e6ecd5']
  const cells = Array.from({ length: 48 }, (_, i) => tiles[(i * 7 + (i % 5)) % tiles.length])
  return (
    <div aria-hidden className="absolute inset-0 grid grid-cols-8 gap-[6px] p-[6px] opacity-[0.22] [transform:perspective(900px)_rotateX(28deg)_scale(1.35)] [transform-origin:50%_100%]">
      {cells.map((c, i) => <div key={i} className="rounded-[14px]" style={{ background: c, gridColumn: i % 9 === 0 ? 'span 2' : undefined }} />)}
    </div>
  )
}

export default function Home() {
  const { t } = useI18n()
  const { profile } = useProfile()
  const cards = [
    { icon: Satellite, title: t('how_1t'), body: t('how_1'), bg: 'bg-sky' },
    { icon: CloudRain, title: t('how_2t'), body: t('how_2'), bg: 'bg-peach' },
    { icon: Droplets, title: t('how_3t'), body: t('how_3'), bg: 'bg-sage' },
  ]
  return (
    <>
      <section className="relative isolate overflow-hidden bg-forest text-white">
        <FieldQuilt />
        <div className="relative mx-auto flex min-h-[78vh] max-w-[1200px] flex-col items-center justify-center px-4 py-24 text-center">
          <p className="eyebrow mb-5 !text-lime">{t('tagline')}</p>
          <h1 className="max-w-[16ch] text-[44px] leading-[1.04] md:text-[64px] lg:text-[72px]">{t('hero_title')}</h1>
          <p className="mt-6 max-w-[56ch] text-[17px] text-white/85">{t('hero_body')}</p>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <Link to={profile ? '/my-farm' : '/onboarding'} className="btn bg-lime text-ink hover:bg-white">{profile ? t('nav_myfarm') : t('im_farmer')}</Link>
            <Link to="/monitor" className="btn-ghost-light">{t('explore')}</Link>
          </div>
          <a href="#how" className="absolute bottom-6 flex items-center gap-1.5 text-[13px] text-white/75 hover:text-white">{t('scroll')} <ArrowDown size={14} /></a>
        </div>
      </section>

      <section id="how" className="py-[50px] md:py-20">
        <Container>
          <h2 className="mb-10 text-[37px] md:text-[45px]">{t('how_title')}</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {cards.map(({ icon: Icon, title, body, bg }) => (
              <div key={title} className={`rounded-[20px] ${bg} p-[30px]`}>
                <span className="grid h-10 w-10 place-items-center rounded-full bg-white"><Icon size={18} strokeWidth={1.5} /></span>
                <h3 className="mt-5 text-[24px]">{title}</h3>
                <p className="mt-2 text-[15px] text-graphite">{body}</p>
              </div>
            ))}
          </div>
        </Container>
      </section>

      <section className="bg-forest py-16 text-white md:py-20">
        <Container className="grid items-center gap-10 md:grid-cols-[1.2fr_1fr]">
          <div>
            <h2 className="text-[37px] md:text-[45px]">{t('how_4t')}</h2>
            <p className="mt-4 max-w-[60ch] text-[17px] text-white/85">{t('how_4')}</p>
          </div>
          <div className="flex items-start gap-4 rounded-[20px] bg-white/10 p-[30px]">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-white text-forest"><ShieldCheck size={18} /></span>
            <p className="text-[15px] text-white/85">{t('footer_note')}</p>
          </div>
        </Container>
      </section>
    </>
  )
}
