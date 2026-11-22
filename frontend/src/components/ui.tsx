import type { ReactNode } from 'react'
import { AlertTriangle, Clock, FlaskConical, Satellite, Sparkles } from 'lucide-react'
import { useI18n } from '../lib/i18n'
import type { Bin } from '../lib/scales'

export function Container({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-[1200px] px-4 md:px-6 ${className}`}>{children}</div>
}

export function SectionHeader({ eyebrow, title, intro, action }: { eyebrow?: string; title: string; intro?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-[60ch]">
        {eyebrow && <p className="eyebrow rise mb-2">{eyebrow}</p>}
        <h1 className="rise text-[37px] [animation-delay:80ms] md:text-[45px]">{title}</h1>
        {intro && <p className="rise mt-3 text-[17px] text-graphite [animation-delay:160ms]">{intro}</p>}
      </div>
      {action}
    </div>
  )
}

/** Labels the nature of a number: observed / estimate / provisional / forecast. Never colour-only. */
export function NatureBadge({ kind }: { kind: 'observed' | 'estimate' | 'provisional' | 'forecast' | 'final' | string }) {
  const { t } = useI18n()
  if (kind === 'estimate') return <span className="badge bg-sky/60 text-ink"><Sparkles size={12} /> {t('estimate')}</span>
  if (kind === 'provisional') return <span className="badge bg-peach text-ink"><Clock size={12} /> {t('provisional')}</span>
  if (kind === 'forecast') return <span className="badge bg-sage text-ink"><Sparkles size={12} /> {t('forecast')}</span>
  return <span className="badge bg-ash text-graphite"><Satellite size={12} /> observed</span>
}

export function Swatch({ color, size = 14 }: { color: string; size?: number }) {
  return <span aria-hidden className="inline-block shrink-0 rounded-[4px] ring-1 ring-black/10" style={{ background: color, width: size, height: size }} />
}

export function BinPill({ bin }: { bin: Bin | null }) {
  const { lang, t } = useI18n()
  if (!bin) return <span className="badge bg-ash text-pewter">{t('no_data')}</span>
  return (
    <span className="badge" style={{ background: bin.color, color: bin.textDark ? '#212529' : '#ffffff' }}>
      {lang === 'mr' ? bin.label_mr : bin.label}
    </span>
  )
}

export function Legend({ bins, title }: { bins: Bin[]; title?: string }) {
  const { lang, t } = useI18n()
  return (
    <div>
      <p className="eyebrow mb-2">{title ?? t('legend')}</p>
      <ul className="flex flex-col gap-1.5 text-[13px] text-graphite">
        {bins.map((b) => (
          <li key={b.key} className="flex items-center gap-2"><Swatch color={b.color} /> {lang === 'mr' ? b.label_mr : b.label}</li>
        ))}
        <li className="flex items-center gap-2"><Swatch color="#ffffff" /> {t('no_data')}</li>
      </ul>
    </div>
  )
}

export function Loading({ label }: { label?: string }) {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-3 py-10 text-pewter" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-moss border-t-forest" /> {label ?? t('loading')}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n()
  return (
    <div className="card flex flex-wrap items-center gap-3 border border-dry-1 text-[15px]" role="alert">
      <AlertTriangle size={18} className="text-dry-2" /> <span className="font-medium">{t('error')}</span>
      <span className="text-pewter">{error instanceof Error ? error.message : String(error)}</span>
      {onRetry && <button className="btn-ghost ml-auto !py-1.5" onClick={onRetry}>{t('retry')}</button>}
    </div>
  )
}

export function MethodNote({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  return (
    <details className="group rounded-[20px] bg-ash/70 px-5 py-3 text-[14px] text-graphite">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-ink">
        <FlaskConical size={16} strokeWidth={1.75} /> {t('methods')}
        <span className="ml-auto text-pewter transition-transform group-open:rotate-180">⌄</span>
      </summary>
      <div className="mt-2 space-y-2 leading-relaxed">{children}</div>
    </details>
  )
}

export function Stat({ label, value, sub, tone = 'white' }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'white' | 'sky' | 'peach' | 'sage' | 'ash' }) {
  const bg = { white: 'bg-white', sky: 'bg-sky', peach: 'bg-peach', sage: 'bg-sage', ash: 'bg-ash' }[tone]
  return (
    <div className={`rounded-[20px] ${bg} p-6`}>
      <p className="text-[13px] font-medium text-graphite">{label}</p>
      <div className="mt-2 font-serif text-[37px] font-light leading-none text-ink">{value}</div>
      {sub && <div className="mt-3 text-[13px] text-graphite">{sub}</div>}
    </div>
  )
}
