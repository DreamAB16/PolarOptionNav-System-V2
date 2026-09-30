// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Map from 'ol/Map'
import View from 'ol/View'
import LineString from 'ol/geom/LineString'
import { EnvironmentFeaturePool } from './environment-feature-pool'
import { createCurrentVectorLayer, MIN_VISIBLE_CURRENT_SPEED, sampleCurrentViewport, updateCurrentFeaturePool, type CurrentField, type CurrentVector, type UnavailableCurrentPoint } from './current-field'
import '../map/polar-view'

const field: CurrentField = {
  requested_time: '2025-02-15T12:00:00Z',
  matched_time: '2025-02-15T12:00:00Z',
  source: 'Copernicus Marine TOPAZ5 Arctic Ocean Physics',
  units: 'm/s',
  detided: true,
  currents: [
    { id: 'valid', available: true, latitude: 75, longitude: 30, timestamp: '2025-02-15T12:00:00Z', vxo: 0.1, vyo: 0.1, current_east: 0.1, current_north: 0.1, current_speed: 0.14, current_direction_to: 45, source: 'TOPAZ5', detided: true },
    { id: 'invalid', available: false, latitude: 70, longitude: 100, reason: 'no_data' },
  ],
}

describe('current field map adapter', () => {
  beforeEach(() => vi.restoreAllMocks())

  function mapStub(projection: string): Map {
    const view = new View({ center: [0, 0], zoom: 2, projection })
    return {
      getView: () => view,
      getSize: () => [400, 300],
      getCoordinateFromPixel: ([x, y]: number[]) => [x * 1000 - 200000, 8_000_000 - y * 1000],
    } as unknown as Map
  }

  it('keeps real low currents and rejects unavailable points in EPSG:3857', () => {
    const map = mapStub('EPSG:3857')
    const layer = createCurrentVectorLayer(map, field)
    expect(MIN_VISIBLE_CURRENT_SPEED).toBe(0.01)
    expect(layer.getSource()?.getFeatures()).toHaveLength(1)
    const coordinates = (layer.getSource()?.getFeatures()[0].getGeometry() as LineString).getCoordinates()
    expect(coordinates.flat().every(Number.isFinite)).toBe(true)
  })

  it('creates a finite arrow in EPSG:3413', () => {
    const map = mapStub('EPSG:3413')
    const feature = createCurrentVectorLayer(map, field).getSource()?.getFeatures()[0]
    expect((feature?.getGeometry() as LineString).getCoordinates().flat().every(Number.isFinite)).toBe(true)
  })

  it('uses one batch request and consumes latitude/longitude response fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => field }))
    const map = mapStub('EPSG:3857')
    const result = await sampleCurrentViewport(map, new Date('2025-02-15T12:00:00Z'), 100)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(result.currents[0]).toMatchObject({ latitude: 75, longitude: 30 })
  })

  it('reuses current Feature objects', () => {
    const pool = new EnvironmentFeaturePool<CurrentVector | UnavailableCurrentPoint>()
    const map = mapStub('EPSG:3413')
    updateCurrentFeaturePool(pool, map, field)
    const feature = pool.source.getFeatures()[0]
    updateCurrentFeaturePool(pool, map, { ...field, currents: [{ ...(field.currents[0] as CurrentVector), current_speed: 0.3 }] })
    expect(pool.source.getFeatures()[0]).toBe(feature)
    expect(pool.size).toBe(2)
    expect(pool.activeCount).toBe(1)
  })
})
