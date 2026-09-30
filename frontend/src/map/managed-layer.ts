import type OlMap from 'ol/Map'
import type BaseLayer from 'ol/layer/Base'

export type LayerId = 'charts' | 'bathymetry' | 'ice' | 'wind' | 'current' | 'wave' | 'route' | 'vessel'
export type LayerState = 'idle' | 'loading' | 'ready' | 'error'
export type LayerType = 'geojson' | 'vector-tile' | 'raster-tile' | 'vector-field' | 'route' | 'legacy'
export type LayerStateListener = (state: LayerState, error?: Error) => void

/** Unified lifecycle implemented by every independently managed map layer. */
export interface ManagedLayer {
  readonly id: LayerId
  readonly type: LayerType
  readonly state: LayerState
  readonly error?: Error

  load(map: OlMap): Promise<void>
  unload(): void
  refresh(): Promise<void>
  updateTime(time: Date): Promise<void>
  setVisibility(visible: boolean): void
  show(): void
  hide(): void
  dispose(): void
  subscribe(listener: LayerStateListener): () => void
}

/** Shared async lifecycle, cancellation and state handling for map layers. */
export abstract class ManagedLayerBase implements ManagedLayer {
  abstract readonly id: LayerId
  abstract readonly type: LayerType

  private currentState: LayerState = 'idle'
  private currentError: Error | undefined
  private map: OlMap | undefined
  private olLayer: BaseLayer | undefined
  private loadPromise: Promise<void> | undefined
  private loadController: AbortController | undefined
  private generation = 0
  private desiredVisibility = false
  private readonly listeners = new Set<LayerStateListener>()

  get state(): LayerState {
    return this.currentState
  }

  get error(): Error | undefined {
    return this.currentError
  }

  async load(map: OlMap): Promise<void> {
    if (this.currentState === 'ready') {
      if (this.map !== map && this.olLayer) {
        this.map?.removeLayer(this.olLayer)
        map.addLayer(this.olLayer)
      }
      this.map = map
      return
    }
    this.map = map
    if (this.loadPromise) return this.loadPromise

    const generation = ++this.generation
    this.loadController?.abort()
    const controller = new AbortController()
    this.loadController = controller
    this.setState('loading')

    const operation = (async () => {
      try {
        const layer = await this.createLayer(controller.signal)
        if (controller.signal.aborted || generation !== this.generation) {
          layer.dispose()
          return
        }
        layer.setVisible(this.desiredVisibility)
        this.olLayer = layer
        this.map?.addLayer(layer)
        this.setState('ready')
      } catch (cause) {
        if (!controller.signal.aborted && generation === this.generation) {
          const error = cause instanceof Error ? cause : new Error(String(cause))
          this.setState('error', error)
        }
        throw cause
      } finally {
        if (generation === this.generation) this.loadPromise = undefined
      }
    })()

    this.loadPromise = operation
    return operation
  }

  unload(): void {
    this.generation += 1
    this.loadController?.abort()
    this.loadController = undefined
    if (this.olLayer) {
      this.map?.removeLayer(this.olLayer)
      this.olLayer.dispose()
      this.olLayer = undefined
    }
    this.loadPromise = undefined
    this.setState('idle')
  }

  async refresh(): Promise<void> {
    const map = this.map
    if (!map) return
    this.unload()
    await this.load(map)
  }

  async updateTime(_time: Date): Promise<void> {
    // Static layers intentionally do nothing. Time-aware subclasses override this.
  }

  show(): void {
    this.desiredVisibility = true
    this.olLayer?.setVisible(true)
  }

  hide(): void {
    this.desiredVisibility = false
    this.olLayer?.setVisible(false)
  }

  setVisibility(visible: boolean): void {
    if (visible) this.show()
    else this.hide()
  }

  dispose(): void {
    this.unload()
    this.map = undefined
    this.listeners.clear()
  }

  subscribe(listener: LayerStateListener): () => void {
    this.listeners.add(listener)
    listener(this.currentState, this.currentError)
    return () => this.listeners.delete(listener)
  }

  protected abstract createLayer(signal: AbortSignal): Promise<BaseLayer>

  protected setState(state: LayerState, error?: Error): void {
    this.currentState = state
    this.currentError = error
    this.listeners.forEach((listener) => listener(state, error))
  }
}
