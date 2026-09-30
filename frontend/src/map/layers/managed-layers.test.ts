import type OlMap from 'ol/Map'
import type BaseLayer from 'ol/layer/Base'
import VectorLayer from 'ol/layer/Vector'
import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BathymetryLayer } from './bathymetry-layer'
import { ChartLayer } from './chart-layer'
import { IceLayer } from './ice-layer'

function createMapHarness(): { map: OlMap; layers: BaseLayer[] } {
  const layers: BaseLayer[] = []
  const map = {
    addLayer: (layer: BaseLayer) => layers.push(layer),
    removeLayer: (layer: BaseLayer) => {
      const index = layers.indexOf(layer)
      if (index >= 0) layers.splice(index, 1)
    },
  } as unknown as OlMap
  return { map, layers }
}

afterEach(() => vi.unstubAllGlobals())

describe('managed map layers', () => {
  it('loads, displays and unloads the existing coastline layer', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ layers: [{ id: 'coastline', url: '/api/chart/layers/coastline' }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: [[18, 69], [19, 70]] },
          }],
        }),
      }))
    const harness = createMapHarness()
    const layer = new ChartLayer()
    const states: string[] = []
    layer.subscribe((state) => states.push(state))

    layer.show()
    await layer.load(harness.map)

    expect(states).toEqual(['idle', 'loading', 'ready'])
    expect(harness.layers).toHaveLength(1)
    expect((harness.layers[0] as VectorLayer).getSource()?.getFeatures()).toHaveLength(1)
    layer.hide()
    expect(harness.layers[0].getVisible()).toBe(false)
    layer.unload()
    expect(layer.state).toBe('idle')
    expect(harness.layers).toHaveLength(0)
  })

  it('loads the existing bathymetry XYZ layer on demand', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ layers: [{ id: 'bathymetry', status: 'ready' }] }),
    }))
    const harness = createMapHarness()
    const layer = new BathymetryLayer()

    layer.show()
    await layer.load(harness.map)

    expect(layer.state).toBe('ready')
    expect(harness.layers).toHaveLength(1)
    expect(harness.layers[0].getVisible()).toBe(true)
    layer.setPolarMode(true)
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getProjection()?.getCode()).toBe('EPSG:3413')
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getUrls()?.[0]).toContain('/bathymetry/polar/tile/')
  })

  it('reports an unavailable bathymetry provider as an error state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    const layer = new BathymetryLayer()

    await expect(layer.load(createMapHarness().map)).rejects.toThrow('水深数据服务不可用。')
    expect(layer.state).toBe('error')
    expect(layer.error?.message).toBe('水深数据服务不可用。')
  })

  it('loads the sea-ice XYZ layer on demand', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ layers: [{ id: 'ice', status: 'ready' }] }),
    }))
    const harness = createMapHarness()
    const layer = new IceLayer()

    layer.show()
    await layer.load(harness.map)

    expect(layer.state).toBe('ready')
    expect(harness.layers).toHaveLength(1)
    expect(harness.layers[0].getVisible()).toBe(true)
    layer.setOpacity(0.4)
    expect((harness.layers[0] as TileLayer).getOpacity()).toBe(0.4)
    layer.setOpacity(0.1)
    expect((harness.layers[0] as TileLayer).getOpacity()).toBe(0.3)
    await layer.updateTime(new Date('2025-02-20T12:00:00Z'))
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getUrls()?.[0]).toContain('time=2025-02-20T12%3A00%3A00.000Z')
    layer.setMode('thickness')
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getUrls()?.[0]).toContain('/ice/thickness/tile/')
    layer.setPolarMode(true)
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getUrls()?.[0]).toContain('/ice/thickness/polar/tile/')
    expect((harness.layers[0] as TileLayer<XYZ>).getSource()?.getProjection()?.getCode()).toBe('EPSG:3413')
  })
})
