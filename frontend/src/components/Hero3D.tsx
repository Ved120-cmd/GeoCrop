/**
 * 3D Maharashtra: every district extruded from its real boundary, height and colour = today's
 * water-stress ESTIMATE (same scale as Monitor). Districts rise in a ripple from the centre, the map sways gently,
 * hovering lifts a district and names it, clicking opens it in Monitor.
 * Loaded lazily (three.js is heavy) and paused when off-screen; static when the user prefers reduced motion.
 */
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as THREE from 'three'
import type { Polygon, Position } from 'geojson'
import { api, type Overview } from '../lib/api'
import { useDistrictGeo } from './Maps'
import { STRESS_BINS, stressBin } from '../lib/scales'
import { pick, useI18n } from '../lib/i18n'

const HEIGHT: Record<string, number> = { none: 0.1, mild: 0.24, moderate: 0.4, severe: 0.6 }
const LON0 = 76.75, LAT0 = 18.85, SCALE = 0.98, KX = Math.cos((LAT0 * Math.PI) / 180)
const project = ([lon, lat]: Position) => new THREE.Vector2((lon - LON0) * KX * SCALE, (lat - LAT0) * SCALE)

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function webglAvailable() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch {
    return false
  }
}

function shapesFor(geom: Polygon | { type: 'MultiPolygon'; coordinates: Position[][][] }) {
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates
  return polys.map((rings) => {
    const s = new THREE.Shape(rings[0].map(project))
    rings.slice(1).forEach((h) => s.holes.push(new THREE.Path(h.map(project))))
    return s
  })
}

/** Line segments around the top face (z = 1 before the per-district height scale). */
function topOutline(shapes: THREE.Shape[]) {
  const pts: number[] = []
  for (const s of shapes) {
    for (const ring of [s.getPoints(), ...s.holes.map((h) => h.getPoints())]) {
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i], b = ring[(i + 1) % ring.length]
        pts.push(a.x, a.y, 1.001, b.x, b.y, 1.001)
      }
    }
  }
  return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
}

interface DistrictMesh { id: number; name: string; stress: string | null; geometry: THREE.ExtrudeGeometry; outline: THREE.BufferGeometry; delay: number; color: string; h: number }

function District({ d, hovered, onHover, onPick, start, still }: {
  d: DistrictMesh; hovered: boolean; onHover: (id: number | null, e?: ThreeEvent<PointerEvent>) => void; onPick: (id: number) => void; start: number; still: boolean
}) {
  const g = useRef<THREE.Group>(null)
  const mat = useRef<THREE.MeshStandardMaterial>(null)
  const base = useMemo(() => new THREE.Color(d.color), [d.color])
  const light = useMemo(() => new THREE.Color(d.color).lerp(new THREE.Color('#ffffff'), 0.35), [d.color])
  useFrame(({ clock }) => {
    if (!g.current) return
    const t = still ? 1 : Math.min(1, Math.max(0, (clock.elapsedTime - start - d.delay) / 1.1))
    const ease = 1 - Math.pow(1 - t, 3)
    g.current.scale.z = Math.max(0.001, ease * d.h)
    const lift = hovered ? 0.12 : 0
    g.current.position.z += (lift - g.current.position.z) * 0.18
    mat.current?.color.lerp(hovered ? light : base, 0.2)
  })
  return (
    <group ref={g}>
      <mesh geometry={d.geometry} onPointerOver={(e) => { e.stopPropagation(); onHover(d.id, e) }} onPointerMove={(e) => onHover(d.id, e)}
        onPointerOut={() => onHover(null)} onClick={(e) => { e.stopPropagation(); onPick(d.id) }}>
        <meshStandardMaterial ref={mat} color={d.color} roughness={0.85} metalness={0} flatShading />
      </mesh>
      {/* outline of the district's top face only (side-wall edges of jagged borders look like noise) */}
      <lineSegments geometry={d.outline}>
        <lineBasicMaterial color="#f1efdf" transparent opacity={0.7} />
      </lineSegments>
    </group>
  )
}

function Scene({ districts, hovered, setHovered, still }: { districts: DistrictMesh[]; hovered: number | null; setHovered: (id: number | null, e?: ThreeEvent<PointerEvent>) => void; still: boolean }) {
  const nav = useNavigate()
  const root = useRef<THREE.Group>(null)
  useFrame(({ clock }) => {
    if (root.current && !still) root.current.rotation.z = Math.sin(clock.elapsedTime * 0.18) * 0.16  // gentle sway
  })
  return (
    <group rotation={[-0.95, 0, 0]} position={[0, -0.25, 0]}>
      <group ref={root}>
        {districts.map((d) => (
          <District key={d.id} d={d} hovered={hovered === d.id} onHover={setHovered} onPick={(id) => nav(`/monitor/district/${id}`)} start={0.2} still={still} />
        ))}
      </group>
    </group>
  )
}

/** Move the camera back until the whole state (plus room for the sway) fits the canvas, at any aspect ratio. */
function FitCamera({ width = 8.8, height = 6.0 }: { width?: number; height?: number }) {
  const { camera, size } = useThree()
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const t = Math.tan(((cam.fov / 2) * Math.PI) / 180)
    const aspect = size.width / Math.max(size.height, 1)
    cam.position.set(0, 0, Math.max(width / 2 / (t * aspect), height / 2 / t))
    cam.updateProjectionMatrix()
  }, [camera, size, width, height])
  return null
}

class GLBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

export default function Hero3D({ fallback }: { fallback: ReactNode }) {
  const { lang } = useI18n()
  const geo = useDistrictGeo()
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/monitor/overview') })
  const wrap = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const [hover, setHover] = useState<{ id: number; x: number; y: number } | null>(null)
  const still = useMemo(prefersReducedMotion, [])
  const ok = useMemo(webglAvailable, [])

  useEffect(() => {  // pause rendering when the hero scrolls out of view (battery, CPU)
    if (!wrap.current) return
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 })
    io.observe(wrap.current)
    return () => io.disconnect()
  }, [])

  const districts = useMemo<DistrictMesh[]>(() => {
    if (!geo.data) return []
    const stress = new Map(ov.data?.districts.map((d) => [d.district_id, d.indicators.stress_today?.stress ?? null]) ?? [])
    return geo.data.features.map((f) => {
      const s = stress.get(f.properties.district_id) ?? null
      const shapes = shapesFor(f.geometry as Polygon)
      const geometry = new THREE.ExtrudeGeometry(shapes, { depth: 1, bevelEnabled: false })
      geometry.computeBoundingBox()
      const c = geometry.boundingBox!.getCenter(new THREE.Vector3())
      return { id: f.properties.district_id, name: f.properties.district, stress: s, geometry, outline: topOutline(shapes),
               delay: Math.hypot(c.x, c.y) * 0.32, color: stressBin(s)?.color ?? '#ffffff', h: s ? HEIGHT[s] ?? 0.16 : 0.1 }
    })
  }, [geo.data, ov.data])
  useEffect(() => () => districts.forEach((d) => { d.geometry.dispose(); d.outline.dispose() }), [districts])

  if (!ok) return <>{fallback}</>
  const hd = hover ? districts.find((d) => d.id === hover.id) : null
  const bin = hd ? stressBin(hd.stress) : null
  return (
    <div ref={wrap} className="relative h-full w-full" role="img"
      aria-label={pick(lang, 'Three-dimensional map of Maharashtra: each district is raised by its estimated water stress today.', 'महाराष्ट्राचा त्रिमितीय नकाशा: प्रत्येक जिल्ह्याची उंची आजच्या अंदाजित पाण्याच्या ताणानुसार.')}>
      <GLBoundary fallback={fallback}>
        {districts.length > 0 && (
          <Canvas frameloop={visible ? (still ? 'demand' : 'always') : 'never'} dpr={[1, 1.75]} camera={{ position: [0, 0, 10], fov: 40 }}
            gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }} onPointerMissed={() => setHover(null)}
            onPointerLeave={() => setHover(null)}>
            <FitCamera />
            <ambientLight intensity={1.35} />
            <directionalLight position={[-4, 8, 6]} intensity={1.6} />
            <directionalLight position={[5, -2, 4]} intensity={0.35} />
            <Scene districts={districts} hovered={hover?.id ?? null} still={still}
              setHovered={(id, e) => setHover(id === null || !e ? null : { id, x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })} />
          </Canvas>
        )}
      </GLBoundary>
      {hd && hover && (
        <div className="pointer-events-none absolute z-10 rounded-[12px] bg-ink px-3 py-2 text-[13px] text-white" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <p className="font-semibold">{hd.name}</p>
          <p className="text-white/80">{bin ? pick(lang, bin.label, bin.label_mr) : pick(lang, 'No estimate', 'अंदाज नाही')}</p>
        </div>
      )}
      <ul className="absolute bottom-2 left-1/2 flex -translate-x-1/2 flex-wrap justify-center gap-x-4 gap-y-1 text-[12px] text-white/85">
        {STRESS_BINS.map((b) => (
          <li key={b.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: b.color }} />{pick(lang, b.label, b.label_mr)}</li>
        ))}
      </ul>
    </div>
  )
}
