import OSM from 'ol/source/OSM'
import { createXYZ } from 'ol/tilegrid'
import { POLAR_PROJECTION_CODE } from './polar-view'

/**
 * EPSG:3413 coordinates of the equator are about 12,330 km from the pole.
 * This grid therefore covers the whole northern hemisphere with a small
 * rounding margin, while the strategic View itself stays limited to 30°N--90°N.
 */
export const POLAR_OSM_TILE_EXTENT = [-12_400_000, -12_400_000, 12_400_000, 12_400_000]
export const POLAR_OSM_TILE_SIZE = 256
export const POLAR_OSM_MAX_ZOOM = 19

/**
 * Keep the OSM source in its native EPSG:3857 scheme, but give OpenLayers an
 * independent EPSG:3413 target matrix for reprojection.  This must run before
 * the source requests its first polar tile.
 */
export function configurePolarOsmReprojection(source: OSM): OSM {
  source.setTileGridForProjection(
    POLAR_PROJECTION_CODE,
    createXYZ({
      extent: POLAR_OSM_TILE_EXTENT,
      tileSize: POLAR_OSM_TILE_SIZE,
      maxZoom: POLAR_OSM_MAX_ZOOM,
    }),
  )
  return source
}
