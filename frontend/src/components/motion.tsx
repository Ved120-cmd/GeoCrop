/**
 * Small motion primitives. Quiet by design (the brand "whispers"): short fades and lifts, no bounce, no shadows.
 * Everything collapses to the final state when the user prefers reduced motion.
 */
import React, { createElement, useEffect, useRef, useState, type CSSProperties, type ElementType, type ReactNode } from 'react'

export function useReducedMotion() {
  const [r, setR] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const m = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!m) return
    const f = () => setR(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return r
}

/** Becomes true once the element has scrolled into view (and stays true). */
export function useInView<T extends Element>(rootMargin = '0px 0px -8% 0px') {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    if (!('IntersectionObserver' in window)) { setSeen(true); return }
    // An element counts as seen once it is in view OR has been scrolled past: a fast jump (Page Down, anchor link,
    // scroll restoration) can skip over it without the observer ever reporting an intersection.
    const reached = () => el.getBoundingClientRect().top < window.innerHeight * 0.95
    if (reached()) { setSeen(true); return }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting || reached()) done() }, { rootMargin })
    let raf = 0
    const onScroll = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { if (reached()) done() }) }
    function done() { setSeen(true); io.disconnect(); window.removeEventListener('scroll', onScroll) }
    io.observe(el)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => { io.disconnect(); window.removeEventListener('scroll', onScroll); cancelAnimationFrame(raf) }
  }, [seen, rootMargin])
  return [ref, seen] as const
}

/** Fade + rise into place when scrolled into view. `delay` (ms) staggers siblings. */
export function Reveal({ children, delay = 0, as = 'div', className = '', style, ...rest }: {
  children: ReactNode; delay?: number; as?: ElementType; className?: string; style?: CSSProperties; [attr: string]: unknown
}) {
  const [ref, seen] = useInView<HTMLElement>()
  return createElement(as, { ...rest, ref, className: `reveal ${seen ? 'reveal-in' : ''} ${className}`, style: { ...style, transitionDelay: seen ? `${delay}ms` : '0ms' } }, children)
}

/** Counts from 0 to `value` once visible (ease-out, ~1.2 s). Renders the final number for reduced motion / SSR. */
export function CountUp({ value, decimals = 0, duration = 1200, format }: { value: number; decimals?: number; duration?: number; format?: (n: number) => string }) {
  const reduced = useReducedMotion()
  const [ref, seen] = useInView<HTMLSpanElement>()
  const [n, setN] = useState(reduced ? value : 0)
  useEffect(() => {
    if (reduced || !seen) { if (reduced) setN(value); return }
    let raf = 0; const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration)
      setN(value * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, value, duration, reduced])
  const shown = format ? format(n) : n.toLocaleString('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals })
  return <span ref={ref} className="tabular-nums">{shown}</span>
}

/** A bar that grows to `pct` (0-100) once visible. */
export function GrowBar({ pct, color, className = '' }: { pct: number; color: string; className?: string }) {
  const [ref, seen] = useInView<HTMLSpanElement>()
  return (
    <span ref={ref} className={`block h-2 rounded-full bg-[#e9e7dd] ${className}`}>
      <span className="grow-bar block h-2 rounded-full" style={{ width: seen ? `${Math.max(0, Math.min(100, pct))}%` : '0%', background: color }} />
    </span>
  )
}

/** Card that tilts a few degrees toward the pointer (3D, no shadow). Touch devices and reduced motion: plain. */
export function Tilt({ children, className = '', max = 5, as = 'div', ...rest }: {
  children: ReactNode; className?: string; max?: number; as?: ElementType; [k: string]: unknown
}) {
  const reduced = useReducedMotion()
  const ref = useRef<HTMLElement>(null)
  const onMove = (e: React.PointerEvent) => {
    if (reduced || e.pointerType !== 'mouse' || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5
    ref.current.style.setProperty('--ry', `${(x * max).toFixed(2)}deg`)
    ref.current.style.setProperty('--rx', `${(-y * max).toFixed(2)}deg`)
    ref.current.style.setProperty('--ty', '-4px')
  }
  const reset = () => { if (!ref.current) return; ['--rx', '--ry', '--ty'].forEach((p) => ref.current!.style.removeProperty(p)) }
  return createElement(as, { ref, className: `tilt ${className}`, onPointerMove: onMove, onPointerLeave: reset, ...rest }, children)
}
