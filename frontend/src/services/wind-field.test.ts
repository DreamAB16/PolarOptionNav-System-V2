import { describe, expect, it } from 'vitest'
import type Map from 'ol/Map'
import type View from 'ol/View'
import type LineString from 'ol/geom/LineString'
import { createPolarView, createStandardView } from '../map/polar-view'
import { EnvironmentFeaturePool } from './environment-feature-pool'
import { createWindVectorLayer, updateWindFeaturePool, type WindVector } from './wind-field'

const backendVector: WindVector = {
  id: 'p1',
  latitude: 80,
  longitude: 0,
  timestamp: '2025-02-15T12:00:00Z',
  u10: 1,
  v10: -5,
  wind_speed: Math.sqrt(26),
  wind_direction_math: 281.31,
  wind_direction_meteorological: 348.69,
  source: 'CARRA2 Pan-Arctic',
}

function mapWithView(view: View): Map {
  return { getView: () => view } as unknown as Map
}

describe('wind response contract', () => {
  it.each([
    ['EPSG:3857', createStandardView()],
    ['EPSG:3413', createPolarView()],
  ])('creates finite wind geometry in %s', (_projection, view) => {
    const layer = createWindVectorLayer(mapWithView(view), { vectors: [backendVector] })
    const features = layer.getSource()?.getFeatures() ?? []
    const geometry = features[0]?.getGeometry()
    const coordinates = (geometry as LineString | undefined)?.getCoordinates() as number[][]

    expect(features).toHaveLength(1)
    expect(coordinates.flat().every(Number.isFinite)).toBe(true)
    expect(features[0].get('latitude')).toBe(80)
    expect(features[0].get('longitude')).toBe(0)
  })

  it('skips a vector with invalid coordinates instead of projecting it at zero', () => {
    const invalid = { ...backendVector, longitude: Number.NaN }
    const layer = createWindVectorLayer(mapWithView(createPolarView()), { vectors: [invalid] })
    expect(layer.getSource()?.getFeatures()).toHaveLength(0)
  })

  it('skips a point outside CARRA2 coverage', () => {
    const unavailable = { ...backendVector, available: false }
    const layer = createWindVectorLayer(mapWithView(createPolarView()), { vectors: [unavailable] })
    expect(layer.getSource()?.getFeatures()).toHaveLength(0)
  })

  it('reuses wind Feature and Geometry objects between time steps', () => {
    const pool = new EnvironmentFeaturePool<WindVector>()
    const map = mapWithView(createPolarView())
    updateWindFeaturePool(pool, map, { requested_time: '', matched_time: '', vectors: [backendVector] })
    const feature = pool.source.getFeatures()[0]
    const geometry = feature.getGeometry()
    updateWindFeaturePool(pool, map, { requested_time: '', matched_time: '', vectors: [{ ...backendVector, u10: 4, wind_speed: 7 }] })
    expect(pool.size).toBe(1)
    expect(pool.source.getFeatures()[0]).toBe(feature)
    expect(pool.source.getFeatures()[0].getGeometry()).toBe(geometry)
    expect(pool.source.getFeatures()[0].get('wind_speed')).toBe(7)
  })
})
