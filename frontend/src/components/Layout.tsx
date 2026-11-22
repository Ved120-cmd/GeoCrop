import { useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Menu, X, CircleCheck, UserRound } from 'lucide-react'
import { api, type Overview } from '../lib/api'
import { useI18n, type TKey } from '../lib/i18n'
import { useProfile } from '../lib/profile'

export const NAV: { to: string; label: TKey }[] = [
  { to: '/monitor', label: 'nav_monitor' },
  { to: '/predict', label: 'nav_predict' },
  { to: '/soil', label: 'nav_soil' },
  { to: '/crop-advisor', label: 'nav_advisor' },
  { to: '/plant-doctor', label: 'nav_doctor' },
  { to: '/simulator', label: 'nav_sim' },
]

export function Logo({ light = true }: { light?: boolean }) {
  return (
    <Link to="/" className={`flex items-center gap-2 ${light ? 'text-white' : 'text-forest'}`} aria-label="GeoCrop home">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 3 L29 27 H3 Z" fill="#e8fe85" />
        <path d="M16 11 L23 24 H9 Z" fill="#07503f" />
      </svg>
      <span className="font-serif text-[26px] font-light leading-none tracking-[-0.02em]">geocrop</span>
    </Link>
  )
}

function LangToggle() {
  const { lang, setLang } = useI18n()
  return (
    <div className="flex rounded-[100px] bg-white/10 p-0.5 text-[13px]" role="group" aria-label="Language">
      {(['en', 'mr'] as const).map((l) => (
        <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
          className={`rounded-[100px] px-3 py-1 font-medium transition-colors ${lang === l ? 'bg-white text-ink' : 'text-white hover:bg-white/10'}`}>
          {l === 'en' ? 'EN' : 'मराठी'}
        </button>
      ))}
    </div>
  )
}

function Marquee() {
  const { t, lang } = useI18n()
  const { data } = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/monitor/overview') })
  const items: string[] = []
  if (data) {
    const n = data.districts.filter((d) => ['moderate', 'severe'].includes(d.indicators.stress_today?.stress ?? '')).length
    items.push(`${n} / 36 ${t('alerts')}`)
    const s = data.freshness?.sources ?? {}
    const mr = lang === 'mr'
    const lbl: Record<string, string> = mr
      ? { SMAP: 'मातीतील ओलावा', IMERG: 'उपग्रह पाऊस', MOD13Q1: 'वनस्पती (NDVI)', MOD11A2: 'जमिनीचे तापमान', MOD16A2: 'बाष्पीभवन' }
      : { SMAP: 'Soil moisture', IMERG: 'Satellite rain', MOD13Q1: 'Vegetation (NDVI)', MOD11A2: 'Land temperature', MOD16A2: 'Evapotranspiration' }
    for (const [k, v] of Object.entries(s)) if (lbl[k]) items.push(`${lbl[k]} ${t('as_of')} ${v.latest}${v.status_latest === 'provisional' ? ` (${t('provisional')})` : ''}`)
  } else items.push(t('tagline'))
  const row = items.concat(items)
  return (
    <div className="overflow-hidden bg-lime text-[13px] text-ink" aria-label={t('data_freshness')}>
      <div className="marquee-track flex w-max gap-10 py-2 pl-6">
        {row.map((s, i) => (
          <span key={i} className="flex items-center gap-2 whitespace-nowrap" aria-hidden={i >= items.length}>
            <CircleCheck size={14} strokeWidth={1.5} /> {s}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const { profile } = useProfile()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `whitespace-nowrap rounded-[100px] px-3 py-1.5 text-[15px] transition-colors ${isActive ? 'bg-white/15 text-white' : 'text-white/85 hover:text-white'}`

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
      <Marquee />
      <header className="sticky top-0 z-[1000] bg-forest">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between gap-4 px-4 md:px-6">
          <Logo />
          <nav className="hidden items-center gap-0.5 xl:flex" aria-label="Main">
            {NAV.map((n) => <NavLink key={n.to} to={n.to} className={navCls}>{t(n.label)}</NavLink>)}
          </nav>
          <div className="flex items-center gap-2">
            <div className="hidden sm:block"><LangToggle /></div>
            <Link to={profile ? '/my-farm' : '/onboarding'} className="btn-white hidden whitespace-nowrap !px-4 !py-2 sm:inline-flex">
              <UserRound size={16} strokeWidth={1.75} /> {profile ? t('nav_myfarm') : t('im_farmer')}
            </Link>
            <button className="rounded-full p-2 text-white xl:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? t('close') : t('menu')}>
              {open ? <X /> : <Menu />}
            </button>
          </div>
        </div>
        {open && (
          <div className="border-t border-white/10 bg-forest px-4 pb-4 xl:hidden" onClick={() => setOpen(false)}>
            <nav className="flex flex-col gap-1 pt-2" aria-label="Mobile">
              {NAV.map((n) => <NavLink key={n.to} to={n.to} className={navCls}>{t(n.label)}</NavLink>)}
              <NavLink to={profile ? '/my-farm' : '/onboarding'} className={navCls}>{profile ? t('nav_myfarm') : t('im_farmer')}</NavLink>
            </nav>
            <div className="mt-3" onClick={(e) => e.stopPropagation()}><LangToggle /></div>
          </div>
        )}
      </header>
      <main id="main" key={loc.pathname} className="page-enter flex-1">{children}</main>
      <Footer />
    </div>
  )
}

function Footer() {
  const { t, lang } = useI18n()
  return (
    <footer className="mt-16 bg-forest text-white">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-14 md:grid-cols-[1.2fr_2fr] md:px-6">
        <div>
          <Logo />
          <p className="mt-4 max-w-[38ch] text-[15px] text-white/80">{t('tagline')}</p>
        </div>
        <div className="grid gap-8 sm:grid-cols-2">
          <ul className="space-y-2 text-[15px]">
            {NAV.map((n) => <li key={n.to}><Link className="text-white/85 hover:text-white" to={n.to}>{t(n.label)}</Link></li>)}
          </ul>
          <div className="space-y-3 text-[13px] text-white/75">
            <p>{t('footer_data')}</p>
            <p>{t('footer_note')}</p>
            {lang === 'mr' && <p className="text-lime">{t('mr_review')}</p>}
          </div>
        </div>
      </div>
    </footer>
  )
}
