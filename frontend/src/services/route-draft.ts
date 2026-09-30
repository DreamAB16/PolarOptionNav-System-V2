import { getDistance } from 'ol/sphere'
import type { GeoPoint } from '../types/bridge'
import type { CaptainDraftRoute, DraftWaypoint } from '../types/navigation'

function waypoint(point: GeoPoint, sequence: number, name: string): DraftWaypoint {
  return { id: `wp-${sequence}-${Math.random().toString(36).slice(2, 8)}`, sequence, name, longitude: point.longitude, latitude: point.latitude, locked: false, mustPass: false, notes: '' }
}

export function createCaptainDraft(start: GeoPoint, destination: GeoPoint, now = new Date()): CaptainDraftRoute {
  return { id: `draft-${now.getTime()}`, waypoints: [waypoint(start, 1, '起点'), waypoint(destination, 2, '终点')], role: 'CAPTAIN_DRAFT', validation: 'UNCHECKED', lifecycle: 'DRAFT', distanceNm: distanceNm([start, destination]), modifiedAt: now.toISOString() }
}

export function distanceNm(points: Array<Pick<GeoPoint, 'longitude' | 'latitude'>>): number {
  let total = 0
  for (let i = 1; i < points.length; i += 1) total += getDistance([points[i - 1].longitude, points[i - 1].latitude], [points[i].longitude, points[i].latitude]) / 1852
  return total
}

export function addWaypoint(route: CaptainDraftRoute, point: GeoPoint, index = route.waypoints.length - 1): CaptainDraftRoute {
  const waypoints = [...route.waypoints]
  waypoints.splice(Math.max(1, Math.min(index, waypoints.length - 1)), 0, waypoint(point, 0, `航点 ${waypoints.length + 1}`))
  return changed({ ...route, waypoints })
}

export function updateWaypoint(route: CaptainDraftRoute, id: string, point: Pick<GeoPoint, 'longitude' | 'latitude'>): CaptainDraftRoute {
  return changed({ ...route, waypoints: route.waypoints.map((item) => item.id === id && !item.locked ? { ...item, longitude: point.longitude, latitude: point.latitude } : item) })
}

export function deleteWaypoint(route: CaptainDraftRoute, id: string): CaptainDraftRoute {
  if (route.waypoints.length <= 2) return route
  return changed({ ...route, waypoints: route.waypoints.filter((item) => item.id !== id).map((item, index) => ({ ...item, sequence: index + 1 })) })
}

export function toggleWaypointFlag(route: CaptainDraftRoute, id: string, field: 'locked' | 'mustPass'): CaptainDraftRoute {
  return changed({ ...route, waypoints: route.waypoints.map((item) => item.id === id ? { ...item, [field]: !item[field] } : item) })
}

function changed(route: CaptainDraftRoute): CaptainDraftRoute {
  return { ...route, validation: 'UNCHECKED', distanceNm: distanceNm(route.waypoints), modifiedAt: new Date().toISOString() }
}
