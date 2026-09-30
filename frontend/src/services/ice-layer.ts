import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'
import { createXYZ } from 'ol/tilegrid'
import {
  POLAR_ICE_TILE_EXTENT,
  POLAR_PROJECTION_CODE,
  STANDARD_PROJECTION_CODE,
} from '../map/polar-view'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface EnvironmentLayer {
  id: string
  status: string
}

/** Check that the backend exposes a real sea-ice tile source. */
export async function isIceAvailable(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch(`${apiBaseUrl}/api/environment/layers`, { signal })
  if (!response.ok) return false
  const body = (await response.json()) as { layers: EnvironmentLayer[] }
  return body.layers.some((layer) => layer.id === 'ice' && layer.status === 'ready')
}

/** Build a backend-backed XYZ raster layer; no NetCDF is loaded by the browser. */
export const DEFAULT_ICE_OPACITY = 0.75
export type IceDisplayMode = 'concentration' | 'thickness'

export interface IceLegendEntry {
  label: string
  color: string
}

/** Build the concentration legend used by the backend Copernicus tile palette. */
export const ICE_CONCENTRATION_LEGEND: readonly IceLegendEntry[] = [
  { label: '0%', color: 'rgba(218, 246, 249, 0)' },
  { label: '20%', color: 'rgba(170, 226, 230, 0.518)' },
  { label: '40%', color: 'rgba(92, 190, 180, 0.706)' },
  { label: '60%', color: 'rgba(58, 144, 139, 0.824)' },
  { label: '80%', color: 'rgba(215, 225, 225, 0.933)' },
  { label: '100%', color: 'rgba(255, 255, 255, 1)' },
]

export const ICE_THICKNESS_LEGEND: readonly IceLegendEntry[] = [
  { label: '0米', color: 'rgba(255, 246, 214, 0)' },
  { label: '0.5米', color: 'rgba(255, 229, 153, 0.569)' },
  { label: '1.5米', color: 'rgba(239, 155, 70, 0.824)' },
  { label: '3米', color: 'rgba(132, 82, 125, 0.941)' },
  { label: '5米以上', color: 'rgba(255, 255, 255, 1)' },
]

export const ICE_LEGENDS: Record<IceDisplayMode, readonly IceLegendEntry[]> = {
  concentration: ICE_CONCENTRATION_LEGEND,
  thickness: ICE_THICKNESS_LEGEND,
}

export function iceTileUrl(
  timestamp?: Date,
  mode: IceDisplayMode = 'concentration',
  polar = false,
): string {
  const timeParameter = timestamp ? `?time=${encodeURIComponent(timestamp.toISOString())}` : ''
  const path = polar
    ? mode === 'thickness'
      ? '/api/environment/ice/thickness/polar/tile/{z}/{x}/{y}.png'
      : '/api/environment/ice/polar/tile/{z}/{x}/{y}.png'
    : mode === 'thickness'
      ? '/api/environment/ice/thickness/tile/{z}/{x}/{y}.png'
      : '/api/environment/ice/tile/{z}/{x}/{y}.png'
  return `${apiBaseUrl}${path}${timeParameter}`
}

export function createIceSource(
  timestamp?: Date,
  mode: IceDisplayMode = 'concentration',
  polar = false,
): XYZ {
  return new XYZ({
    url: iceTileUrl(timestamp, mode, polar),
    projection: polar ? POLAR_PROJECTION_CODE : STANDARD_PROJECTION_CODE,
    tileGrid: polar
      ? createXYZ({ extent: POLAR_ICE_TILE_EXTENT, tileSize: 256, maxZoom: 10 })
      : undefined,
    crossOrigin: 'anonymous',
    maxZoom: 10,
    transition: 150,
  })
}

export function createIceLayer(
  opacity = DEFAULT_ICE_OPACITY,
  timestamp?: Date,
  mode: IceDisplayMode = 'concentration',
  polar = false,
): TileLayer<XYZ> {
  const layer = new TileLayer({
    source: createIceSource(timestamp, mode, polar),
    opacity,
  })
  // Ice is above bathymetry (-5) but below the coastline vector layer (0).
  layer.setZIndex(-2)
  return layer
}
