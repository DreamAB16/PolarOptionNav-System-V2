import OSM from 'ol/source/OSM'
import { get as getProjection } from 'ol/proj'
import { describe, expect, it } from 'vitest'
import {
  configurePolarOsmReprojection,
  POLAR_OSM_MAX_ZOOM,
  POLAR_OSM_TILE_EXTENT,
  POLAR_OSM_TILE_SIZE,
} from './polar-osm'
import { POLAR_PROJECTION_CODE } from './polar-view'

describe('polar OSM reprojection', () => {
  it('uses an explicit EPSG:3413 target grid without changing OSM source tiles', () => {
    const source = configurePolarOsmReprojection(new OSM())
    const sourceGrid = source.getTileGrid()
    const polarGrid = source.getTileGridForProjection(getProjection(POLAR_PROJECTION_CODE)!)

    expect(source.getProjection()?.getCode()).toBe('EPSG:3857')
    if (!sourceGrid) throw new Error('OSM source must expose its native tile grid.')
    expect(sourceGrid.getExtent()).toEqual([
      -20_037_508.342789244,
      -20_037_508.342789244,
      20_037_508.342789244,
      20_037_508.342789244,
    ])
    expect(polarGrid.getExtent()).toEqual(POLAR_OSM_TILE_EXTENT)
    expect(polarGrid.getOrigin(0)).toEqual([-12_400_000, 12_400_000])
    expect(polarGrid.getTileSize(0)).toBe(POLAR_OSM_TILE_SIZE)
    expect(polarGrid.getMinZoom()).toBe(0)
    expect(polarGrid.getMaxZoom()).toBe(POLAR_OSM_MAX_ZOOM)
  })
})
