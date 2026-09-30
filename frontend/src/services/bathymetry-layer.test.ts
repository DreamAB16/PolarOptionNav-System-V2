import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createBathymetryLayer,
  createBathymetrySource,
  isBathymetryAvailable,
} from './bathymetry-layer'

afterEach(() => vi.unstubAllGlobals())

describe('bathymetry layer', () => {
  it('discovers and creates the backend XYZ raster source', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        layers: [{ id: 'bathymetry', name: 'Bathymetry', status: 'ready' }],
      }),
    }))

    expect(await isBathymetryAvailable()).toBe(true)
    const layer = createBathymetryLayer()
    expect(layer.getSource()?.getUrls()?.[0]).toContain('/api/environment/bathymetry/tiles/{z}/{x}/{y}.png')
    expect(layer.getSource()?.getProjection()?.getCode()).toBe('EPSG:3857')
    expect(layer.getOpacity()).toBe(0.72)
  })

  it('uses native EPSG:3413 tiles for Arctic map modes', () => {
    const source = createBathymetrySource(true)

    expect(source.getUrls()?.[0]).toContain('/api/environment/bathymetry/polar/tile/{z}/{x}/{y}.png')
    expect(source.getProjection()?.getCode()).toBe('EPSG:3413')
    expect(source.getTileGrid()?.getExtent()).toEqual([-7_150_000, -7_150_000, 7_150_000, 7_150_000])
  })
})
