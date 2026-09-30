import type BaseLayer from 'ol/layer/Base'
import VectorLayer from 'ol/layer/Vector'
import type Map from 'ol/Map'
import { ManagedLayerBase } from '../managed-layer'
import { EnvironmentDisplayCache, EnvironmentPrefetchQueue, environmentDisplayCacheKey, environmentSampleSpacing } from '../../services/environment-display-cache'
import { EnvironmentFeaturePool } from '../../services/environment-feature-pool'
import { sampleCurrentViewport, updateCurrentFeaturePool, type CurrentField, type CurrentVector, type UnavailableCurrentPoint } from '../../services/current-field'

/** Time-aware TOPAZ5 surface-current arrows with stale-request protection. */
export class CurrentLayer extends ManagedLayerBase {
  readonly id = 'current' as const
  readonly type = 'vector-field' as const
  private mapRef?: Map
  private time = new Date('2025-02-15T12:00:00Z')
  private readonly pool = new EnvironmentFeaturePool<CurrentVector | UnavailableCurrentPoint>()
  private readonly vectorLayer = new VectorLayer({ source: this.pool.source, zIndex: 6 })
  private readonly displayCache = new EnvironmentDisplayCache<CurrentField>(10)
  private readonly prefetchQueue = new EnvironmentPrefetchQueue()
  private attached = false
  private requestId = 0
  private requestController?: AbortController
  private enabled = false
  private matchedTime?: string

  protected async createLayer(_signal: AbortSignal): Promise<BaseLayer> {
    throw new Error('海流需要地图上下文，请通过 refresh 载入。')
  }

  async load(map: Map): Promise<void> {
    this.mapRef = map
    this.enabled = true
    this.prefetchQueue.cancel()
    const id = ++this.requestId
    this.requestController?.abort()
    const controller = new AbortController()
    this.requestController = controller
    this.setState('loading')
    try {
      const spacing = environmentSampleSpacing('current', map.getView().getZoom())
      const key = environmentDisplayCacheKey('current', map, this.time, spacing, 1)
      const cached = this.displayCache.get(key)
      const field = cached ?? await sampleCurrentViewport(map, this.time, spacing, controller.signal)
      if (controller.signal.aborted || id !== this.requestId || !this.enabled) return
      if (!cached) this.displayCache.set(key, field)
      updateCurrentFeaturePool(this.pool, map, field)
      this.matchedTime = field.matched_time
      if (!this.attached) { map.addLayer(this.vectorLayer); this.attached = true }
      this.setState('ready')
      this.prefetch(map, spacing)
    } catch (cause) {
      if (controller.signal.aborted || id !== this.requestId) return
      const error = cause instanceof Error ? cause : new Error(String(cause))
      this.setState('error', error)
      throw error
    }
  }

  async updateTime(time: Date): Promise<void> {
    this.time = time
    this.matchedTime = undefined
    if (this.mapRef && this.enabled) await this.load(this.mapRef)
  }

  async refresh(): Promise<void> {
    if (this.mapRef && this.enabled) await this.load(this.mapRef)
  }

  unload(): void {
    this.enabled = false
    ++this.requestId
    this.requestController?.abort()
    this.prefetchQueue.cancel()
    this.requestController = undefined
    if (this.attached) this.mapRef?.removeLayer(this.vectorLayer)
    this.attached = false
    this.setState('idle')
  }

  setVisibility(visible: boolean): void {
    if (!visible) this.unload()
    else { this.enabled = true; this.vectorLayer.setVisible(true) }
  }

  getMatchedTime(): string | undefined { return this.matchedTime }

  private prefetch(map: Map, spacing: number): void {
    this.prefetchQueue.schedule([1, 2, 3].map((hours) => async (signal: AbortSignal) => {
      const time = new Date(this.time.getTime() + hours * 3_600_000)
      const key = environmentDisplayCacheKey('current', map, time, spacing, 1)
      if (this.displayCache.has(key)) return
      this.displayCache.set(key, await sampleCurrentViewport(map, time, spacing, signal))
    }))
  }

}
