import { describe, expect, it } from 'vitest'
import type OlMap from 'ol/Map'
import type BaseLayer from 'ol/layer/Base'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import { MapLayerManager } from './map-layer-manager'
import { ManagedLayerBase } from '../map/managed-layer'

class TestManagedLayer extends ManagedLayerBase {
  readonly id = 'route' as const
  readonly type = 'route' as const
  readonly times: string[] = []

  protected async createLayer(_signal: AbortSignal): Promise<BaseLayer> {
    return new TileLayer({ source: new OSM() })
  }

  async updateTime(time: Date): Promise<void> {
    this.times.push(time.toISOString())
  }
}

describe('MapLayerManager', () => {
  it('registers and toggles named layers', () => {
    const manager = new MapLayerManager()
    const layer = new TileLayer({ source: new OSM() })
    manager.register('charts', layer)
    manager.setVisible('charts', false)
    expect(layer.getVisible()).toBe(false)
  })

  it('coordinates a managed layer lifecycle', async () => {
    const attached: BaseLayer[] = []
    const map = {
      addLayer: (layer: BaseLayer) => attached.push(layer),
      removeLayer: (layer: BaseLayer) => attached.splice(attached.indexOf(layer), 1),
    } as unknown as OlMap
    const manager = new MapLayerManager()
    const managedLayer = new TestManagedLayer()
    manager.attach(map)
    manager.register(managedLayer)
    const states: string[] = []
    manager.subscribe('route', (state) => states.push(state))

    await manager.setVisibility('route', true)
    await manager.updateTime(new Date('2025-08-15T12:00:00Z'))

    expect(states).toEqual(['idle', 'loading', 'ready'])
    expect(manager.getState('route')).toBe('ready')
    expect(attached).toHaveLength(1)
    expect(managedLayer.times).toEqual(['2025-08-15T12:00:00.000Z'])

    const reattached: BaseLayer[] = []
    const secondMap = {
      addLayer: (layer: BaseLayer) => reattached.push(layer),
      removeLayer: (layer: BaseLayer) => reattached.splice(reattached.indexOf(layer), 1),
    } as unknown as OlMap
    manager.attach(secondMap)
    expect(attached).toHaveLength(0)
    expect(reattached).toHaveLength(1)

    manager.unload('route')
    expect(manager.getState('route')).toBe('idle')
    expect(reattached).toHaveLength(0)
  })
})
