import Feature from 'ol/Feature'
import LineString from 'ol/geom/LineString'
import VectorLayer from 'ol/layer/Vector'
import type Map from 'ol/Map'
import { transform } from 'ol/proj'
import VectorSource from 'ol/source/Vector'
import { Stroke, Style } from 'ol/style'
import { EnvironmentFeaturePool } from './environment-feature-pool'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
export const MIN_VISIBLE_CURRENT_SPEED = 0.01

export interface CurrentVector {
  id: string
  available: true
  latitude: number
  longitude: number
  timestamp: string
  vxo: number
  vyo: number
  current_east: number
  current_north: number
  current_speed: number
  current_direction_to: number
  source: string
  detided: boolean
}

export interface UnavailableCurrentPoint {
  id: string
  available: false
  latitude: number
  longitude: number
  reason: 'no_data' | 'out_of_coverage'
}

export interface CurrentField {
  requested_time: string
  matched_time: string
  source: string
  units: string
  detided: boolean
  currents: Array<CurrentVector | UnavailableCurrentPoint>
}

export async function sampleCurrentViewport(
  map: Map,
  time: Date,
  spacing = 100,
  signal?: AbortSignal,
): Promise<CurrentField> {
  const size = map.getSize() ?? [1000, 700]
  const points: { id: string; lat: number; lon: number }[] = []
  for (let y = spacing / 2; y < size[1]; y += spacing) {
    for (let x = spacing / 2; x < size[0]; x += spacing) {
      const coordinate = map.getCoordinateFromPixel([x, y])
      if (!coordinate) continue
      const [lon, lat] = transform(coordinate, map.getView().getProjection(), 'EPSG:4326')
      if (Number.isFinite(lat) && Number.isFinite(lon) && lat >= 30 && lat <= 90) {
        points.push({ id: `${x}-${y}`, lat, lon: ((lon + 180) % 360 + 360) % 360 - 180 })
      }
    }
  }
  if (!points.length) throw new Error('当前视口不在北极海流数据覆盖范围内')
  const response = await fetch(`${apiBaseUrl}/api/environment/current/field`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time: time.toISOString(), points }),
    signal,
  })
  if (!response.ok) throw new Error('当前环境时间无可用海流数据')
  return response.json() as Promise<CurrentField>
}

const CURRENT_STYLES = {
  normal: new Style({ stroke: new Stroke({ color: '#34b6c8', width: 2.2 }) }),
  strong: new Style({ stroke: new Stroke({ color: '#00d9ff', width: 2.2 }) }),
}

export function updateCurrentFeaturePool(
  pool: EnvironmentFeaturePool<CurrentVector | UnavailableCurrentPoint>,
  map: Map,
  field: CurrentField,
): number {
  const projection = map.getView().getProjection()
  return pool.update(field.currents, (feature, current) => {
    if (!current.available || current.current_speed < MIN_VISIBLE_CURRENT_SPEED) return false
    if (![current.longitude, current.latitude, current.current_east, current.current_north].every(Number.isFinite)) return false
    const start = transform([current.longitude, current.latitude], 'EPSG:4326', projection)
    const speed = current.current_speed
    const latitudeRadians = current.latitude * Math.PI / 180
    const endGeo: [number, number] = [current.longitude + (current.current_east / speed) * 0.08 / Math.max(0.15, Math.cos(latitudeRadians)), current.latitude + (current.current_north / speed) * 0.08]
    const projectedEnd = transform(endGeo, 'EPSG:4326', projection)
    const dx = projectedEnd[0] - start[0], dy = projectedEnd[1] - start[1]
    if (!Number.isFinite(dx) || !Number.isFinite(dy) || Math.hypot(dx, dy) < 1e-9) return false
    const mapLength = Math.max(16, Math.min(38, 16 + speed * 30)) * (map.getView().getResolution() ?? 1)
    const scale = mapLength / Math.hypot(dx, dy)
    const tip: [number, number] = [start[0] + dx * scale, start[1] + dy * scale]
    const angle = Math.atan2(dy, dx), wing = Math.PI / 7
    const left: [number, number] = [tip[0] - mapLength * 0.30 * Math.cos(angle - wing), tip[1] - mapLength * 0.30 * Math.sin(angle - wing)]
    const right: [number, number] = [tip[0] - mapLength * 0.30 * Math.cos(angle + wing), tip[1] - mapLength * 0.30 * Math.sin(angle + wing)]
    const geometry = feature.getGeometry()
    const coordinates = [start, tip, left, tip, right]
    if (geometry instanceof LineString) geometry.setCoordinates(coordinates)
    else feature.setGeometry(new LineString(coordinates))
    feature.setProperties(current, true)
    feature.setStyle(speed >= 0.5 ? CURRENT_STYLES.strong : CURRENT_STYLES.normal)
    feature.changed()
    return true
  })
}

export function createCurrentVectorLayer(map: Map, field: CurrentField): VectorLayer<VectorSource> {
  const pool = new EnvironmentFeaturePool<CurrentVector | UnavailableCurrentPoint>()
  updateCurrentFeaturePool(pool, map, field)
  return new VectorLayer({ source: new VectorSource({ features: pool.source.getFeatures().filter((feature) => feature.getGeometry() !== undefined) }), zIndex: 6 })
}
