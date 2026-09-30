import type BaseLayer from 'ol/layer/Base'
import { ManagedLayerBase } from '../managed-layer'
import { createCoastlineLayer, fetchChartLayer, fetchChartLayers } from '../../services/chart-client'

/** Independently manages the existing coastline GeoJSON lifecycle. */
export class ChartLayer extends ManagedLayerBase {
  readonly id = 'charts' as const
  readonly type = 'geojson' as const
  private projection = 'EPSG:3857'

  async setProjection(projection: string): Promise<void> {
    if (projection === this.projection) return
    this.projection = projection
    await this.refresh()
  }

  protected async createLayer(signal: AbortSignal): Promise<BaseLayer> {
    const coastline = (await fetchChartLayers(signal)).find((layer) => layer.id === 'coastline')
    if (!coastline) throw new Error('海图服务未发布海岸线图层。')
    const data = await fetchChartLayer(coastline.url, signal)
    return createCoastlineLayer(data, this.projection)
  }
}
