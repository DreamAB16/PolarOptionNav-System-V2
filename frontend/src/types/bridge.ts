export type PrimaryPanel = 'task' | 'vessel' | 'environment' | 'planning' | 'monitoring' | 'events'

export type PlanningStatus =
  | 'not_started'
  | 'waiting'
  | 'planning'
  | 'completed'
  | 'failed'
  | 'revalidation_required'
  | 'replanning'
  | 'emergency'

export interface GeoPoint {
  name: string
  longitude: number
  latitude: number
}

export interface TaskDraft {
  name: string
  start?: GeoPoint
  destination?: GeoPoint
  departureTime: string
  vesselId?: string
  planningMode: 'fastest' | 'lowest_risk' | 'balanced'
  notes: string
  tacticalHorizonNm?: number
  globalRouteContext?: string
  captainConstraints?: string
}

export interface NavigationTask extends TaskDraft {
  id: string
}

export interface VesselSummary {
  id: string
  name: string
  type: string
  iceClass: string
  length: number
  beam: number
  draft: number
  maxSpeed: number
  propulsion?: string
  propulsionPowerMw?: number
  iceThickness?: number
  snowThickness?: number
  iceSpeed?: string
  enduranceNmi?: number
  enduranceDays?: number
  position?: GeoPoint
  speed?: number
  heading?: number
  displacement?: number
}

export interface VesselProfileResponse {
  identity: { id: string; name: string; vessel_type: string; operator?: string }
  geometry: { length_m: number; beam_m: number; design_draft_m: number }
  mass: { design_displacement_t: number }
  propulsion: { type: string; azipod_count: number; azipod_power_mw_each: number; total_propulsion_power_mw: number }
  speed: { service_speed_min_kn: number; service_speed_max_kn: number; maximum_speed_kn: number; endurance_nmi: number; endurance_days: number }
  ice_capability: { ice_class: string; continuous_ice_thickness_m: number; continuous_snow_thickness_m: number; continuous_ice_speed_min_kn: number; continuous_ice_speed_max_kn: number }
}

export interface PlannerRouteObjectives {
  risk: number
  distance_km: number
  time_hours: number
}

export interface PlannerRoute {
  routeId: string
  objectives: PlannerRouteObjectives
  path: Array<{ latitude: number; longitude: number }>
}

export interface PlannerResponse {
  status: 'mock' | 'ready' | 'failed'
  route_points: Array<{ position: { latitude: number; longitude: number }; timestamp?: string }>
  eta?: string
  risk?: { status?: string; score?: number; factor_weights?: Record<string, number> }
  routes: PlannerRoute[]
  plan_id?: string
  metadata: {
    plan_id?: string
    representative_routes?: Record<string, PlannerRoute>
    recommended_route?: PlannerRoute
    risk_layers?: PlannerRiskLayers
    [key: string]: unknown
  }
}

export interface PlannerRiskLayers {
  width: number
  height: number
  cell_size_m?: number
  latitudes: number[] | number[][]
  longitudes: number[] | number[][]
  layers: {
    rio: number[][]
    fog: number[][]
    wind: number[][]
    wave: number[][]
    depth: number[][]
    combined: number[][]
  }
  cells?: PlannerGridCell[]
}

export interface PlannerGridCell {
  cell_id: string
  center: { latitude: number; longitude: number }
  bounds?: { north: number; east: number; south: number; west: number }
  geometry?: Array<[number, number]>
  cell_size_m: number
  environment: Record<string, number | null>
  risk: Record<'rio' | 'fog' | 'wind' | 'wave' | 'depth' | 'combined', number>
  quality: Record<string, 'real' | 'synthetic'>
  sources: Record<string, string>
  is_land?: boolean
  land_ratio?: number
  effective_speed_kn: number | null
  traversable: boolean
  obstacle_type?: string | null
  obstacle_reason?: string | null
}

export type PickTarget = 'start' | 'destination' | undefined
