import type { LayerKey } from './map-layer-manager'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type EnvironmentLayerKey = Extract<
  LayerKey,
  'bathymetry' | 'ice' | 'wind' | 'current' | 'wave'
>

export interface EnvironmentLayerInfo {
  source: string
  resolution: string
  cadence: string
}

export const ENVIRONMENT_LAYER_INFO: Readonly<Record<EnvironmentLayerKey, EnvironmentLayerInfo>> = {
  bathymetry: {
    source: 'GEBCO 2026',
    resolution: '原始 15″ · 极地显示 1 km',
    cadence: '静态地形',
  },
  ice: {
    source: 'Copernicus Marine neXtSIM-F',
    resolution: '0.03° · 北纬 60°–90°',
    cadence: '日场景 · 12:00 UTC',
  },
  wind: {
    source: 'CARRA2 Pan-Arctic',
    resolution: '2.5 km 极地网格',
    cadence: '3 小时',
  },
  current: {
    source: 'Copernicus Marine TOPAZ5',
    resolution: '6.25 km 极地网格',
    cadence: '小时级',
  },
  wave: {
    source: 'Copernicus Marine Arctic WAM',
    resolution: '0.03° · 约 3 km',
    cadence: '小时级',
  },
}

export type EnvironmentProviderStatus = 'ready' | 'pending' | 'not_found' | 'unknown'

/** Read runtime readiness without exposing any environmental file path. */
export async function getEnvironmentProviderStatuses(
  signal?: AbortSignal,
): Promise<Partial<Record<EnvironmentLayerKey, EnvironmentProviderStatus>>> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/environment/layers`, { signal })
    if (!response.ok) return {}
    const body = (await response.json()) as {
      layers?: Array<{ id: string; status: string }>
    }
    const result: Partial<Record<EnvironmentLayerKey, EnvironmentProviderStatus>> = {}
    for (const layer of body.layers ?? []) {
      if (!(layer.id in ENVIRONMENT_LAYER_INFO)) continue
      const status = ['ready', 'pending', 'not_found'].includes(layer.status)
        ? layer.status as EnvironmentProviderStatus
        : 'unknown'
      result[layer.id as EnvironmentLayerKey] = status
    }
    return result
  } catch {
    return {}
  }
}
