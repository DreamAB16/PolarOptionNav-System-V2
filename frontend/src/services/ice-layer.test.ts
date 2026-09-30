import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createIceLayer,
  createIceSource,
  DEFAULT_ICE_OPACITY,
  ICE_CONCENTRATION_LEGEND,
  ICE_THICKNESS_LEGEND,
  iceTileUrl,
  isIceAvailable,
} from './ice-layer'
import { POLAR_ICE_TILE_EXTENT, POLAR_VIEW_EXTENT } from '../map/polar-view'

afterEach(() => vi.unstubAllGlobals())

describe('ice layer', () => {
  it('discovers and creates the backend XYZ raster source', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ layers: [{ id: 'ice', name: 'Sea Ice', status: 'ready' }] }),
    }))

    expect(await isIceAvailable()).toBe(true)
    const layer = createIceLayer()
    expect(layer.getSource()?.getUrls()?.[0]).toContain('/api/environment/ice/tile/{z}/{x}/{y}.png')
    expect(layer.getOpacity()).toBe(DEFAULT_ICE_OPACITY)
    expect(createIceLayer(0.4).getOpacity()).toBe(0.4)
    expect(iceTileUrl(new Date('2025-02-20T12:00:00Z'))).toContain('time=2025-02-20T12%3A00%3A00.000Z')
    expect(iceTileUrl(undefined, 'thickness')).toContain('/api/environment/ice/thickness/tile/')
    expect(iceTileUrl(undefined, 'concentration', true)).toContain('/api/environment/ice/polar/tile/')
    const polarSource = createIceSource(undefined, 'concentration', true)
    expect(polarSource.getProjection()?.getCode()).toBe('EPSG:3413')
    expect(polarSource.getTileGrid()?.getExtent()).toEqual(POLAR_ICE_TILE_EXTENT)
    expect(POLAR_VIEW_EXTENT[2]).toBeGreaterThan(POLAR_ICE_TILE_EXTENT[2])
  })

  it('exposes renderer-aligned concentration and thickness legends', () => {
    expect(ICE_CONCENTRATION_LEGEND.map((entry) => entry.label)).toEqual([
      '0%', '20%', '40%', '60%', '80%', '100%',
    ])
    expect(ICE_CONCENTRATION_LEGEND.at(-1)?.color).toContain('255, 255, 255')
    expect(ICE_THICKNESS_LEGEND.map((entry) => entry.label)).toEqual([
      '0米', '0.5米', '1.5米', '3米', '5米以上',
    ])
  })
})
