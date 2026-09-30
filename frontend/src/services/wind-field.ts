import { transform } from 'ol/proj'
import type Map from 'ol/Map'
import Feature from 'ol/Feature'
import LineString from 'ol/geom/LineString'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import { Style, Stroke } from 'ol/style'
import { EnvironmentFeaturePool } from './environment-feature-pool'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
export interface WindVector {
  id: string
  available?: boolean
  latitude: number
  longitude: number
  timestamp: string
  u10: number
  v10: number
  wind_speed: number
  wind_direction_math: number
  wind_direction_meteorological: number
  source: string
}
export interface WindField { requested_time: string; matched_time: string; vectors: WindVector[] }
export function sampleViewport(map: Map, time: Date, spacing = 110, signal?: AbortSignal): Promise<WindField> {
  const size = map.getSize() ?? [1000, 700]
  const points: { id: string; lat: number; lon: number }[] = []
  for (let y = spacing / 2; y < size[1]; y += spacing) for (let x = spacing / 2; x < size[0]; x += spacing) {
    const coordinate = map.getCoordinateFromPixel([x, y]); if (!coordinate) continue
    const [lon, lat] = transform(coordinate, map.getView().getProjection(), 'EPSG:4326')
    if (lat >= 30 && lat <= 90) points.push({ id: `${x}-${y}`, lat, lon })
  }
  return fetch(`${apiBaseUrl}/api/environment/wind/field`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ time: time.toISOString(), points }), signal })
    .then(async response => { if (!response.ok) throw new Error('当前环境时间无可用风场数据'); return response.json() })
}

const WIND_STYLES = {
  normal: new Style({ stroke: new Stroke({ color: '#d7eef2', width: 2 }) }),
  strong: new Style({ stroke: new Stroke({ color: '#e07a3f', width: 2 }) }),
}

export function updateWindFeaturePool(pool: EnvironmentFeaturePool<WindVector>, map: Map, field: WindField): number {
  return pool.update(field.vectors, (feature, vector) => {
    if (vector.available === false || vector.wind_speed < 0.2) return false
    if (![vector.longitude, vector.latitude, vector.u10, vector.v10, vector.wind_speed].every(Number.isFinite)) return false
    const start = transform([vector.longitude, vector.latitude], 'EPSG:4326', map.getView().getProjection())
    const length = Math.max(18, Math.min(42, 16 + vector.wind_speed * 2)) * (map.getView().getResolution() ?? 1)
    const endGeo: [number, number] = [vector.longitude + vector.u10 / Math.max(1, Math.cos(vector.latitude * Math.PI / 180)) * 0.08, vector.latitude + vector.v10 * 0.08]
    const end = transform(endGeo, 'EPSG:4326', map.getView().getProjection())
    const dx = end[0] - start[0], dy = end[1] - start[1], scale = length / Math.max(1, Math.hypot(dx, dy))
    const tip: [number, number] = [start[0] + dx * scale, start[1] + dy * scale]
    const angle = Math.atan2(dy, dx), wing = Math.PI / 7
    const left: [number, number] = [tip[0] - length * 0.28 * Math.cos(angle - wing), tip[1] - length * 0.28 * Math.sin(angle - wing)]
    const right: [number, number] = [tip[0] - length * 0.28 * Math.cos(angle + wing), tip[1] - length * 0.28 * Math.sin(angle + wing)]
    const coordinates = [start, tip, left, tip, right]
    const geometry = feature.getGeometry()
    if (geometry instanceof LineString) geometry.setCoordinates(coordinates)
    else feature.setGeometry(new LineString(coordinates))
    feature.setProperties(vector, true)
    feature.setStyle(vector.wind_speed > 12 ? WIND_STYLES.strong : WIND_STYLES.normal)
    feature.changed()
    return true
  })
}

export function createWindVectorLayer(map: Map, field: { vectors: WindVector[] }): VectorLayer<VectorSource> {
  const pool = new EnvironmentFeaturePool<WindVector>()
  updateWindFeaturePool(pool, map, { requested_time: '', matched_time: '', vectors: field.vectors })
  return new VectorLayer({ source: new VectorSource({ features: pool.source.getFeatures().filter((feature) => feature.getGeometry() !== undefined) }), zIndex: 5 })
}
