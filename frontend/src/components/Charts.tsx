import type { ReactNode } from 'react'
import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Chart chrome per the dataviz method: recessive grid/axes, 2px lines, text in ink tokens, one axis per chart.
const AXIS = { stroke: '#c3c2b7', tick: { fill: '#6d6d6d', fontSize: 12 }, tickLine: false }
const GRID = <CartesianGrid stroke="#e1e0d9" strokeDasharray="0" vertical={false} />
const TT = {
  contentStyle: { background: '#212529', border: 0, borderRadius: 12, color: '#fff', fontSize: 13, padding: '8px 12px' },
  labelStyle: { color: '#e8fe85', marginBottom: 4 }, itemStyle: { color: '#fff', padding: 0 }, cursor: { stroke: '#6d6d6d', strokeWidth: 1 },
}
const fmtDate = (s: string) => { const d = new Date(s); return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) }
export const FOREST = '#07503f'
export const NORMAL = '#898781'

export function ChartCard({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <figure className="card !p-6">
      <figcaption className="mb-4">
        <h3 className="font-sans text-[16px] font-semibold tracking-normal">{title}</h3>
        {subtitle && <div className="mt-1 text-[13px] text-pewter">{subtitle}</div>}
      </figcaption>
      {children}
      {footer && <div className="mt-3 text-[13px] text-pewter">{footer}</div>}
    </figure>
  )
}

/** Two series vs date: "this year" (forest, solid) and "normal" (grey, dashed). */
export function ThisYearVsNormal({ data, x, y, yNormal, labels, yDomain, unit = '' }: {
  data: Record<string, unknown>[]; x: string; y: string; yNormal: string; labels: [string, string]; yDomain?: [number, number]; unit?: string
}) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        {GRID}
        <XAxis dataKey={x} tickFormatter={fmtDate} {...AXIS} minTickGap={28} />
        <YAxis domain={yDomain ?? ['auto', 'auto']} {...AXIS} width={52} tickFormatter={(v) => `${v}${unit}`} />
        <Tooltip {...TT} labelFormatter={(l) => fmtDate(String(l))} formatter={(v: number) => (v == null ? '–' : `${Number(v).toFixed(unit === '%' ? 0 : 2)}${unit}`)} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 13, color: '#353535' }} />
        <Line type="monotone" dataKey={yNormal} name={labels[1]} stroke={NORMAL} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
        <Line type="monotone" dataKey={y} name={labels[0]} stroke={FOREST} strokeWidth={2} dot={{ r: 3, fill: FOREST, strokeWidth: 0 }} activeDot={{ r: 5 }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Percentile line over shaded dry/normal/wet bands. */
export function PercentileChart({ data, x, y, name }: { data: Record<string, unknown>[]; x: string; y: string; name: string }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <ReferenceArea y1={0} y2={10} fill="#eda07a" fillOpacity={0.25} />
        <ReferenceArea y1={10} y2={30} fill="#eda07a" fillOpacity={0.12} />
        <ReferenceArea y1={70} y2={100} fill="#86b6ef" fillOpacity={0.15} />
        {GRID}
        <XAxis dataKey={x} tickFormatter={fmtDate} {...AXIS} minTickGap={28} />
        <YAxis domain={[0, 100]} ticks={[0, 10, 30, 50, 70, 90, 100]} {...AXIS} width={44} />
        <Tooltip {...TT} labelFormatter={(l) => fmtDate(String(l))} formatter={(v: number) => (v == null ? '–' : `${Number(v).toFixed(0)}th percentile`)} />
        <Line type="monotone" dataKey={y} name={name} stroke={FOREST} strokeWidth={2} dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Depletion % over the next days: observed/gap-filled solid, forecast dashed; stress threshold marked. */
export function DepletionChart({ data, threshold, labels }: {
  data: { date: string; depletion_pct?: number | null; kind?: string }[]; threshold?: number; labels: { obs: string; fc: string; thr: string }
}) {
  // Only days with weather are plotted. "Observed" = observed or climatology gap-filled weather; the forecast segment
  // starts at the last observed point so the two lines join. Lines never bridge missing values.
  const isObs = (k?: string) => k === 'observed' || k === 'gap-filled'
  const rows = data.filter((d) => d.kind).map((d, i, arr) => {
    const fc = d.kind === 'forecast'
    const nextFc = arr[i + 1]?.kind === 'forecast'
    return { date: d.date, obs: isObs(d.kind) ? d.depletion_pct : null, fc: fc || (isObs(d.kind) && nextFc) ? d.depletion_pct : null }
  })
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        {GRID}
        <XAxis dataKey="date" tickFormatter={fmtDate} {...AXIS} minTickGap={20} />
        <YAxis domain={[0, 100]} {...AXIS} width={56} tickFormatter={(v) => `${v}%`} />
        {threshold != null && <ReferenceLine y={threshold} stroke="#9e3f1e" strokeDasharray="4 4" label={{ value: labels.thr, position: 'insideTopLeft', fill: '#9e3f1e', fontSize: 12 }} />}
        <Tooltip {...TT} labelFormatter={(l) => fmtDate(String(l))} formatter={(v: number) => (v == null ? '–' : `${Number(v).toFixed(0)}%`)} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 13, color: '#353535' }} />
        <Area type="monotone" dataKey="obs" name={labels.obs} stroke={FOREST} strokeWidth={2} fill={FOREST} fillOpacity={0.08} />
        <Line type="monotone" dataKey="fc" name={labels.fc} stroke={FOREST} strokeWidth={2} strokeDasharray="5 4" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Daily rain bars (single series). */
export function RainBars({ data, name }: { data: { date: string; rain_mm?: number | null }[]; name: string }) {
  return (
    <ResponsiveContainer width="100%" height={120}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
        {GRID}
        <XAxis dataKey="date" tickFormatter={fmtDate} {...AXIS} minTickGap={20} />
        <YAxis {...AXIS} width={48} tickFormatter={(v) => `${v}`} allowDecimals={false} />
        <Tooltip {...TT} labelFormatter={(l) => fmtDate(String(l))} formatter={(v: number) => `${Number(v ?? 0).toFixed(1)} mm`} />
        <Bar dataKey="rain_mm" name={name} fill="#3987e5" radius={[4, 4, 0, 0]} maxBarSize={18} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
