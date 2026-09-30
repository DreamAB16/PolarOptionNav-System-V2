import { describe, expect, it, vi } from 'vitest'
import type Map from 'ol/Map'
import {
  createPolarView,
  createStandardView,
  focusPolarView,
  POLAR_LEVEL_ZOOMS,
  POLAR_PROJECTION_CODE,
  POLAR_STRATEGIC_VIEW_EXTENT,
  setPolarNavigationLevel,
  STANDARD_PROJECTION_CODE,
} from './polar-view'

describe('map view modes', () => {
  it('creates the ordinary Web Mercator view', () => {
    const view = createStandardView()

    expect(view.getProjection().getCode()).toBe(STANDARD_PROJECTION_CODE)
    expect(view.getZoom()).toBe(5)
  })

  it('creates an EPSG:3413 strategic view covering the Arctic down to 30N', () => {
    const view = createPolarView()

    expect(view.getProjection().getCode()).toBe(POLAR_PROJECTION_CODE)
    expect(view.getProjection().getExtent()).toBeNull()
    expect(view.get('extent')).toEqual(POLAR_STRATEGIC_VIEW_EXTENT)
    expect(view.getCenter()).toEqual([0, 0])
    expect(POLAR_STRATEGIC_VIEW_EXTENT[2]).toBeGreaterThan(7_100_000)
    expect(view.getZoom()).toBeCloseTo(POLAR_LEVEL_ZOOMS.strategic)
    expect(view.getMaxZoom()).toBeGreaterThanOrEqual(20)
  })

  it('replaces the map view with EPSG:3413', () => {
    let selectedView = createStandardView()
    const map = {
      setView: vi.fn((view) => { selectedView = view }),
    } as unknown as Map

    focusPolarView(map)

    expect(map.setView).toHaveBeenCalledOnce()
    expect(selectedView.getProjection().getCode()).toBe(POLAR_PROJECTION_CODE)
  })

  it('switches between strategic and detailed polar levels', () => {
    const view = createPolarView()
    const map = { getView: () => view } as unknown as Map

    setPolarNavigationLevel(map, 'tactical')
    expect(view.getZoom()).toBe(POLAR_LEVEL_ZOOMS.tactical)

    setPolarNavigationLevel(map, 'strategic')
    expect(view.getZoom()).toBeCloseTo(POLAR_LEVEL_ZOOMS.strategic)
    expect(view.getCenter()?.[0]).toBeCloseTo(0, 3)
    expect(view.getCenter()?.[1]).toBeCloseTo(0, 3)
  })
})
