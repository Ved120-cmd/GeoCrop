import { useEffect, useMemo } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L, { type LatLngBoundsExpression, type PathOptions } from 'leaflet'
import { useQuery } from '@tanstack/react-query'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { api } from '../lib/api'

export interface DistrictProps { district_id: number; district: string; region: string; region_mr: string; subregion: string; division: string }
export type DistrictsFC = FeatureCollection<Geometry, DistrictProps>

export function useDistrictGeo() {
  return useQuery({ queryKey: ['geo-districts'], queryFn: () => api.get<DistrictsFC>('/geo/districts'), staleTime: Infinity })
}

const MH_BOUNDS: LatLngBoundsExpression = [[15.6, 72.6], [22.1, 80.9]]

/** Leaflet caches its container size; if the map mounts while hidden (size 0) clicks and fitBounds break.
 *  Re-measure whenever the container is resized, then let `onResize` re-fit the view. */
function AutoResize({ onResize }: { onResize?: () => void }) {
  const map = useMap()
  useEffect(() => {
    const el = map.getContainer()
    const ro = new ResizeObserver(() => { map.invalidateSize(); onResize?.() })
    ro.observe(el)
    return () => ro.disconnect()
  }, [map, onResize])
  return null
}

function FitTo({ fc, ids }: { fc: DistrictsFC; ids?: number[] }) {
  const map = useMap()
  const fit = useMemo(() => () => {
    const feats = ids?.length ? fc.features.filter((f) => ids.includes(f.properties.district_id)) : fc.features
    const b = L.geoJSON({ type: 'FeatureCollection', features: feats } as FeatureCollection).getBounds()
    if (b.isValid() && map.getSize().x > 0) map.fitBounds(b, { padding: [16, 16] })
  }, [fc, ids?.join(','), map]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fit() }, [fit])
  return <AutoResize onResize={fit} />
}

/** Choropleth of the 36 districts. Colour comes from `colorFor`; identity is also in the tooltip and lists. */
export function DistrictChoropleth({
  fc, colorFor, tooltipFor, onSelect, focusIds, selectedId, height = 520,
}: {
  fc: DistrictsFC
  colorFor: (id: number) => string
  tooltipFor: (id: number, name: string) => string
  onSelect?: (id: number) => void
  focusIds?: number[]
  selectedId?: number
  height?: number
}) {
  const styleKey = useMemo(() => fc.features.map((f) => colorFor(f.properties.district_id)).join('|') + (focusIds ?? []).join(',') + selectedId, [fc, colorFor, focusIds, selectedId])
  const style = (f?: Feature<Geometry, DistrictProps>): PathOptions => {
    const id = f!.properties.district_id
    const dim = focusIds?.length ? !focusIds.includes(id) : false
    return {
      fillColor: colorFor(id), fillOpacity: dim ? 0.25 : 1,
      color: id === selectedId ? '#07503f' : '#ffffff', weight: id === selectedId ? 3 : 1.5, opacity: 1,
    }
  }
  return (
    <MapContainer bounds={MH_BOUNDS} style={{ height }} scrollWheelZoom={false} zoomSnap={0.25} attributionControl={false} className="w-full">
      <GeoJSON
        key={styleKey}
        data={fc}
        style={style as never}
        onEachFeature={(f, layer) => {
          const p = (f as Feature<Geometry, DistrictProps>).properties
          layer.bindTooltip(tooltipFor(p.district_id, p.district), { sticky: true, direction: 'top' })
          layer.on({
            click: () => onSelect?.(p.district_id),
            mouseover: (e) => (e.target as L.Path).setStyle({ weight: 3, color: '#212529' }),
            mouseout: (e) => (e.target as L.Path).setStyle({ weight: p.district_id === selectedId ? 3 : 1.5, color: p.district_id === selectedId ? '#07503f' : '#ffffff' }),
            keypress: () => onSelect?.(p.district_id),
          })
        }}
      />
      <FitTo fc={fc} ids={focusIds} />
    </MapContainer>
  )
}

function ClickToPin({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(+e.latlng.lat.toFixed(5), +e.latlng.lng.toFixed(5)) })
  return null
}

function FlyTo({ lat, lon, bounds }: { lat?: number | null; lon?: number | null; bounds?: L.LatLngBounds | null }) {
  const map = useMap()
  const go = useMemo(() => (animate: boolean) => {
    if (map.getSize().x === 0) return
    if (lat != null && lon != null) map.setView([lat, lon], Math.max(map.getZoom(), 12), { animate })
    else if (bounds?.isValid()) map.fitBounds(bounds, { padding: [12, 12], animate })
  }, [lat, lon, bounds, map])
  useEffect(() => { go(true) }, [go])
  const onResize = useMemo(() => () => go(false), [go])
  return <AutoResize onResize={onResize} />
}

/** Farm pin picker on an OpenStreetMap basemap, with the chosen district outlined. */
export function PinMap({ fc, districtId, lat, lon, onPick, height = 380 }: {
  fc?: DistrictsFC; districtId?: number; lat?: number | null; lon?: number | null; onPick: (lat: number, lon: number) => void; height?: number
}) {
  const feat = fc?.features.find((f) => f.properties.district_id === districtId)
  const bounds = useMemo(() => (feat ? L.geoJSON(feat as never).getBounds() : null), [feat])
  return (
    <MapContainer bounds={MH_BOUNDS} style={{ height }} className="w-full">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={18}
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      {feat && <GeoJSON key={districtId} data={feat as never} style={{ color: '#07503f', weight: 2.5, fillOpacity: 0.06, fillColor: '#07503f' }} interactive={false} />}
      {lat != null && lon != null && <CircleMarker center={[lat, lon]} radius={10} pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#07503f', fillOpacity: 1 }} />}
      <ClickToPin onPick={onPick} />
      <FlyTo lat={lat} lon={lon} bounds={bounds} />
    </MapContainer>
  )
}
