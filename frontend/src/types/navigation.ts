export type UiDataState = 'NOT_CONNECTED' | 'NOT_CALCULATED' | 'UNKNOWN' | 'UNAVAILABLE'

export type RouteRole = 'RECOMMENDED' | 'ALTERNATIVE' | 'CAPTAIN_DRAFT' | 'ACTIVE' | 'ARCHIVED'
export type ValidationStatus = 'UNCHECKED' | 'CHECKING' | 'VALID' | 'CONDITIONAL' | 'INVALID'
export type LifecycleStatus = 'DRAFT' | 'PROPOSED' | 'ACCEPTED' | 'ACTIVE' | 'SUPERSEDED' | 'ARCHIVED'

export interface DraftWaypoint {
  id: string
  sequence: number
  name: string
  longitude: number
  latitude: number
  locked: boolean
  mustPass: boolean
  notes: string
}

export interface CaptainDraftRoute {
  id: string
  waypoints: DraftWaypoint[]
  role: 'CAPTAIN_DRAFT'
  validation: 'UNCHECKED'
  lifecycle: 'DRAFT'
  distanceNm: number
  modifiedAt: string
}
