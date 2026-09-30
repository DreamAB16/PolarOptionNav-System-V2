import GeoJSON from 'ol/format/GeoJSON'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import { Stroke, Style } from 'ol/style'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface ChartLayerDescriptor {
  id: string
  name: string
  format: 'geojson'
  geometry_type: string
  feature_count: number
  source_crs: string
  url: string
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection'
  features: object[]
}

/** Fetches the server-published chart catalogue; no data-file URL reaches the browser. */
export async function fetchChartLayers(signal?: AbortSignal): Promise<ChartLayerDescriptor[]> {
  const response = await fetch(`${apiBaseUrl}/api/chart/layers`, { signal })
  if (!response.ok) throw new Error('无法加载海图图层目录。')
  const body = (await response.json()) as { layers: ChartLayerDescriptor[] }
  return body.layers
}

/** Fetches a provider-approved chart layer in GeoJSON, ready for OpenLayers. */
export async function fetchChartLayer(url: string, signal?: AbortSignal): Promise<GeoJsonFeatureCollection> {
  const response = await fetch(`${apiBaseUrl}${url}`, { signal })
  if (!response.ok) throw new Error('无法加载海图图层数据。')
  return (await response.json()) as GeoJsonFeatureCollection
}

/** Creates the dedicated coastline vector layer in the map display projection. */
export function createCoastlineLayer(
  data: GeoJsonFeatureCollection,
  featureProjection = 'EPSG:3857',
): VectorLayer<VectorSource> {
  const features = new GeoJSON().readFeatures(data, {
    dataProjection: 'EPSG:4326',
    featureProjection,
  })
  return new VectorLayer({
    source: new VectorSource({ features }),
    style: new Style({ stroke: new Stroke({ color: '#153c5a', width: 1.4 }) }),
  })
}
