import type BaseLayer from 'ol/layer/Base'
import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'
import { ManagedLayerBase } from '../managed-layer'
import {
  createBathymetryLayer,
  createBathymetrySource,
  isBathymetryAvailable,
} from '../../services/bathymetry-layer'

/** Independently manages the existing GEBCO raster tile lifecycle. */
export class BathymetryLayer extends ManagedLayerBase {
  readonly id = 'bathymetry' as const
  readonly type = 'raster-tile' as const
  private polar = false
  private tileLayer: TileLayer<XYZ> | undefined

  /** Switch between the retained global source and native Arctic EPSG:3413 tiles. */
  setPolarMode(enabled: boolean): void {
    if (enabled === this.polar) return
    this.polar = enabled
    this.tileLayer?.setSource(createBathymetrySource(this.polar))
  }

  protected async createLayer(signal: AbortSignal): Promise<BaseLayer> {
    if (!(await isBathymetryAvailable(signal))) {
      throw new Error('水深数据服务不可用。')
    }
    this.tileLayer = createBathymetryLayer(this.polar)
    return this.tileLayer
  }
}
