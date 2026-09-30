// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Polygon from 'ol/geom/Polygon'
import type Map from 'ol/Map'
import View from 'ol/View'
import { EnvironmentFeaturePool } from './environment-feature-pool'
import { createWaveRasterFeatures, createWaveVectorLayer, sampleWaveViewport, updateWaveFeaturePool, type UnavailableWaveSample, type WaveField, type WaveSample } from './wave-field'
import '../map/polar-view'

const field: WaveField = {
  requested_time: '2025-02-15T12:00:00Z',
  matched_time: '2025-02-15T12:00:00Z',
  source: 'Copernicus Marine Arctic Wave',
  waves: [
    { id: 'valid', available: true, timestamp: '2025-02-15T12:00:00Z', requested_time: '2025-02-15T12:00:00Z', matched_time: '2025-02-15T12:00:00Z', latitude: 80, longitude: 30, wave_height: 1.8, wave_period: 7.5, wave_direction_from: 230, source: 'Copernicus Marine Arctic Wave' },
    { id: 'invalid', available: false, latitude: 75, longitude: -30, reason: 'no_data' },
  ],
}

function mapStub(projection: string): Map {
  const view = new View({ center: [0, 0], zoom: 2, projection })
  return {
    getView: () => view,
    getSize: () => [400, 300],
    getCoordinateFromPixel: ([x, y]: number[]) => [x * 1000 - 200000, 8_000_000 - y * 1000],
  } as unknown as Map
}

describe('wave field map adapter', () => {
  beforeEach(() => vi.restoreAllMocks())

  it.each(['EPSG:3857', 'EPSG:3413'])('creates one finite wave-height feature in %s', (projection) => {
    const layer = createWaveVectorLayer(mapStub(projection), field)
    const features = layer.getSource()?.getFeatures() ?? []
    expect(features).toHaveLength(1)
    expect((features[0].getGeometry() as Polygon).getCoordinates()[0].flat().every(Number.isFinite)).toBe(true)
    expect(features[0].get('wave_direction_from')).toBe(230)
  })

  it('builds contiguous polygon cells and omits unavailable samples', () => {
    const features = createWaveRasterFeatures(mapStub('EPSG:3857'), field.waves)
    expect(features).toHaveLength(1)
    expect((features[0].getGeometry() as Polygon).getCoordinates()[0]).toHaveLength(5)
  })

  it('uses one batch request and consumes the wave contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => field }))
    const result = await sampleWaveViewport(mapStub('EPSG:3857'), new Date('2025-02-15T12:00:00Z'))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(result.waves[0]).toMatchObject({ wave_height: 1.8, wave_period: 7.5, wave_direction_from: 230 })
  })

  it('reuses wave Feature and Polygon objects', () => {
    const pool = new EnvironmentFeaturePool<WaveSample | UnavailableWaveSample>()
    const map = mapStub('EPSG:3413')
    updateWaveFeaturePool(pool, map, field)
    const feature = pool.source.getFeatures()[0]
    const geometry = feature.getGeometry()
    updateWaveFeaturePool(pool, map, { ...field, waves: [{ ...(field.waves[0] as WaveSample), wave_height: 3 }] })
    expect(pool.source.getFeatures()[0]).toBe(feature)
    expect(pool.source.getFeatures()[0].getGeometry()).toBe(geometry)
    expect(pool.activeCount).toBe(1)
  })
})
