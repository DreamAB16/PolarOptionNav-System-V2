import type OlMap from 'ol/Map'
import type BaseLayer from 'ol/layer/Base'
import type { LayerId, LayerState, LayerStateListener, ManagedLayer } from '../map/managed-layer'

export type { LayerId as LayerKey, LayerState, ManagedLayer } from '../map/managed-layer'

interface LayerRecord {
  layer: ManagedLayer
  legacy: boolean
  desiredVisibility: boolean
}

/** Adapts the original OpenLayers-only registration API to the new lifecycle. */
class LegacyLayerAdapter implements ManagedLayer {
  readonly type = 'legacy' as const
  readonly error = undefined
  private currentState: LayerState = 'idle'
  private map: OlMap | undefined
  private readonly listeners = new Set<LayerStateListener>()

  constructor(readonly id: LayerId, private readonly olLayer: BaseLayer) {}

  get state(): LayerState {
    return this.currentState
  }

  async load(map: OlMap): Promise<void> {
    if (this.currentState === 'ready' && this.map === map) return
    this.map?.removeLayer(this.olLayer)
    this.map = map
    map.addLayer(this.olLayer)
    this.setState('ready')
  }

  unload(): void {
    this.map?.removeLayer(this.olLayer)
    this.map = undefined
    this.setState('idle')
  }

  async refresh(): Promise<void> {
    const source = (this.olLayer as BaseLayer & { getSource?: () => { refresh?: () => void } }).getSource?.()
    source?.refresh?.()
  }

  async updateTime(_time: Date): Promise<void> {}

  setVisibility(visible: boolean): void {
    this.olLayer.setVisible(visible)
  }

  show(): void {
    this.setVisibility(true)
  }

  hide(): void {
    this.setVisibility(false)
  }

  dispose(): void {
    this.unload()
    this.olLayer.dispose()
    this.listeners.clear()
  }

  subscribe(listener: LayerStateListener): () => void {
    this.listeners.add(listener)
    listener(this.currentState)
    return () => this.listeners.delete(listener)
  }

  private setState(state: LayerState): void {
    this.currentState = state
    this.listeners.forEach((listener) => listener(state))
  }
}

/** Owns map-layer registration, visibility and asynchronous lifecycle coordination. */
export class MapLayerManager {
  private readonly layers = new globalThis.Map<LayerId, LayerRecord>()
  private map: OlMap | undefined

  register(layer: ManagedLayer): void
  register(key: LayerId, layer: BaseLayer): void
  register(keyOrLayer: LayerId | ManagedLayer, olLayer?: BaseLayer): void {
    const legacy = typeof keyOrLayer === 'string'
    const layer = legacy ? new LegacyLayerAdapter(keyOrLayer, olLayer as BaseLayer) : keyOrLayer
    this.layers.get(layer.id)?.layer.dispose()

    const desiredVisibility = legacy ? (olLayer as BaseLayer).getVisible() : false
    const record: LayerRecord = { layer, legacy, desiredVisibility }
    this.layers.set(layer.id, record)
    if (this.map && legacy) void layer.load(this.map).catch(() => undefined)
  }

  attach(map: OlMap): void {
    this.map = map
    this.layers.forEach((record) => {
      if (record.legacy || record.desiredVisibility) {
        void record.layer.load(map).catch(() => undefined)
      }
    })
  }

  /** Backward-compatible visibility API for existing callers. */
  setVisible(key: LayerId, visible: boolean): void {
    void this.setVisibility(key, visible).catch(() => undefined)
  }

  async setVisibility(key: LayerId, visible: boolean): Promise<void> {
    const record = this.layers.get(key)
    if (!record) return
    record.desiredVisibility = visible
    if (!visible) {
      record.layer.setVisibility(false)
      return
    }
    record.layer.setVisibility(true)
    if (this.map) await record.layer.load(this.map)
  }

  async refresh(key: LayerId): Promise<void> {
    await this.layers.get(key)?.layer.refresh()
  }

  async updateTime(time: Date): Promise<void> {
    await Promise.allSettled([...this.layers.values()].map(({ layer }) => layer.updateTime(time)))
  }

  unload(key: LayerId): void {
    const record = this.layers.get(key)
    if (!record) return
    record.desiredVisibility = false
    record.layer.unload()
  }

  unregister(key: LayerId): void {
    this.layers.get(key)?.layer.dispose()
    this.layers.delete(key)
  }

  getState(key: LayerId): LayerState {
    return this.layers.get(key)?.layer.state ?? 'idle'
  }

  subscribe(key: LayerId, listener: LayerStateListener): () => void {
    return this.layers.get(key)?.layer.subscribe(listener) ?? (() => undefined)
  }

  dispose(): void {
    this.layers.forEach(({ layer }) => layer.dispose())
    this.layers.clear()
    this.map = undefined
  }
}
