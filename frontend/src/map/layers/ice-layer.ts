import type BaseLayer from 'ol/layer/Base'
import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'
import { ManagedLayerBase } from '../managed-layer'
import {
  createIceLayer,
  createIceSource,
  DEFAULT_ICE_OPACITY,
  iceTileUrl,
  isIceAvailable,
  type IceDisplayMode,
} from '../../services/ice-layer'
import { nearestAvailableIceTime } from '../../services/environment-time'

/** Independently manages the backend sea-ice raster tile lifecycle. */
export class IceLayer extends ManagedLayerBase {
  readonly id = 'ice' as const
  readonly type = 'raster-tile' as const
  private opacity = DEFAULT_ICE_OPACITY
  private timestamp: Date | undefined
  private mode: IceDisplayMode = 'concentration'
  private polar = false
  private tileLayer: TileLayer<XYZ> | undefined

  setOpacity(opacity: number): void {
    this.opacity = Math.min(1, Math.max(0.3, opacity))
    this.tileLayer?.setOpacity(this.opacity)
  }

  async updateTime(time: Date): Promise<void> {
    this.timestamp = time
    this.updateSourceUrl()
  }

  setMode(mode: IceDisplayMode): void {
    this.mode = mode
    this.updateSourceUrl()
  }

  setPolarMode(enabled: boolean): void {
    if (enabled === this.polar) return
    this.polar = enabled
    if (this.tileLayer) {
      this.tileLayer.setSource(createIceSource(this.timestamp, this.mode, this.polar))
    }
  }

  protected async createLayer(signal: AbortSignal): Promise<BaseLayer> {
    if (!(await isIceAvailable(signal))) {
      throw new Error('海冰数据服务不可用。')
    }
    this.tileLayer = createIceLayer(this.opacity, this.timestamp, this.mode, this.polar)
    return this.tileLayer
  }

  private updateSourceUrl(): void {
    this.tileLayer?.getSource()?.setUrl(iceTileUrl(this.timestamp, this.mode, this.polar))
  }

  getMatchedTime(): string | undefined {
    return this.timestamp ? nearestAvailableIceTime(this.timestamp) : undefined
  }
}
