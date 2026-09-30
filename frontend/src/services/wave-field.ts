import Feature from 'ol/Feature'
import Polygon from 'ol/geom/Polygon'
import VectorLayer from 'ol/layer/Vector'
import type Map from 'ol/Map'
import { transform } from 'ol/proj'
import VectorSource from 'ol/source/Vector'
import { Fill, Stroke, Style } from 'ol/style'
import { EnvironmentFeaturePool } from './environment-feature-pool'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface WaveSample {
  id: string
  available: true
  timestamp: string
  requested_time: string
  matched_time: string
  latitude: number
  longitude: number
  wave_height: number
  wave_period: number
  wave_direction_from: number
  source: string
}

export interface UnavailableWaveSample {
  id: string
  available: false
  latitude: number
  longitude: number
  reason: 'no_data' | 'out_of_coverage'
}

export interface WaveField {
  requested_time: string
  matched_time: string
  source: string
  waves: Array<WaveSample | UnavailableWaveSample>
}

export async function sampleWaveViewport(
  map: Map,
  time: Date,
  spacing = 105,
  signal?: AbortSignal,
): Promise<WaveField> {
  const size = map.getSize() ?? [1000, 700]
  const points: { id: string; lat: number; lon: number }[] = []
  for (let y = spacing / 2; y < size[1]; y += spacing) {
    for (let x = spacing / 2; x < size[0]; x += spacing) {
      const coordinate = map.getCoordinateFromPixel([x, y])
      if (!coordinate) continue
      const [longitude, latitude] = transform(coordinate, map.getView().getProjection(), 'EPSG:4326')
      if (Number.isFinite(latitude) && Number.isFinite(longitude) && latitude >= 30 && latitude <= 90) {
        const normalizedLongitude = ((longitude + 180) % 360 + 360) % 360 - 180
        points.push({ id: `${x}-${y}`, lat: latitude, lon: normalizedLongitude })
      }
    }
  }
  if (!points.length) throw new Error('当前视口不在北极海浪数据覆盖范围内')
  const response = await fetch(`${apiBaseUrl}/api/environment/wave/field`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time: time.toISOString(), points }),
    signal,
  })
  if (!response.ok) throw new Error('当前环境时间无可用海浪数据')
  return response.json() as Promise<WaveField>
}

export const WAVE_HEIGHT_LEGEND = [
  { label: '0–1 m', level: '低', color: 'rgba(105, 174, 198, 0.40)' },
  { label: '1–2 m', level: '中低', color: 'rgba(70, 158, 151, 0.42)' },
  { label: '2–4 m', level: '中等', color: 'rgba(201, 181, 91, 0.43)' },
  { label: '4–6 m', level: '较高', color: 'rgba(207, 129, 70, 0.45)' },
  { label: '>6 m', level: '高', color: 'rgba(183, 78, 68, 0.47)' },
] as const

export function waveHeightColor(height: number): string {
  if (height < 1) return WAVE_HEIGHT_LEGEND[0].color
  if (height < 2) return WAVE_HEIGHT_LEGEND[1].color
  if (height < 4) return WAVE_HEIGHT_LEGEND[2].color
  if (height < 6) return WAVE_HEIGHT_LEGEND[3].color
  return WAVE_HEIGHT_LEGEND[4].color
}

function pixelFromId(id: string): [number, number] | undefined {
  const match = /^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/.exec(id)
  if (!match) return undefined
  return [Number(match[1]), Number(match[2])]
}

const WAVE_STYLES = new globalThis.Map<string, Style>()
function waveStyle(height: number): Style {
  const color = waveHeightColor(height)
  const cached = WAVE_STYLES.get(color)
  if (cached) return cached
  const style = new Style({ fill: new Fill({ color }), stroke: new Stroke({ color, width: 0.6 }) })
  WAVE_STYLES.set(color, style)
  return style
}

function waveRing(map: Map, wave: WaveSample, spacing: number): number[][] | undefined {
  const pixel = pixelFromId(wave.id)
  let ring: number[][]
  if (pixel) {
    const half = spacing / 2
    ring = [[-half, -half], [half, -half], [half, half], [-half, half]]
      .map(([dx, dy]) => map.getCoordinateFromPixel([pixel[0] + dx, pixel[1] + dy]) ?? [Number.NaN, Number.NaN])
  } else {
    const center = transform([wave.longitude, wave.latitude], 'EPSG:4326', map.getView().getProjection())
    const half = spacing * (map.getView().getResolution() ?? 1) / 2
    ring = [[center[0] - half, center[1] + half], [center[0] + half, center[1] + half], [center[0] + half, center[1] - half], [center[0] - half, center[1] - half]]
  }
  if (!ring.flat().every(Number.isFinite)) return undefined
  ring.push([...ring[0]])
  return ring
}

export function updateWaveFeaturePool(
  pool: EnvironmentFeaturePool<WaveSample | UnavailableWaveSample>,
  map: Map,
  field: WaveField,
  spacing = 105,
): number {
  return pool.update(field.waves.slice(0, 500), (feature, wave) => {
    if (!wave.available || !Number.isFinite(wave.wave_height)) return false
    const ring = waveRing(map, wave, spacing)
    if (!ring) return false
    const geometry = feature.getGeometry()
    if (geometry instanceof Polygon) geometry.setCoordinates([ring])
    else feature.setGeometry(new Polygon([ring]))
    feature.setProperties(wave, true)
    feature.setStyle(waveStyle(wave.wave_height))
    feature.changed()
    return true
  })
}

/** Convert viewport samples to contiguous screen-grid cells in the active projection. */
export function createWaveRasterFeatures(
  map: Map,
  waves: WaveField['waves'],
  spacing = 105,
): Feature<Polygon>[] {
  const features: Feature[] = []
  for (const wave of waves.slice(0, 500)) {
    if (!wave.available || !Number.isFinite(wave.wave_height)) continue
    const ring = waveRing(map, wave, spacing)
    if (!ring) continue
    const feature = new Feature<Polygon>({ geometry: new Polygon([ring]), ...wave })
    feature.setStyle(waveStyle(wave.wave_height))
    features.push(feature)
  }
  return features as Feature<Polygon>[]
}

/** Backward-compatible factory; the returned vector layer now contains polygons. */
export function createWaveVectorLayer(map: Map, field: WaveField, spacing = 105): VectorLayer<VectorSource> {
  const pool = new EnvironmentFeaturePool<WaveSample | UnavailableWaveSample>()
  updateWaveFeaturePool(pool, map, field, spacing)
  const layer = new VectorLayer({ source: new VectorSource({ features: pool.source.getFeatures().filter((feature) => feature.getGeometry() !== undefined) }), zIndex: 4 })
  layer.set('managedLayerId', 'wave')
  return layer
}
