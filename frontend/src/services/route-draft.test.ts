import { describe, expect, it } from 'vitest'
import { addWaypoint, createCaptainDraft, deleteWaypoint, toggleWaypointFlag, updateWaypoint } from './route-draft'
import type { GeoPoint } from '../types/bridge'

const start: GeoPoint = { name: 'Start', longitude: 10, latitude: 70 }
const goal: GeoPoint = { name: 'Goal', longitude: 11, latitude: 71 }

describe('UI-only CaptainDraftRoute model', () => {
  it('creates a draft with explicit role, lifecycle, and unchecked validation', () => {
    const draft = createCaptainDraft(start, goal, new Date('2025-01-01T00:00:00Z'))
    expect(draft.role).toBe('CAPTAIN_DRAFT')
    expect(draft.lifecycle).toBe('DRAFT')
    expect(draft.validation).toBe('UNCHECKED')
    expect(draft.waypoints).toHaveLength(2)
    expect(draft.distanceNm).toBeGreaterThan(0)
  })

  it('supports add, move, insert/delete semantics and resets validation', () => {
    let draft = createCaptainDraft(start, goal)
    draft = addWaypoint(draft, { name: 'Mid', longitude: 10.5, latitude: 70.5 })
    expect(draft.waypoints).toHaveLength(3)
    const mid = draft.waypoints[1]
    draft = updateWaypoint(draft, mid.id, { longitude: 10.7, latitude: 70.6 })
    expect(draft.validation).toBe('UNCHECKED')
    expect(draft.waypoints[1].longitude).toBe(10.7)
    draft = deleteWaypoint(draft, mid.id)
    expect(draft.waypoints).toHaveLength(2)
  })

  it('keeps endpoints and supports lock/must-pass flags', () => {
    let draft = createCaptainDraft(start, goal)
    const first = draft.waypoints[0]
    draft = toggleWaypointFlag(draft, first.id, 'locked')
    draft = updateWaypoint(draft, first.id, { longitude: 99, latitude: 1 })
    expect(draft.waypoints[0].longitude).toBe(10)
    draft = toggleWaypointFlag(draft, first.id, 'mustPass')
    expect(draft.waypoints[0].mustPass).toBe(true)
    draft = deleteWaypoint(draft, first.id)
    expect(draft.waypoints).toHaveLength(2)
  })
})
