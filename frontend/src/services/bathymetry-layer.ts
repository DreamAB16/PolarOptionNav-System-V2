import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'
import { createXYZ } from 'ol/tilegrid'
import {
  POLAR_PROJECTION_CODE,
  POLAR_VIEW_EXTENT,
  STANDARD_PROJECTION_CODE,
} from '../map/polar-view'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface EnvironmentLayer {
  id: string
  name: string
  status: string
}

/** Verify that the backend has registered a real bathymetry provider. */
export async function isBathymetryAvailable(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch(`${apiBaseUrl}/api/environment/layers`, { signal })
  if (!response.ok) return false
  const body = (await response.json()) as { layers: EnvironmentLayer[] }
  return body.layers.some((layer) => layer.id === 'bathymetry' && layer.status === 'ready')
}

export function bathymetryTileUrl(polar = false): string {
  const path = polar
    ? '/api/environment/bathymetry/polar/tile/{z}/{x}/{y}.png'
    : '/api/environment/bathymetry/tiles/{z}/{x}/{y}.png'
  return `${apiBaseUrl}${path}`
}

/** Build a source in the projection served by the corresponding backend route. */
export function createBathymetrySource(polar = false): XYZ {
  return new XYZ({
    url: bathymetryTileUrl(polar),
    projection: polar ? POLAR_PROJECTION_CODE : STANDARD_PROJECTION_CODE,
    tileGrid: polar
      ? createXYZ({ extent: POLAR_VIEW_EXTENT, tileSize: 256, maxZoom: 14 })
      : undefined,
    crossOrigin: 'anonymous',
    maxZoom: 14,
    transition: 150,
  })
}

/** Build a backend-backed bathymetry layer; GEBCO never reaches the browser. */
export function createBathymetryLayer(polar = false): TileLayer<XYZ> {
  const layer = new TileLayer({
    source: createBathymetrySource(polar),
    opacity: 0.72,
  })
  // Base map is -10 and vector chart layers keep the default 0.
  layer.setZIndex(-5)
  return layer
}
