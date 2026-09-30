export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

import type { PlannerResponse, PlannerRiskLayers, VesselProfileResponse } from '../types/bridge'

export interface PlannerRequest {
  start: { lat: number; lon: number }
  goal: { lat: number; lon: number }
  departure_time: string
  grid_size?: number
  cell_size_m?: number
  population_size?: number
  generations?: number
  seed?: number
}

export async function isSystemOnline(): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/status`)
    return response.ok
  } catch {
    return false
  }
}

export async function getCurrentVessel(): Promise<VesselProfileResponse | undefined> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/vessel/current`)
    if (!response.ok) return undefined
    return await response.json() as VesselProfileResponse
  } catch {
    return undefined
  }
}

export async function planRoute(request: PlannerRequest): Promise<PlannerResponse> {
  const response = await fetch(`${apiBaseUrl}/api/planner`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    let detail = `规划请求失败（HTTP ${response.status}）`
    try {
      const payload = await response.json() as { detail?: unknown }
      if (typeof payload.detail === 'string') detail = payload.detail
      else if (payload.detail && typeof payload.detail === 'object' && 'message' in payload.detail) detail = String(payload.detail.message)
      else if (Array.isArray(payload.detail)) detail = payload.detail
        .map((item) => { const rec = item as { msg?: string; message?: string } | undefined; return rec?.msg ?? rec?.message ?? '' })
        .filter(Boolean)
        .join('；')
      if (!detail || detail.length === 0) detail = `规划请求失败（HTTP ${response.status}）`
    } catch {
      // Keep the HTTP status when the server did not return JSON.
    }
    throw new Error(detail)
  }
  return await response.json() as PlannerResponse
}

export async function getPlannerGrid(planId: string): Promise<PlannerRiskLayers & { plan_id: string }> {
  const response = await fetch(`${apiBaseUrl}/api/planner/${encodeURIComponent(planId)}/grid`)
  if (!response.ok) throw new Error(`规划栅格请求失败（HTTP ${response.status}）`)
  return await response.json() as PlannerRiskLayers & { plan_id: string }
}

export async function getPlannerGridCell(planId: string, cellId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiBaseUrl}/api/planner/${encodeURIComponent(planId)}/grid/${encodeURIComponent(cellId)}`)
  if (!response.ok) throw new Error(`规划栅格单元请求失败（HTTP ${response.status}）`)
  return await response.json() as Record<string, unknown>
}

export interface NorthernEnvironmentGridResponse extends PlannerRiskLayers {
  cell_size_m: number
  coordinate_reference: string
  planning_region: { south: number; north: number; west: number; east: number }
  bounds: { south: number; north: number; west: number; east: number }
  cell_count: number
  timestamp: string
  metrics?: Record<string, unknown>
}

export async function getNorthernEnvironmentGrid(time: string, options: { south?: number; north?: number; west?: number; east?: number; maxCells?: number } = {}, signal?: AbortSignal): Promise<NorthernEnvironmentGridResponse> {
  const params = new URLSearchParams({ time })
  if (options.south !== undefined) params.set('south', String(options.south))
  if (options.north !== undefined) params.set('north', String(options.north))
  if (options.west !== undefined) params.set('west', String(options.west))
  if (options.east !== undefined) params.set('east', String(options.east))
  if (options.maxCells !== undefined) params.set('max_cells', String(options.maxCells))
  const response = await fetch(`${apiBaseUrl}/api/environment/grid/northern?${params.toString()}`, { signal })
  if (!response.ok) {
    let detail = `环境栅格请求失败（HTTP ${response.status}）`
    try { const body = await response.json() as { detail?: unknown }; if (typeof body.detail === 'string') detail = body.detail } catch { /* retain status */ }
    throw new Error(detail)
  }
  return await response.json() as NorthernEnvironmentGridResponse
}

export async function inspectEnvironmentGridCell(lat: number, lon: number, time: string): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon), time })
  const response = await fetch(`${apiBaseUrl}/api/environment/grid/cell?${params.toString()}`)
  if (!response.ok) throw new Error(`环境栅格单元请求失败（HTTP ${response.status}）`)
  return await response.json() as Record<string, unknown>
}
